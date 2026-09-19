"""Offline, provider-neutral AI handoff with strict validation and audit trail."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from pydantic import BaseModel, ValidationError
from core.models import JournalLine, PipelineResult, ProcessingWarning, ReviewStatus, Severity
from core.schema_ai import AI_RESPONSE_SCHEMAS, AmbiguousTransactionResponse


class OfflineAIBridge:
    """Creates portable prompt files and consumes JSON answers; performs no network I/O."""

    def __init__(self, root: Path, accounts: dict[str, tuple[str, str]], data_root: Path | None = None) -> None:
        self.root = root
        self.data_root = data_root or root
        self.prompts_dir = root / "ai_bridge" / "prompts"
        self.tasks_dir = self.data_root / "ai_tasks"
        self.audit_path = self.data_root / "logs" / "ai_audit.jsonl"
        self.accounts = accounts
        for name in ("pending", "completed", "rejected"):
            (self.tasks_dir / name).mkdir(parents=True, exist_ok=True)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)

    def _render(self, template_name: str, values: dict[str, str]) -> tuple[str, str]:
        path = self.prompts_dir / template_name
        template = path.read_text(encoding="utf-8")
        rendered = template
        for key, value in values.items():
            rendered = rendered.replace("{{" + key + "}}", value)
        if "{{" in rendered:
            raise ValueError(f"placeholder مقداردهی‌نشده در {template_name}")
        return rendered, hashlib.sha256(template.encode()).hexdigest()

    def create_tasks(self, result: PipelineResult) -> list[Path]:
        paths: list[Path] = []
        account_text = "\n".join(f"- {code}: {name}" for code, name in sorted(set(self.accounts.values())))
        schema_model = AI_RESPONSE_SCHEMAS["resolve_ambiguous_transaction"]
        schema = json.dumps(schema_model.model_json_schema(), ensure_ascii=False, indent=2)
        for line in result.lines:
            if line.status != ReviewStatus.PENDING_AI:
                continue
            task_id = f"TX-{line.line_id}"
            task_json_path = self.tasks_dir / "pending" / f"{task_id}.task.json"
            response_path = self.tasks_dir / "pending" / f"{task_id}.response.json"
            if task_json_path.exists():
                result.pending_task_ids.append(task_id)
                continue
            prompt, prompt_hash = self._render("resolve_ambiguous_transaction.md", {
                "task_id": task_id, "document_number": line.document_number,
                "jalali_date": line.jalali_date, "transaction_description": line.description,
                "debit": str(line.debit), "credit": str(line.credit),
                "available_accounts": account_text, "json_schema": schema,
            })
            payload = {
                "task_id": task_id, "task_type": "resolve_ambiguous_transaction", "schema_version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(), "line_id": line.line_id,
                "prompt_template": "resolve_ambiguous_transaction.md", "prompt_sha256": prompt_hash,
                "response_file": response_path.name,
            }
            task_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            handoff = self.tasks_dir / "pending" / f"{task_id}.prompt.md"
            handoff.write_text(prompt + f"\n\n---\nپاسخ JSON را در فایل `{response_path.name}` ذخیره کنید.\n", encoding="utf-8")
            result.pending_task_ids.append(task_id)
            self._audit("task_created", payload | {"input": line.model_dump(mode="json")})
            paths.append(handoff)
        return paths

    def apply_responses(self, result: PipelineResult) -> None:
        line_map = {f"TX-{line.line_id}": line for line in result.lines}
        for task_path in sorted((self.tasks_dir / "pending").glob("*.task.json")):
            task = json.loads(task_path.read_text(encoding="utf-8"))
            task_id = task["task_id"]
            line = line_map.get(task_id)
            if line is None:
                continue
            response_path = task_path.with_name(task["response_file"])
            if not response_path.exists():
                continue
            raw_text = response_path.read_text(encoding="utf-8").strip()
            try:
                raw = json.loads(raw_text)
                model_class = AI_RESPONSE_SCHEMAS[task["task_type"]]
                validated: BaseModel = model_class.model_validate(raw)
                if validated.task_id != task_id:  # type: ignore[attr-defined]
                    raise ValueError("task_id پاسخ با درخواست تطابق ندارد")
                answer = validated
                if isinstance(answer, AmbiguousTransactionResponse):
                    self._apply_transaction(line, answer)
                self._audit("response_accepted", task | {"raw_output": raw, "validated_output": answer.model_dump(mode="json")})
                completed = self.tasks_dir / "completed"
                for path in task_path.parent.glob(f"{task_id}.*"):
                    path.replace(completed / path.name)
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                self._reject_or_request_correction(task, raw_text, str(exc), line, result)

    def _apply_transaction(self, line: JournalLine, answer: AmbiguousTransactionResponse) -> None:
        allowed = {code: name for code, name in self.accounts.values()}
        if answer.suggested_account_code and answer.suggested_account_code not in allowed:
            raise ValueError("کد حساب پیشنهادی خارج از فهرست مجاز است")
        line.description = answer.normalized_description
        line.confidence = answer.confidence
        if answer.suggested_account_code:
            line.account_code = answer.suggested_account_code
            line.account_name = allowed[answer.suggested_account_code]
        line.review_note = answer.reasoning
        line.status = ReviewStatus.HUMAN_REVIEW if answer.requires_human_review or answer.confidence < 0.6 else ReviewStatus.RESOLVED

    def _reject_or_request_correction(self, task: dict[str, Any], raw: str, error: str,
                                      line: JournalLine, result: PipelineResult) -> None:
        attempts = int(task.get("validation_attempts", 0)) + 1
        task["validation_attempts"] = attempts
        task_path = self.tasks_dir / "pending" / f"{task['task_id']}.task.json"
        self._audit("response_rejected", task | {"raw_output": raw, "validation_error": error})
        if attempts <= 2:
            model = AI_RESPONSE_SCHEMAS[task["task_type"]]
            prompt, _ = self._render("correct_invalid_response.md", {
                "task_id": task["task_id"], "validation_errors": error,
                "previous_response": raw, "json_schema": json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2),
            })
            correction = self.tasks_dir / "pending" / f"{task['task_id']}.correction-{attempts}.md"
            correction.write_text(prompt, encoding="utf-8")
            task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            line.status = ReviewStatus.HUMAN_REVIEW
            line.review_note = f"پاسخ هوش مصنوعی پس از دو اصلاح معتبر نشد: {error}"
            result.warnings.append(ProcessingWarning(code="AI_VALIDATION_FAILED", message=line.review_note,
                severity=Severity.ERROR, row_number=line.source_row, document_number=line.document_number))
            rejected = self.tasks_dir / "rejected"
            for path in task_path.parent.glob(f"{task['task_id']}.*"):
                path.replace(rejected / path.name)

    def _audit(self, event: str, data: dict[str, Any]) -> None:
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **data}
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

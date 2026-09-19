"""Persistent human work queue with safe field-level application."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.human_tasks import HumanField, HumanFieldOption, HumanTask, HumanTaskStatus
from core.models import PipelineResult, ReviewStatus


class HumanTaskStore:
    def __init__(self, data_root: Path) -> None:
        self.pending_dir = data_root / "human_tasks" / "pending"
        self.resolved_dir = data_root / "human_tasks" / "resolved"
        self.audit_path = data_root / "logs" / "human_task_audit.jsonl"
        for path in (self.pending_dir, self.resolved_dir, self.audit_path.parent):
            path.mkdir(parents=True, exist_ok=True)

    def create_for_result(self, result: PipelineResult,
                          accounts: dict[str, tuple[str, str]]) -> list[HumanTask]:
        created: list[HumanTask] = []
        options = [
            HumanFieldOption(value=code, label=f"{code} — {name}")
            for code, name in sorted(set(accounts.values()))
        ]
        for line in result.lines:
            if line.status != ReviewStatus.HUMAN_REVIEW:
                continue
            task_id = f"HUMAN-TX-{line.line_id}"
            if self._exists(task_id):
                continue
            task = HumanTask(
                task_id=task_id, task_type="transaction_review",
                title="تکمیل تصمیم حسابداری تراکنش",
                instructions="حساب صحیح را انتخاب کن و در صورت نیاز شرح استاندارد را اصلاح کن.",
                reason=line.review_note or "اطمینان تصمیم هوشمند برای ثبت قطعی کافی نیست.",
                priority="high",
                fields=[
                    HumanField(key="account_code", label="حساب نهایی", field_type="select",
                               options=options, default=line.account_code,
                               help_text="حساب قطعی که این ردیف باید روی آن ثبت شود."),
                    HumanField(key="normalized_description", label="شرح نهایی", field_type="text",
                               default=line.description, placeholder="شرح استاندارد سند"),
                    HumanField(key="review_note", label="یادداشت تصمیم", field_type="textarea",
                               required=False, placeholder="دلیل انتخاب یا مدرک مرتبط"),
                ],
                context={
                    "line_id": line.line_id, "document_number": line.document_number,
                    "jalali_date": line.jalali_date, "description": line.description,
                    "debit": float(line.debit), "credit": float(line.credit),
                    "suggested_account_code": line.account_code,
                    "suggested_account_name": line.account_name,
                },
            )
            self._save(task, self.pending_dir)
            self._audit("human_task_created", task.model_dump(mode="json"))
            created.append(task)
        for warning in result.warnings:
            if warning.code != "UNBALANCED_DOCUMENT" or not warning.document_number:
                continue
            digest = hashlib.sha256(warning.document_number.encode()).hexdigest()[:10]
            task_id = f"HUMAN-DOC-{digest}"
            if self._exists(task_id):
                continue
            task = HumanTask(
                task_id=task_id, task_type="document_review", title="رسیدگی به سند نامتوازن",
                instructions="سند و مدارک منبع را بررسی کن و نتیجه رسیدگی را ثبت کن.",
                reason=warning.message, priority="critical",
                fields=[
                    HumanField(key="acknowledged", label="بررسی سند انجام شد", field_type="boolean"),
                    HumanField(key="resolution_note", label="نتیجه و اقدام انجام‌شده", field_type="textarea",
                               placeholder="مثلاً ردیف جاافتاده، اصلاح مبلغ یا ارجاع به مسئول"),
                ],
                context={"document_number": warning.document_number, "warning": warning.message},
            )
            self._save(task, self.pending_dir)
            self._audit("human_task_created", task.model_dump(mode="json"))
            created.append(task)
        return created

    def apply_resolutions(self, result: PipelineResult) -> None:
        line_map = {line.line_id: line for line in result.lines}
        for path in self.resolved_dir.glob("*.json"):
            try:
                task = HumanTask.model_validate_json(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            if task.task_type != "transaction_review":
                continue
            line = line_map.get(str(task.context.get("line_id", "")))
            if not line:
                continue
            code = str(task.answers.get("account_code", ""))
            if code:
                line.account_code = code
                selected = next((option.label.split(" — ", 1)[-1] for option in task.fields[0].options
                                 if option.value == code), line.account_name)
                line.account_name = selected
            description = task.answers.get("normalized_description")
            if description:
                line.description = str(description)
            line.review_note = str(task.answers.get("review_note") or "تأیید و تکمیل توسط انسان")
            line.status = ReviewStatus.RESOLVED
            line.confidence = 1.0

    def resolve(self, task_id: str, answers: dict[str, Any]) -> HumanTask:
        path = self.pending_dir / f"{task_id}.json"
        if not path.exists():
            raise ValueError("کار انسانی پیدا نشد یا قبلاً تکمیل شده است")
        task = HumanTask.model_validate_json(path.read_text(encoding="utf-8"))
        task.answers = task.validate_answers(answers)
        if task.task_type == "document_review" and not task.answers.get("acknowledged"):
            raise ValueError("برای بستن کار، انجام بررسی سند باید تأیید شود")
        task.status = HumanTaskStatus.RESOLVED
        task.resolved_at = datetime.now(timezone.utc)
        resolved_path = self.resolved_dir / path.name
        self._save(task, self.resolved_dir)
        path.unlink(missing_ok=True)
        self._audit("human_task_resolved", task.model_dump(mode="json"))
        return task

    def pending(self) -> list[HumanTask]:
        tasks: list[HumanTask] = []
        for path in self.pending_dir.glob("*.json"):
            try:
                tasks.append(HumanTask.model_validate_json(path.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                continue
        priority = {"critical": 0, "high": 1, "normal": 2, "low": 3}
        return sorted(tasks, key=lambda item: (priority[item.priority], item.created_at))

    def stats(self) -> dict[str, int]:
        return {
            "pending": len(self.pending()),
            "resolved": len(list(self.resolved_dir.glob("*.json"))),
        }

    def _exists(self, task_id: str) -> bool:
        return (self.pending_dir / f"{task_id}.json").exists() or (self.resolved_dir / f"{task_id}.json").exists()

    @staticmethod
    def _save(task: HumanTask, directory: Path) -> None:
        (directory / f"{task.task_id}.json").write_text(task.model_dump_json(indent=2), encoding="utf-8")

    def _audit(self, event: str, payload: dict[str, Any]) -> None:
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **payload
            }, ensure_ascii=False, default=str) + "\n")

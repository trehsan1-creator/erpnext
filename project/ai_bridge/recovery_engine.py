"""Universal offline recovery engine: every unknown failure becomes a solvable task."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from core.human_task_store import HumanTaskStore
from core.human_tasks import HumanTask
from core.recovery_models import Blocker, BlockerStatus, RecoveryAIResponse, SourceStage


class RecoveryEngine:
    def __init__(self, project_root: Path, data_root: Path, human_store: HumanTaskStore) -> None:
        self.project_root = project_root
        self.data_root = data_root
        self.human_store = human_store
        self.pending = data_root / "recovery_tasks" / "pending"
        self.completed = data_root / "recovery_tasks" / "completed"
        self.audit_path = data_root / "logs" / "recovery_audit.jsonl"
        for path in (self.pending, self.completed, self.audit_path.parent):
            path.mkdir(parents=True, exist_ok=True)

    def capture(self, *, source_stage: SourceStage, operation: str, error_code: str, title: str,
                message: str, context: dict[str, Any] | None = None,
                safe_capabilities: list[str] | None = None, source_file: str | None = None) -> Blocker:
        canonical = json.dumps({
            "stage": source_stage, "operation": operation, "code": error_code,
            "message": message, "context": context or {},
        }, ensure_ascii=False, sort_keys=True, default=str)
        blocker_id = "RECOVERY-" + hashlib.sha256(canonical.encode()).hexdigest()[:14]
        existing = self.pending / f"{blocker_id}.blocker.json"
        if existing.exists():
            return Blocker.model_validate_json(existing.read_text(encoding="utf-8"))
        blocker = Blocker(
            blocker_id=blocker_id, source_stage=source_stage, operation=operation,
            error_code=error_code, title=title, message=message, context=context or {},
            safe_capabilities=safe_capabilities or ["request_human", "propose_safe_configuration"],
            source_file=source_file,
        )
        existing.write_text(blocker.model_dump_json(indent=2), encoding="utf-8")
        self._write_prompt(blocker)
        self._audit("blocker_captured", blocker.model_dump(mode="json"))
        return blocker

    def accept_response(self, blocker_id: str, payload: dict[str, Any]) -> tuple[RecoveryAIResponse, HumanTask | None]:
        blocker_path = self.pending / f"{blocker_id}.blocker.json"
        if not blocker_path.exists():
            raise ValueError("مانع فعال پیدا نشد یا قبلاً حل شده است")
        blocker = Blocker.model_validate_json(blocker_path.read_text(encoding="utf-8"))
        try:
            response = RecoveryAIResponse.model_validate(payload)
            if response.task_id != blocker_id:
                raise ValueError("task_id پاسخ با مانع عملیات تطابق ندارد")
        except (ValidationError, ValueError) as exc:
            blocker.attempts += 1
            blocker_path.write_text(blocker.model_dump_json(indent=2), encoding="utf-8")
            self._audit("recovery_response_rejected", {
                "blocker_id": blocker_id, "error": str(exc), "payload": payload,
            })
            raise ValueError(f"پاسخ بازیابی معتبر نیست: {exc}") from exc

        human_task: HumanTask | None = None
        needs_human = response.resolution_type in {
            "request_human", "manual_action", "not_safely_resolvable"
        } or response.requires_approval
        if needs_human:
            fields = response.human_fields
            if not fields:
                from core.human_tasks import HumanField
                fields = [HumanField(
                    key="approval_note", label="نظر و اقدام حسابدار", field_type="textarea",
                    placeholder="راه‌حل را بررسی و اقدام انجام‌شده را ثبت کنید.",
                )]
            human_task = HumanTask(
                task_id="HUMAN-" + blocker_id,
                task_type="data_completion",
                title=response.human_title or blocker.title,
                instructions=response.human_instructions or response.diagnosis,
                reason=response.reasoning,
                priority="high" if blocker.source_stage in {"validation", "erpnext_sync"} else "normal",
                fields=fields,
                context={
                    "blocker_id": blocker_id, "source_stage": blocker.source_stage,
                    "operation": blocker.operation, "error_code": blocker.error_code,
                    "source_file": blocker.source_file, **blocker.context,
                },
            )
            self.human_store.create_custom(human_task)
            blocker.status = BlockerStatus.PENDING_HUMAN
        else:
            # Auto-application requires a stage-specific allowlisted handler. Until one exists,
            # a generic recommendation is completed but never mutates accounting data.
            blocker.status = BlockerStatus.RESOLVED

        (self.pending / f"{blocker_id}.response.json").write_text(
            response.model_dump_json(indent=2), encoding="utf-8"
        )
        blocker_path.write_text(blocker.model_dump_json(indent=2), encoding="utf-8")
        for path in list(self.pending.glob(f"{blocker_id}.*")):
            path.replace(self.completed / path.name)
        self._audit("recovery_response_accepted", {
            "blocker": blocker.model_dump(mode="json"),
            "response": response.model_dump(mode="json"),
            "human_task_id": human_task.task_id if human_task else None,
        })
        return response, human_task

    def pending_tasks(self) -> list[Blocker]:
        tasks: list[Blocker] = []
        for path in self.pending.glob("*.blocker.json"):
            try:
                tasks.append(Blocker.model_validate_json(path.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                continue
        return sorted(tasks, key=lambda item: item.created_at)

    def prompt_path(self, blocker_id: str) -> Path:
        return self.pending / f"{blocker_id}.prompt.md"

    def _write_prompt(self, blocker: Blocker) -> None:
        template = (self.project_root / "ai_bridge" / "prompts" / "resolve_system_blocker.md").read_text(encoding="utf-8")
        values = {
            "task_id": blocker.blocker_id, "source_stage": blocker.source_stage,
            "operation": blocker.operation, "error_code": blocker.error_code,
            "title": blocker.title, "message": blocker.message,
            "context": json.dumps(blocker.context, ensure_ascii=False, indent=2, default=str),
            "safe_capabilities": json.dumps(blocker.safe_capabilities, ensure_ascii=False, indent=2),
            "json_schema": json.dumps(RecoveryAIResponse.model_json_schema(), ensure_ascii=False, indent=2),
        }
        for key, value in values.items():
            template = template.replace("{{" + key + "}}", value)
        (self.pending / f"{blocker.blocker_id}.prompt.md").write_text(template, encoding="utf-8")

    def _audit(self, event: str, payload: dict[str, Any]) -> None:
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **payload,
            }, ensure_ascii=False, default=str) + "\n")

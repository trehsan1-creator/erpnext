"""Offline handoff for learning new spreadsheet layouts as safe JSON profiles."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

from core.parser_config import ParserConfigAIResponse, ParserProfile
from core.text import normalize_persian
from parsers.profile_store import ParserProfileStore


class ParserLearningBridge:
    def __init__(self, project_root: Path, data_root: Path) -> None:
        self.project_root = project_root
        self.data_root = data_root
        self.tasks = data_root / "parser_tasks"
        self.pending = self.tasks / "pending"
        self.completed = self.tasks / "completed"
        self.audit_path = data_root / "logs" / "parser_learning_audit.jsonl"
        self.store = ParserProfileStore(data_root)
        for folder in (self.pending, self.completed, self.audit_path.parent):
            folder.mkdir(parents=True, exist_ok=True)

    def create_task(self, source: Path, reason: str) -> dict[str, Any]:
        preview = self._preview(source)
        digest = hashlib.sha256((source.suffix.lower() + preview).encode("utf-8")).hexdigest()[:12]
        task_id = f"PARSER-{digest}"
        schema = json.dumps(ParserConfigAIResponse.model_json_schema(), ensure_ascii=False, indent=2)
        template_path = self.project_root / "ai_bridge" / "prompts" / "build_parser_config.md"
        template = template_path.read_text(encoding="utf-8")
        values = {
            "task_id": task_id,
            "file_name": source.name,
            "file_type": source.suffix.lower().lstrip("."),
            "failure_reason": reason,
            "file_preview": preview,
            "json_schema": schema,
        }
        prompt = template
        for key, value in values.items():
            prompt = prompt.replace("{{" + key + "}}", value)
        prompt_path = self.pending / f"{task_id}.prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        metadata = {
            "task_id": task_id,
            "source_name": source.name,
            "source_path": str(source),
            "file_type": source.suffix.lower().lstrip("."),
            "reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "prompt_sha256": hashlib.sha256(template.encode()).hexdigest(),
        }
        (self.pending / f"{task_id}.task.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._audit("parser_task_created", metadata)
        return {"task_id": task_id, "file_name": source.name, "reason": reason}

    def accept_config(self, task_id: str, payload: dict[str, Any], source: Path,
                      persist: bool = True) -> ParserProfile:
        task_path = self.pending / f"{task_id}.task.json"
        if not task_path.exists():
            raise ValueError("وظیفه ساخت Parser پیدا نشد یا قبلاً تکمیل شده است")
        try:
            answer = ParserConfigAIResponse.model_validate(payload)
            if answer.task_id != task_id:
                raise ValueError("task_id کانفیگ با مأموریت تطابق ندارد")
            expected_type = source.suffix.lower().lstrip(".")
            if answer.file_type != expected_type:
                raise ValueError("نوع فایل کانفیگ با فایل بارگذاری‌شده تطابق ندارد")
            profile_id = "profile-" + hashlib.sha256(
                json.dumps(answer.model_dump(mode="json"), ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()[:12]
            profile = ParserProfile(
                profile_id=profile_id,
                signature_headers=[],
                **answer.model_dump(exclude={"task_id"}),
            )
            headers = ParserProfileStore._headers(source, profile)
            required = {normalize_persian(item) for item in ParserProfileStore._mapped_headers(profile)}
            missing = sorted(required - set(headers))
            if missing:
                raise ValueError("ستون‌های معرفی‌شده در فایل پیدا نشدند: " + "، ".join(missing))
            profile.signature_headers = headers
            if persist:
                self.complete_config(task_id, payload, profile, source.name)
            return profile
        except (ValidationError, ValueError) as exc:
            self._audit("parser_profile_rejected", {"task_id": task_id, "error": str(exc), "payload": payload})
            raise ValueError(f"کانفیگ Parser معتبر نیست: {exc}") from exc

    def complete_config(self, task_id: str, payload: dict[str, Any], profile: ParserProfile,
                        source_name: str) -> None:
        """Persist only after the profile has successfully parsed its source file."""
        self.store.save(profile)
        response_path = self.pending / f"{task_id}.response.json"
        response_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        for path in list(self.pending.glob(f"{task_id}.*")):
            path.replace(self.completed / path.name)
        self._audit("parser_profile_accepted", {
            "task_id": task_id, "profile": profile.model_dump(mode="json"), "source": source_name
        })

    def _preview(self, source: Path) -> str:
        try:
            if source.suffix.lower() == ".csv":
                frame = pd.read_csv(source, header=None, nrows=12, dtype=object, encoding="utf-8-sig")
                return self._frame_preview("CSV", frame)
            book = pd.ExcelFile(source)
            sections: list[str] = []
            for sheet in book.sheet_names[:4]:
                frame = pd.read_excel(source, sheet_name=sheet, header=None, nrows=12, dtype=object)
                sections.append(self._frame_preview(f"Sheet: {sheet}", frame))
            return "\n\n".join(sections)
        except Exception as exc:
            return f"پیش‌نمایش ساختاری ممکن نشد: {exc}"

    @staticmethod
    def _frame_preview(title: str, frame: pd.DataFrame) -> str:
        safe = frame.fillna("").astype(str)
        safe = safe.iloc[:, :30]
        lines = [f"## {title}"]
        for row_number, (_, row) in enumerate(safe.iterrows(), start=1):
            values = [normalize_persian(value)[:120] for value in row.tolist()]
            lines.append(f"Row {row_number}: " + json.dumps(values, ensure_ascii=False))
        return "\n".join(lines)

    def _audit(self, event: str, data: dict[str, Any]) -> None:
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **data}
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

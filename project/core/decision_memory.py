"""Auditable learning memory built from repeated human-approved decisions."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.models import PipelineResult, ReviewStatus
from core.text import normalize_persian


class DecisionMemory:
    """Promotes an exact recurring description after repeated human confirmations."""

    def __init__(self, data_root: Path, promotion_threshold: int = 2) -> None:
        self.path = data_root / "learning" / "decision_memory.json"
        self.audit_path = data_root / "logs" / "learning_audit.jsonl"
        self.threshold = promotion_threshold
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def pattern(description: str) -> str:
        return normalize_persian(description).casefold()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"patterns": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"patterns": {}}

    def record(self, description: str, account_code: str, account_name: str) -> int:
        data = self._load()
        pattern = self.pattern(description)
        key = hashlib.sha256(pattern.encode()).hexdigest()[:16]
        item = data["patterns"].get(key, {
            "pattern": pattern, "account_code": account_code, "account_name": account_name,
            "confirmations": 0, "conflicts": 0,
        })
        if item["account_code"] == account_code:
            item["confirmations"] += 1
            item["account_name"] = account_name
        else:
            item["conflicts"] += 1
            item["confirmations"] = 1
            item["account_code"] = account_code
            item["account_name"] = account_name
        item["updated_at"] = datetime.now(timezone.utc).isoformat()
        item["promoted"] = item["confirmations"] >= self.threshold and item["conflicts"] == 0
        data["patterns"][key] = item
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self._audit("human_decision_recorded", {"pattern_id": key, **item})
        return int(item["confirmations"])

    def apply(self, result: PipelineResult) -> int:
        patterns = self._load().get("patterns", {})
        promoted = {item["pattern"]: item for item in patterns.values() if item.get("promoted")}
        applied = 0
        for line in result.lines:
            if line.status != ReviewStatus.PENDING_AI:
                continue
            item = promoted.get(self.pattern(line.description))
            if not item:
                continue
            line.account_code = item["account_code"]
            line.account_name = item["account_name"]
            line.status = ReviewStatus.RESOLVED
            line.confidence = 0.99
            line.review_note = f"قاعده یادگرفته‌شده با {item['confirmations']} تأیید انسانی"
            applied += 1
        if applied:
            self._audit("learned_rules_applied", {"count": applied})
        return applied

    def stats(self) -> dict[str, int]:
        items = list(self._load().get("patterns", {}).values())
        return {
            "observed_patterns": len(items),
            "promoted_rules": sum(bool(item.get("promoted")) for item in items),
            "human_confirmations": sum(int(item.get("confirmations", 0)) for item in items),
        }

    def _audit(self, event: str, payload: dict[str, Any]) -> None:
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **payload
            }, ensure_ascii=False, default=str) + "\n")

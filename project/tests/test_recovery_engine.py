from pathlib import Path

from ai_bridge.recovery_engine import RecoveryEngine
from core.human_task_store import HumanTaskStore


def test_unknown_blocker_becomes_prompt_then_human_form(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[1]
    human_store = HumanTaskStore(tmp_path)
    engine = RecoveryEngine(project_root, tmp_path, human_store)
    blocker = engine.capture(
        source_stage="erpnext_sync", operation="submit_journal", error_code="MISSING_COST_CENTER",
        title="مرکز هزینه مشخص نیست", message="ERPNext برای این حساب مرکز هزینه می‌خواهد",
        context={"document_number": "100"}, safe_capabilities=["request_human"],
    )
    assert engine.prompt_path(blocker.blocker_id).exists()
    response = {
        "task_id": blocker.blocker_id,
        "diagnosis": "مرکز هزینه اجباری است و از داده منبع قابل تشخیص نیست.",
        "resolution_type": "request_human",
        "proposed_values": {},
        "human_title": "مرکز هزینه را تعیین کن",
        "human_instructions": "مرکز هزینه صحیح سند را انتخاب کنید.",
        "human_fields": [{
            "key": "cost_center", "label": "مرکز هزینه", "field_type": "text",
            "required": True, "placeholder": "نام یا کد مرکز هزینه"
        }],
        "reusable_rule": None,
        "confidence": 0.98,
        "reasoning": "این مقدار باید توسط مسئول شرکت تعیین شود.",
        "requires_approval": True,
    }
    _, task = engine.accept_response(blocker.blocker_id, response)
    assert task is not None
    assert task.fields[0].key == "cost_center"
    assert human_store.stats()["pending"] == 1
    assert not engine.pending_tasks()

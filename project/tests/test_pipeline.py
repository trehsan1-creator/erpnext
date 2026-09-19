import json
from pathlib import Path
import pandas as pd
from ai_bridge.client import OfflineAIBridge
from core.models import ReviewStatus
from exporters.excel_report import PersianExcelReport
from parsers.excel_parser import ExcelParser


def test_end_to_end_offline_handoff(tmp_path: Path) -> None:
    source = tmp_path / "input.xlsx"
    pd.DataFrame([
        {"شماره سند": 1, "تاریخ": "1403/01/01", "شرح": "مورد ناشناخته", "بدهکار": 100, "بستانکار": 0},
        {"شماره سند": 1, "تاریخ": "1403/01/01", "شرح": "بانک", "بدهکار": 0, "بستانکار": 100},
    ]).to_excel(source, index=False)
    parser = ExcelParser(); result = parser.parse(source)
    bridge = OfflineAIBridge(tmp_path, parser.accounts)
    # Tests use copied external prompts, exactly like a deployed project.
    prompt_src = Path(__file__).parents[1] / "ai_bridge" / "prompts"
    bridge.prompts_dir.mkdir(parents=True, exist_ok=True)
    for item in prompt_src.glob("*.md"):
        (bridge.prompts_dir / item.name).write_text(item.read_text(encoding="utf-8"), encoding="utf-8")
    tasks = bridge.create_tasks(result)
    assert len(tasks) == 1
    task_id = result.pending_task_ids[0]
    response = {
        "task_id": task_id, "normalized_description": "سایر پرداخت‌ها", "transaction_type": "پرداخت",
        "suggested_account_code": "610101", "suggested_account_name": "هزینه اجاره",
        "confidence": 0.8, "reasoning": "بر اساس اطلاعات ارائه‌شده", "requires_human_review": False,
    }
    (tmp_path / "ai_tasks" / "pending" / f"{task_id}.response.json").write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
    bridge.apply_responses(result)
    assert result.lines[0].status == ReviewStatus.RESOLVED
    report = PersianExcelReport(Path(__file__).parents[1]).export(result, tmp_path / "report.xlsx")
    assert report.exists()

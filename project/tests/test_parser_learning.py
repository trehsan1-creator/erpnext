import json
from pathlib import Path

from openpyxl import Workbook
import pytest

from ai_bridge.parser_learning import ParserLearningBridge
from parsers.errors import UnsupportedFormatError
from parsers.excel_parser import ExcelParser
from parsers.profile_store import ParserProfileStore


def test_unknown_layout_can_be_learned_and_reused(tmp_path: Path) -> None:
    source = tmp_path / "bank-layout.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["گزارش اختصاصی بانک"])
    sheet.append(["دوره آزمایشی"])
    sheet.append(["شناسه", "روز عملیات", "یادداشت تراکنش", "خالص مبلغ"])
    sheet.append(["A-1", "1403/04/01", "دریافت از مشتری", 5000])
    sheet.append(["A-2", "1403/04/01", "پرداخت متفرقه", -5000])
    workbook.save(source)

    with pytest.raises(UnsupportedFormatError):
        ExcelParser().parse(source)

    project_root = Path(__file__).parents[1]
    learning = ParserLearningBridge(project_root, tmp_path)
    task = learning.create_task(source, "ستون‌های استاندارد پیدا نشدند")
    answer = {
        "task_id": task["task_id"],
        "profile_name": "گردش اختصاصی بانک آزمایشی",
        "file_type": "xlsx",
        "sheet_name": 0,
        "header_row": 3,
        "columns": {
            "document_number": "شناسه", "date": "روز عملیات",
            "description": "یادداشت تراکنش", "amount": "خالص مبلغ"
        },
        "amount_strategy": "signed_amount",
        "debit_when_positive": True,
        "date_system": "jalali",
        "confidence": 0.95,
        "reasoning": "ردیف سوم هدر و مبلغ دارای علامت است.",
        "requires_human_review": False,
    }
    profile = learning.accept_config(task["task_id"], answer, source, persist=False)
    result = ExcelParser(profile=profile).parse(source)
    assert len(result.lines) == 2
    assert result.lines[0].debit == 5000
    assert result.lines[1].credit == 5000
    learning.complete_config(task["task_id"], answer, profile, source.name)

    learned = ParserProfileStore(tmp_path).find_match(source)
    assert learned is not None
    assert learned.profile_name == "گردش اختصاصی بانک آزمایشی"
    assert json.loads((tmp_path / "parser_profiles" / f"{profile.profile_id}.json").read_text())["usage_count"] == 1

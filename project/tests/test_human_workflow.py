from datetime import date
from pathlib import Path

from core.decision_memory import DecisionMemory
from core.human_task_store import HumanTaskStore
from core.models import JournalDocument, JournalLine, PipelineResult, ReviewStatus


def make_result(status: ReviewStatus = ReviewStatus.HUMAN_REVIEW) -> PipelineResult:
    line = JournalLine(
        line_id="stable-line", source_row=2, document_number="100", gregorian_date=date(2024, 3, 20),
        jalali_date="1403/01/01", description="پرداخت سرویس تکراری", debit=100, credit=0,
        status=status, review_note="حساب مناسب با اطمینان کافی مشخص نیست",
    )
    document = JournalDocument(number="100", gregorian_date=line.gregorian_date,
                               jalali_date=line.jalali_date, lines=[line])
    return PipelineResult(source_file="test.xlsx", documents=[document])


def test_human_task_applies_answer_and_persists(tmp_path: Path) -> None:
    accounts = {"اجاره": ("610101", "هزینه اجاره")}
    store = HumanTaskStore(tmp_path)
    result = make_result()
    tasks = store.create_for_result(result, accounts)
    transaction_task = next(task for task in tasks if task.task_type == "transaction_review")
    store.resolve(transaction_task.task_id, {
        "account_code": "610101",
        "normalized_description": "پرداخت سرویس تکراری",
        "review_note": "طبق قرارداد",
    })
    fresh = make_result()
    store.apply_resolutions(fresh)
    assert fresh.lines[0].status == ReviewStatus.RESOLVED
    assert fresh.lines[0].account_code == "610101"
    assert store.stats()["resolved"] == 1


def test_repeated_approved_decision_becomes_rule(tmp_path: Path) -> None:
    memory = DecisionMemory(tmp_path, promotion_threshold=2)
    memory.record("پرداخت سرویس تکراری", "610101", "هزینه اجاره")
    assert memory.apply(make_result(ReviewStatus.PENDING_AI)) == 0
    memory.record("پرداخت سرویس تکراری", "610101", "هزینه اجاره")
    result = make_result(ReviewStatus.PENDING_AI)
    assert memory.apply(result) == 1
    assert result.lines[0].status == ReviewStatus.RESOLVED
    assert result.lines[0].confidence == 0.99

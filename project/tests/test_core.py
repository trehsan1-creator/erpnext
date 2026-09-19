from decimal import Decimal
import pytest
from core.models import JournalLine
from core.text import normalize_persian, parse_decimal


def test_persian_normalization() -> None:
    assert normalize_persian("كالا ۱۲۳") == "کالا 123"
    assert parse_decimal("۱٬۲۳۴٬۵۶۷") == Decimal("1234567")


def test_line_rejects_double_sided_amount() -> None:
    with pytest.raises(ValueError):
        JournalLine(source_row=2, document_number="1", gregorian_date="2024-03-20", jalali_date="1403/01/01",
                    description="آزمون", debit=100, credit=100)

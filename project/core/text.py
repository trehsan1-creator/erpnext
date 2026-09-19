"""Persian text and number normalization helpers."""
from decimal import Decimal, InvalidOperation
from typing import Any

FA_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
AR_TO_FA = str.maketrans({"ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه"})


def normalize_persian(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).translate(FA_TO_EN).translate(AR_TO_FA)
    return " ".join(text.replace("\u200c", " ").split()).strip()


def parse_decimal(value: Any) -> Decimal:
    if value is None or (isinstance(value, float) and value != value):
        return Decimal("0")
    cleaned = normalize_persian(value).replace(",", "").replace("٬", "").replace("ریال", "").strip()
    if not cleaned:
        return Decimal("0")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"مبلغ نامعتبر: {value}") from exc

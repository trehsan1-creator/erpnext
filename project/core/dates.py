"""Jalali/Gregorian date conversion."""
from datetime import date, datetime
from typing import Any
import jdatetime
from core.text import normalize_persian


def parse_accounting_date(value: Any) -> tuple[date, str]:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        gregorian = value
        j = jdatetime.date.fromgregorian(date=gregorian)
        return gregorian, j.strftime("%Y/%m/%d")
    text = normalize_persian(value).replace("-", "/")
    parts = text.split("/")
    if len(parts) != 3:
        raise ValueError(f"تاریخ نامعتبر: {value}")
    year, month, day = map(int, parts)
    if year < 1700:
        jalali = jdatetime.date(year, month, day)
        return jalali.togregorian(), f"{year:04d}/{month:02d}/{day:02d}"
    gregorian = date(year, month, day)
    j = jdatetime.date.fromgregorian(date=gregorian)
    return gregorian, j.strftime("%Y/%m/%d")

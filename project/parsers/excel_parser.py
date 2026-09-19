"""Fault-tolerant Excel/CSV parser with declarative learned profiles."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
import hashlib
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

from core.dates import parse_accounting_date
from core.models import JournalDocument, JournalLine, PipelineResult, ProcessingWarning, ReviewStatus, Severity
from core.parser_config import ParserProfile
from core.text import normalize_persian, parse_decimal
from parsers.base_parser import BaseParser
from parsers.errors import UnsupportedFormatError

ALIASES = {
    "document_number": ("شماره سند", "شماره", "سند", "document_number", "doc_no"),
    "date": ("تاریخ", "تاریخ سند", "date", "document_date"),
    "description": ("شرح", "شرح سند", "description", "memo"),
    "debit": ("بدهکار", "مبلغ بدهکار", "debit"),
    "credit": ("بستانکار", "مبلغ بستانکار", "credit"),
    "account_code": ("کد حساب", "کد", "account_code"),
    "account_name": ("نام حساب", "حساب", "account_name"),
    "reference": ("عطف", "مرجع", "reference"),
    "counterparty": ("طرف حساب", "نام طرف حساب", "counterparty"),
}


class ExcelParser(BaseParser):
    def __init__(self, accounts: dict[str, tuple[str, str]] | None = None,
                 profile: ParserProfile | None = None) -> None:
        super().__init__(accounts)
        self.profile = profile

    def parse(self, path: Path) -> PipelineResult:
        result = PipelineResult(source_file=str(path))
        frame, header_row = self._read(path)
        frame.columns = [normalize_persian(column) for column in frame.columns]
        mapping = self._mapping(frame)
        grouped: dict[str, list[JournalLine]] = defaultdict(list)
        for source_row, (_, series) in enumerate(frame.iterrows(), start=header_row + 1):
            raw = {str(key): (None if pd.isna(value) else value) for key, value in series.to_dict().items()}
            try:
                row = {normalize_persian(key): value for key, value in raw.items()}
                doc_no = normalize_persian(self._value(row, mapping, "document_number")) or f"ROW-{source_row}"
                gregorian, jalali = parse_accounting_date(self._value(row, mapping, "date"))
                description = normalize_persian(self._value(row, mapping, "description"))
                if not description:
                    raise ValueError("شرح تراکنش خالی است")
                debit, credit = self._amounts(row, mapping)
                account_code = normalize_persian(self._value(row, mapping, "account_code")) or None
                account_name = normalize_persian(self._value(row, mapping, "account_name")) or None
                status = ReviewStatus.RESOLVED
                confidence: float | None = 1.0
                if not account_code:
                    match = self.classify_deterministically(description)
                    if match:
                        account_code, account_name = match
                        confidence = 0.95
                    else:
                        status, confidence = ReviewStatus.PENDING_AI, None
                stable_id = hashlib.sha256(
                    f"{path.resolve()}|{source_row}|{doc_no}".encode()
                ).hexdigest()[:12]
                line = JournalLine(
                    line_id=stable_id, source_row=source_row, document_number=doc_no,
                    gregorian_date=gregorian, jalali_date=jalali, description=description,
                    debit=debit, credit=credit, account_code=account_code, account_name=account_name,
                    counterparty=normalize_persian(self._value(row, mapping, "counterparty")) or None,
                    reference=normalize_persian(self._value(row, mapping, "reference")) or None,
                    status=status, confidence=confidence, raw_data=raw,
                )
                grouped[doc_no].append(line)
            except (ValueError, ValidationError, TypeError) as exc:
                result.invalid_rows.append({"source_row": source_row, "error": str(exc), "raw_data": raw})
                result.warnings.append(ProcessingWarning(
                    code="INVALID_ROW", message=str(exc), severity=Severity.ERROR, row_number=source_row
                ))
        if not grouped and len(frame.index):
            raise UnsupportedFormatError(
                "هیچ ردیف حسابداری معتبری با این نگاشت استخراج نشد", list(frame.columns)
            )
        for number, lines in grouped.items():
            document = JournalDocument(
                number=number, gregorian_date=min(line.gregorian_date for line in lines),
                jalali_date=min(line.jalali_date for line in lines), lines=lines,
            )
            result.documents.append(document)
            if not document.is_balanced:
                result.warnings.append(ProcessingWarning(
                    code="UNBALANCED_DOCUMENT",
                    message=f"سند تراز نیست؛ اختلاف: {document.total_debit - document.total_credit:,}",
                    document_number=number, severity=Severity.ERROR,
                ))
        result.documents.sort(key=lambda document: (document.gregorian_date, document.number))
        return result

    def _read(self, path: Path) -> tuple[pd.DataFrame, int]:
        header_row = self.profile.header_row if self.profile else 1
        try:
            if path.suffix.lower() == ".csv":
                encoding = self.profile.encoding if self.profile else "utf-8-sig"
                frame = pd.read_csv(path, dtype=object, header=header_row - 1, encoding=encoding)
            else:
                sheet = self.profile.sheet_name if self.profile else 0
                frame = pd.read_excel(path, dtype=object, header=header_row - 1, sheet_name=sheet)
            if not isinstance(frame, pd.DataFrame):
                raise ValueError("شیت انتخاب‌شده قابل خواندن نیست")
            return frame, header_row
        except Exception as exc:
            raise UnsupportedFormatError(f"خواندن ساختار فایل ممکن نشد: {exc}") from exc

    def _mapping(self, frame: pd.DataFrame) -> dict[str, str | None]:
        headers = list(frame.columns)
        if self.profile:
            values = self.profile.columns.model_dump()
            mapping = {
                key: normalize_persian(value) if value else None for key, value in values.items()
            }
        else:
            mapping = {
                field: next((alias for alias in aliases if alias in headers), None)
                for field, aliases in ALIASES.items()
            }
            mapping["amount"] = None
            mapping["direction"] = None
        missing = [field for field in ("date", "description") if not mapping.get(field)]
        has_amount = bool(
            (mapping.get("debit") and mapping.get("credit")) or mapping.get("amount")
        )
        if missing or not has_amount:
            details = []
            if missing:
                details.append("ستون‌های الزامی ناشناخته: " + "، ".join(missing))
            if not has_amount:
                details.append("ستون یا ساختار مبلغ تشخیص داده نشد")
            raise UnsupportedFormatError("؛ ".join(details), headers)
        unknown = [value for value in mapping.values() if value and value not in headers]
        if unknown:
            raise UnsupportedFormatError(
                "ستون‌های کانفیگ در فایل وجود ندارند: " + "، ".join(unknown), headers
            )
        return mapping

    @staticmethod
    def _value(row: dict[str, Any], mapping: dict[str, str | None], field: str) -> Any:
        column = mapping.get(field)
        return row.get(column) if column else None

    def _profile_decimal(self, value: Any) -> Decimal:
        if not self.profile:
            return parse_decimal(value)
        text = normalize_persian(value)
        if self.profile.thousands_separator:
            text = text.replace(self.profile.thousands_separator, "")
        if self.profile.decimal_separator != ".":
            text = text.replace(self.profile.decimal_separator, ".")
        return parse_decimal(text)

    def _amounts(self, row: dict[str, Any], mapping: dict[str, str | None]) -> tuple[Decimal, Decimal]:
        strategy = self.profile.amount_strategy if self.profile else "separate_columns"
        if strategy == "separate_columns":
            return (
                self._profile_decimal(self._value(row, mapping, "debit")),
                self._profile_decimal(self._value(row, mapping, "credit")),
            )
        amount = self._profile_decimal(self._value(row, mapping, "amount"))
        if strategy == "signed_amount":
            debit_positive = self.profile.debit_when_positive if self.profile else True
            is_debit = (amount >= 0) == debit_positive
            return (abs(amount), Decimal("0")) if is_debit else (Decimal("0"), abs(amount))
        direction = normalize_persian(self._value(row, mapping, "direction")).casefold()
        debit_values = {normalize_persian(item).casefold() for item in (self.profile.debit_direction_values if self.profile else [])}
        credit_values = {normalize_persian(item).casefold() for item in (self.profile.credit_direction_values if self.profile else [])}
        if direction in debit_values:
            return abs(amount), Decimal("0")
        if direction in credit_values:
            return Decimal("0"), abs(amount)
        raise ValueError(f"جهت مبلغ ناشناخته است: {direction}")

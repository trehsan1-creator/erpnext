"""Fault-tolerant Excel/CSV parser for common Iranian accounting exports."""
from __future__ import annotations
from collections import defaultdict
import hashlib
from pathlib import Path
from typing import Any
import pandas as pd
from pydantic import ValidationError
from core.dates import parse_accounting_date
from core.models import JournalDocument, JournalLine, PipelineResult, ProcessingWarning, ReviewStatus, Severity
from core.text import normalize_persian, parse_decimal
from parsers.base_parser import BaseParser

ALIASES = {
    "document": ("شماره سند", "شماره", "سند", "document_number", "doc_no"),
    "date": ("تاریخ", "تاریخ سند", "date", "document_date"),
    "description": ("شرح", "شرح سند", "description", "memo"),
    "debit": ("بدهکار", "مبلغ بدهکار", "debit"),
    "credit": ("بستانکار", "مبلغ بستانکار", "credit"),
    "account_code": ("کد حساب", "کد", "account_code"),
    "account_name": ("نام حساب", "حساب", "account_name"),
    "reference": ("عطف", "مرجع", "reference"),
}


class ExcelParser(BaseParser):
    def parse(self, path: Path) -> PipelineResult:
        result = PipelineResult(source_file=str(path))
        try:
            frame = pd.read_csv(path, dtype=object) if path.suffix.lower() == ".csv" else pd.read_excel(path, dtype=object)
        except Exception as exc:
            raise ValueError(f"خواندن فایل ورودی ممکن نشد: {exc}") from exc
        frame.columns = [normalize_persian(c) for c in frame.columns]
        grouped: dict[str, list[JournalLine]] = defaultdict(list)
        for source_row, (_, series) in enumerate(frame.iterrows(), start=2):
            raw = {str(k): (None if pd.isna(v) else v) for k, v in series.to_dict().items()}
            try:
                row = {normalize_persian(k): v for k, v in raw.items()}
                doc_no = normalize_persian(self.first_value(row, ALIASES["document"])) or f"ROW-{source_row}"
                gregorian, jalali = parse_accounting_date(self.first_value(row, ALIASES["date"]))
                description = normalize_persian(self.first_value(row, ALIASES["description"]))
                if not description:
                    raise ValueError("شرح تراکنش خالی است")
                account_code = normalize_persian(self.first_value(row, ALIASES["account_code"])) or None
                account_name = normalize_persian(self.first_value(row, ALIASES["account_name"])) or None
                status = ReviewStatus.RESOLVED
                confidence: float | None = 1.0
                if not account_code:
                    match = self.classify_deterministically(description)
                    if match:
                        account_code, account_name = match
                        confidence = 0.95
                    else:
                        status, confidence = ReviewStatus.PENDING_AI, None
                stable_id = hashlib.sha256(f"{path.resolve()}|{source_row}|{doc_no}".encode()).hexdigest()[:12]
                line = JournalLine(line_id=stable_id, source_row=source_row, document_number=doc_no, gregorian_date=gregorian,
                    jalali_date=jalali, description=description,
                    debit=parse_decimal(self.first_value(row, ALIASES["debit"])),
                    credit=parse_decimal(self.first_value(row, ALIASES["credit"])),
                    account_code=account_code, account_name=account_name,
                    reference=normalize_persian(self.first_value(row, ALIASES["reference"])) or None,
                    status=status, confidence=confidence, raw_data=raw)
                grouped[doc_no].append(line)
            except (ValueError, ValidationError, TypeError) as exc:
                result.invalid_rows.append({"source_row": source_row, "error": str(exc), "raw_data": raw})
                result.warnings.append(ProcessingWarning(code="INVALID_ROW", message=str(exc), severity=Severity.ERROR, row_number=source_row))
        for number, lines in grouped.items():
            document = JournalDocument(number=number, gregorian_date=min(x.gregorian_date for x in lines),
                jalali_date=min(x.jalali_date for x in lines), lines=lines)
            result.documents.append(document)
            if not document.is_balanced:
                result.warnings.append(ProcessingWarning(code="UNBALANCED_DOCUMENT",
                    message=f"سند تراز نیست؛ اختلاف: {document.total_debit - document.total_credit:,}",
                    document_number=number, severity=Severity.ERROR))
        result.documents.sort(key=lambda d: (d.gregorian_date, d.number))
        return result

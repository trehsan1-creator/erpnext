"""Canonical accounting domain models for Iranian ledgers."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReviewStatus(str, Enum):
    RESOLVED = "resolved"
    PENDING_AI = "pending_ai"
    HUMAN_REVIEW = "human_review"
    INVALID = "invalid"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Account(BaseModel):
    code: str
    name: str
    category: str | None = None
    level: str | None = None


class ProcessingWarning(BaseModel):
    code: str
    message: str
    severity: Severity = Severity.WARNING
    row_number: int | None = None
    document_number: str | None = None


class JournalLine(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    line_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    source_row: int
    document_number: str
    gregorian_date: date
    jalali_date: str
    description: str
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    account_code: str | None = None
    account_name: str | None = None
    counterparty: str | None = None
    reference: str | None = None
    status: ReviewStatus = ReviewStatus.RESOLVED
    confidence: float | None = Field(default=None, ge=0, le=1)
    review_note: str | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_amounts(self) -> "JournalLine":
        if self.debit < 0 or self.credit < 0:
            raise ValueError("مبالغ بدهکار و بستانکار نمی‌توانند منفی باشند")
        if self.debit and self.credit:
            raise ValueError("یک ردیف نمی‌تواند هم‌زمان بدهکار و بستانکار باشد")
        if not self.debit and not self.credit:
            raise ValueError("حداقل یکی از مبالغ بدهکار یا بستانکار باید غیرصفر باشد")
        return self


class JournalDocument(BaseModel):
    number: str
    gregorian_date: date
    jalali_date: str
    lines: list[JournalLine]

    @property
    def total_debit(self) -> Decimal:
        return sum((line.debit for line in self.lines), Decimal("0"))

    @property
    def total_credit(self) -> Decimal:
        return sum((line.credit for line in self.lines), Decimal("0"))

    @property
    def is_balanced(self) -> bool:
        return self.total_debit == self.total_credit


class PipelineResult(BaseModel):
    source_file: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    documents: list[JournalDocument] = Field(default_factory=list)
    warnings: list[ProcessingWarning] = Field(default_factory=list)
    invalid_rows: list[dict[str, Any]] = Field(default_factory=list)
    pending_task_ids: list[str] = Field(default_factory=list)

    @property
    def lines(self) -> list[JournalLine]:
        return [line for document in self.documents for line in document.lines]

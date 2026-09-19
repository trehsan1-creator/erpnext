"""Declarative, safe parser profiles generated through an offline AI handoff."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ColumnMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_number: str | None = None
    date: str
    description: str
    debit: str | None = None
    credit: str | None = None
    amount: str | None = None
    direction: str | None = None
    account_code: str | None = None
    account_name: str | None = None
    reference: str | None = None
    counterparty: str | None = None


class ParserProfile(BaseModel):
    """A data-only parser recipe. It can never execute AI-generated code."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    profile_name: str = Field(min_length=2, max_length=100)
    file_type: Literal["xlsx", "xls", "csv"]
    sheet_name: str | int = 0
    header_row: int = Field(default=1, ge=1, le=100)
    columns: ColumnMapping
    amount_strategy: Literal["separate_columns", "signed_amount", "amount_with_direction"]
    debit_when_positive: bool = True
    debit_direction_values: list[str] = Field(default_factory=lambda: ["بدهکار", "برداشت", "debit", "dr"])
    credit_direction_values: list[str] = Field(default_factory=lambda: ["بستانکار", "واریز", "credit", "cr"])
    date_system: Literal["auto", "jalali", "gregorian"] = "auto"
    day_first: bool = False
    thousands_separator: str | None = None
    decimal_separator: str = "."
    encoding: str = "utf-8-sig"
    confidence: float = Field(ge=0, le=1)
    reasoning: str = Field(min_length=5, max_length=1500)
    requires_human_review: bool = False
    signature_headers: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    usage_count: int = Field(default=0, ge=0)
    last_used_at: datetime | None = None

    @model_validator(mode="after")
    def validate_amount_columns(self) -> "ParserProfile":
        if self.amount_strategy == "separate_columns" and not (self.columns.debit and self.columns.credit):
            raise ValueError("برای separate_columns هر دو ستون debit و credit لازم است")
        if self.amount_strategy in {"signed_amount", "amount_with_direction"} and not self.columns.amount:
            raise ValueError("برای این روش مبلغ، ستون amount لازم است")
        if self.amount_strategy == "amount_with_direction" and not self.columns.direction:
            raise ValueError("برای amount_with_direction ستون direction لازم است")
        return self


class ParserConfigAIResponse(BaseModel):
    """Envelope returned by an external AI before becoming a persisted profile."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    profile_name: str = Field(min_length=2, max_length=100)
    file_type: Literal["xlsx", "xls", "csv"]
    sheet_name: str | int = 0
    header_row: int = Field(ge=1, le=100)
    columns: ColumnMapping
    amount_strategy: Literal["separate_columns", "signed_amount", "amount_with_direction"]
    debit_when_positive: bool = True
    debit_direction_values: list[str] = Field(default_factory=lambda: ["بدهکار", "برداشت", "debit", "dr"])
    credit_direction_values: list[str] = Field(default_factory=lambda: ["بستانکار", "واریز", "credit", "cr"])
    date_system: Literal["auto", "jalali", "gregorian"] = "auto"
    day_first: bool = False
    thousands_separator: str | None = None
    decimal_separator: str = "."
    encoding: str = "utf-8-sig"
    confidence: float = Field(ge=0, le=1)
    reasoning: str = Field(min_length=5, max_length=1500)
    requires_human_review: bool = False

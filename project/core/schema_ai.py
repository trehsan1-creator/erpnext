"""Strict schemas for responses received from any external AI."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class AccountClassificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    selected_account_code: str
    selected_account_name: str
    category: Literal["دارایی", "بدهی", "سرمایه", "درآمد", "هزینه", "انتظامی", "نامشخص"]
    confidence: float = Field(ge=0, le=1)
    reasoning: str = Field(min_length=5, max_length=1000)
    requires_human_review: bool = False


class AmbiguousTransactionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    normalized_description: str = Field(min_length=2)
    transaction_type: Literal[
        "خرید", "فروش", "دریافت", "پرداخت", "هزینه", "درآمد", "انتقال", "حقوق", "مالیات", "نامشخص"
    ]
    suggested_account_code: str | None = None
    suggested_account_name: str | None = None
    confidence: float = Field(ge=0, le=1)
    reasoning: str = Field(min_length=5, max_length=1000)
    requires_human_review: bool = False


AI_RESPONSE_SCHEMAS: dict[str, type[BaseModel]] = {
    "classify_account": AccountClassificationResponse,
    "resolve_ambiguous_transaction": AmbiguousTransactionResponse,
}

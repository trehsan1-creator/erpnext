"""Declarative human-in-the-loop tasks and validated answers."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HumanTaskStatus(str, Enum):
    PENDING = "pending"
    RESOLVED = "resolved"


class HumanFieldOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str
    label: str


class HumanField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,49}$")
    label: str = Field(min_length=2, max_length=150)
    field_type: Literal["text", "textarea", "number", "date", "select", "boolean"]
    required: bool = True
    help_text: str | None = Field(default=None, max_length=500)
    placeholder: str | None = Field(default=None, max_length=200)
    default: str | float | bool | None = None
    options: list[HumanFieldOption] = Field(default_factory=list, max_length=500)
    minimum: float | None = None
    maximum: float | None = None

    @model_validator(mode="after")
    def validate_options(self) -> "HumanField":
        if self.field_type == "select" and not self.options:
            raise ValueError("فیلد select باید حداقل یک گزینه داشته باشد")
        return self


class HumanTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    task_type: Literal["transaction_review", "document_review", "data_completion"]
    title: str
    instructions: str
    reason: str
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    status: HumanTaskStatus = HumanTaskStatus.PENDING
    fields: list[HumanField] = Field(min_length=1, max_length=20)
    context: dict[str, Any] = Field(default_factory=dict)
    answers: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None

    def validate_answers(self, answers: dict[str, Any]) -> dict[str, Any]:
        unknown = set(answers) - {field.key for field in self.fields}
        if unknown:
            raise ValueError("فیلدهای ناشناخته: " + "، ".join(sorted(unknown)))
        cleaned: dict[str, Any] = {}
        for field in self.fields:
            value = answers.get(field.key, field.default)
            if field.required and (value is None or value == ""):
                raise ValueError(f"فیلد «{field.label}» الزامی است")
            if value is None or value == "":
                cleaned[field.key] = value
                continue
            if field.field_type == "select":
                allowed = {option.value for option in field.options}
                if str(value) not in allowed:
                    raise ValueError(f"مقدار فیلد «{field.label}» مجاز نیست")
                value = str(value)
            elif field.field_type == "number":
                value = float(value)
                if field.minimum is not None and value < field.minimum:
                    raise ValueError(f"مقدار «{field.label}» کمتر از حد مجاز است")
                if field.maximum is not None and value > field.maximum:
                    raise ValueError(f"مقدار «{field.label}» بیشتر از حد مجاز است")
            elif field.field_type == "boolean":
                value = bool(value)
            else:
                value = str(value).strip()
            cleaned[field.key] = value
        return cleaned

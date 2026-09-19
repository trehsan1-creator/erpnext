"""Universal recovery contracts for operations the agent cannot safely finish."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.human_tasks import HumanField


SourceStage = Literal[
    "file_read", "parser", "normalization", "account_mapping", "validation",
    "reporting", "erpnext_sync", "workflow", "configuration", "unknown"
]


class BlockerStatus(str, Enum):
    PENDING_AI = "pending_ai"
    PENDING_HUMAN = "pending_human"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class Blocker(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blocker_id: str
    source_stage: SourceStage
    operation: str
    error_code: str
    title: str
    message: str
    context: dict[str, Any] = Field(default_factory=dict)
    safe_capabilities: list[str] = Field(default_factory=list)
    status: BlockerStatus = BlockerStatus.PENDING_AI
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attempts: int = 0
    source_file: str | None = None


class ReusableRuleProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_type: Literal["column_mapping", "account_mapping", "value_normalization", "validation_exception"]
    match_conditions: dict[str, str | int | float | bool]
    output_values: dict[str, str | int | float | bool]
    explanation: str = Field(min_length=5, max_length=1000)


class RecoveryAIResponse(BaseModel):
    """Provider-neutral response. It describes recovery; it cannot execute code."""

    model_config = ConfigDict(extra="forbid")
    task_id: str
    diagnosis: str = Field(min_length=5, max_length=2000)
    resolution_type: Literal[
        "provide_values", "create_safe_rule", "request_human", "manual_action", "not_safely_resolvable"
    ]
    proposed_values: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    human_title: str | None = Field(default=None, max_length=150)
    human_instructions: str | None = Field(default=None, max_length=1000)
    human_fields: list[HumanField] = Field(default_factory=list, max_length=20)
    reusable_rule: ReusableRuleProposal | None = None
    confidence: float = Field(ge=0, le=1)
    reasoning: str = Field(min_length=5, max_length=2000)
    requires_approval: bool = True

    @model_validator(mode="after")
    def validate_resolution(self) -> "RecoveryAIResponse":
        if self.resolution_type == "request_human" and not self.human_fields:
            raise ValueError("برای request_human حداقل یک human_field لازم است")
        if self.resolution_type == "create_safe_rule" and not self.reusable_rule:
            raise ValueError("برای create_safe_rule پیشنهاد reusable_rule لازم است")
        # Generic recovery is never allowed to silently mutate accounting records.
        if self.confidence < 0.9:
            self.requires_approval = True
        return self

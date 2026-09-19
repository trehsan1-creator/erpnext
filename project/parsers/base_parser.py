"""Base parser and deterministic accounting rules."""
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from core.models import PipelineResult


class BaseParser(ABC):
    def __init__(self, accounts: dict[str, tuple[str, str]] | None = None) -> None:
        self.accounts = accounts or {
            "بانک": ("110101", "بانک‌ها"), "حقوق": ("610201", "هزینه حقوق و دستمزد"),
            "اجاره": ("610101", "هزینه اجاره"), "مالیات": ("210301", "مالیات پرداختنی"),
            "فروش": ("410101", "فروش کالا و خدمات"), "خرید": ("510101", "خرید کالا و خدمات"),
        }

    @abstractmethod
    def parse(self, path: Path) -> PipelineResult:
        raise NotImplementedError

    def classify_deterministically(self, description: str) -> tuple[str, str] | None:
        normalized = description.casefold()
        matches = [account for keyword, account in self.accounts.items() if keyword in normalized]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def first_value(row: dict[str, Any], names: tuple[str, ...]) -> Any:
        for name in names:
            if name in row and row[name] is not None:
                return row[name]
        return None

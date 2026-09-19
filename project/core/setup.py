"""First-run company setup and Iranian chart-of-accounts templates."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.dates import parse_accounting_date


class ChartAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    name: str
    parent_code: str | None = None
    level: Literal["group", "general", "subsidiary"]
    nature: Literal["debit", "credit"]
    account_type: Literal[
        "asset", "liability", "equity", "revenue", "cost", "expense", "tax", "off_balance"
    ]
    is_group: bool = False


class CompanySetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    legal_name: str = Field(min_length=2, max_length=200)
    economic_name: str | None = Field(default=None, max_length=200)
    national_id: str | None = Field(default=None, max_length=20)
    registration_number: str | None = Field(default=None, max_length=30)
    activity_type: Literal["service", "trading", "general"]
    fiscal_year_title: str = Field(min_length=2, max_length=100)
    fiscal_year_start: str
    fiscal_year_end: str
    base_currency: Literal["IRR", "IRT"] = "IRR"
    chart_template: Literal["service", "trading", "general"]

    @model_validator(mode="after")
    def validate_period(self) -> "CompanySetupRequest":
        start, _ = parse_accounting_date(self.fiscal_year_start)
        end, _ = parse_accounting_date(self.fiscal_year_end)
        if end <= start:
            raise ValueError("پایان سال مالی باید بعد از شروع آن باشد")
        return self


class CompanyProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: str
    legal_name: str
    economic_name: str | None = None
    national_id: str | None = None
    registration_number: str | None = None
    activity_type: Literal["service", "trading", "general"]
    fiscal_year_title: str
    fiscal_year_start: str
    fiscal_year_end: str
    base_currency: Literal["IRR", "IRT"]
    chart_template: str
    initialized_at: datetime


BASE_CHART: list[ChartAccount] = [
    ChartAccount(code="1", name="دارایی‌ها", level="group", nature="debit", account_type="asset", is_group=True),
    ChartAccount(code="11", name="دارایی‌های جاری", parent_code="1", level="group", nature="debit", account_type="asset", is_group=True),
    ChartAccount(code="1101", name="موجودی نقد و بانک", parent_code="11", level="general", nature="debit", account_type="asset", is_group=True),
    ChartAccount(code="110101", name="صندوق", parent_code="1101", level="subsidiary", nature="debit", account_type="asset"),
    ChartAccount(code="110102", name="بانک‌ها", parent_code="1101", level="subsidiary", nature="debit", account_type="asset"),
    ChartAccount(code="110103", name="تنخواه‌گردان", parent_code="1101", level="subsidiary", nature="debit", account_type="asset"),
    ChartAccount(code="1102", name="سرمایه‌گذاری‌های کوتاه‌مدت", parent_code="11", level="general", nature="debit", account_type="asset"),
    ChartAccount(code="1201", name="حساب‌ها و اسناد دریافتنی", parent_code="11", level="general", nature="debit", account_type="asset", is_group=True),
    ChartAccount(code="120101", name="حساب‌های دریافتنی تجاری", parent_code="1201", level="subsidiary", nature="debit", account_type="asset"),
    ChartAccount(code="120102", name="اسناد دریافتنی", parent_code="1201", level="subsidiary", nature="debit", account_type="asset"),
    ChartAccount(code="120103", name="ذخیره مطالبات مشکوک‌الوصول", parent_code="1201", level="subsidiary", nature="credit", account_type="asset"),
    ChartAccount(code="1301", name="موجودی مواد و کالا", parent_code="11", level="general", nature="debit", account_type="asset"),
    ChartAccount(code="1401", name="پیش‌پرداخت‌ها", parent_code="11", level="general", nature="debit", account_type="asset"),
    ChartAccount(code="1402", name="سپرده‌ها و ودایع کوتاه‌مدت", parent_code="11", level="general", nature="debit", account_type="asset"),
    ChartAccount(code="15", name="دارایی‌های غیرجاری", parent_code="1", level="group", nature="debit", account_type="asset", is_group=True),
    ChartAccount(code="1501", name="دارایی‌های ثابت مشهود", parent_code="15", level="general", nature="debit", account_type="asset", is_group=True),
    ChartAccount(code="150101", name="زمین", parent_code="1501", level="subsidiary", nature="debit", account_type="asset"),
    ChartAccount(code="150102", name="ساختمان", parent_code="1501", level="subsidiary", nature="debit", account_type="asset"),
    ChartAccount(code="150103", name="وسایل نقلیه", parent_code="1501", level="subsidiary", nature="debit", account_type="asset"),
    ChartAccount(code="150104", name="اثاثه و تجهیزات", parent_code="1501", level="subsidiary", nature="debit", account_type="asset"),
    ChartAccount(code="1502", name="استهلاک انباشته", parent_code="15", level="general", nature="credit", account_type="asset"),
    ChartAccount(code="2", name="بدهی‌ها", level="group", nature="credit", account_type="liability", is_group=True),
    ChartAccount(code="21", name="بدهی‌های جاری", parent_code="2", level="group", nature="credit", account_type="liability", is_group=True),
    ChartAccount(code="2101", name="حساب‌ها و اسناد پرداختنی", parent_code="21", level="general", nature="credit", account_type="liability", is_group=True),
    ChartAccount(code="210101", name="حساب‌های پرداختنی تجاری", parent_code="2101", level="subsidiary", nature="credit", account_type="liability"),
    ChartAccount(code="210102", name="اسناد پرداختنی", parent_code="2101", level="subsidiary", nature="credit", account_type="liability"),
    ChartAccount(code="2102", name="مالیات و عوارض پرداختنی", parent_code="21", level="general", nature="credit", account_type="tax", is_group=True),
    ChartAccount(code="210201", name="مالیات بر ارزش افزوده پرداختنی", parent_code="2102", level="subsidiary", nature="credit", account_type="tax"),
    ChartAccount(code="210202", name="مالیات تکلیفی پرداختنی", parent_code="2102", level="subsidiary", nature="credit", account_type="tax"),
    ChartAccount(code="210203", name="مالیات عملکرد پرداختنی", parent_code="2102", level="subsidiary", nature="credit", account_type="tax"),
    ChartAccount(code="2103", name="حقوق و مزایای پرداختنی", parent_code="21", level="general", nature="credit", account_type="liability"),
    ChartAccount(code="2104", name="بیمه پرداختنی", parent_code="21", level="general", nature="credit", account_type="liability"),
    ChartAccount(code="2105", name="پیش‌دریافت‌ها", parent_code="21", level="general", nature="credit", account_type="liability"),
    ChartAccount(code="22", name="بدهی‌های غیرجاری", parent_code="2", level="group", nature="credit", account_type="liability", is_group=True),
    ChartAccount(code="2201", name="تسهیلات مالی بلندمدت", parent_code="22", level="general", nature="credit", account_type="liability"),
    ChartAccount(code="3", name="حقوق مالکانه", level="group", nature="credit", account_type="equity", is_group=True),
    ChartAccount(code="3101", name="سرمایه", parent_code="3", level="general", nature="credit", account_type="equity"),
    ChartAccount(code="3102", name="اندوخته قانونی", parent_code="3", level="general", nature="credit", account_type="equity"),
    ChartAccount(code="3103", name="سود و زیان انباشته", parent_code="3", level="general", nature="credit", account_type="equity"),
    ChartAccount(code="3104", name="جاری شرکا و سهامداران", parent_code="3", level="general", nature="credit", account_type="equity"),
    ChartAccount(code="4", name="درآمدها", level="group", nature="credit", account_type="revenue", is_group=True),
    ChartAccount(code="4101", name="درآمد فروش کالا", parent_code="4", level="general", nature="credit", account_type="revenue"),
    ChartAccount(code="4102", name="درآمد ارائه خدمات", parent_code="4", level="general", nature="credit", account_type="revenue"),
    ChartAccount(code="4103", name="برگشت از فروش و تخفیفات", parent_code="4", level="general", nature="debit", account_type="revenue"),
    ChartAccount(code="4201", name="سایر درآمدهای عملیاتی", parent_code="4", level="general", nature="credit", account_type="revenue"),
    ChartAccount(code="4202", name="درآمدهای غیرعملیاتی", parent_code="4", level="general", nature="credit", account_type="revenue"),
    ChartAccount(code="5", name="بهای تمام‌شده", level="group", nature="debit", account_type="cost", is_group=True),
    ChartAccount(code="5101", name="بهای تمام‌شده کالای فروش‌رفته", parent_code="5", level="general", nature="debit", account_type="cost"),
    ChartAccount(code="5102", name="هزینه مستقیم ارائه خدمات", parent_code="5", level="general", nature="debit", account_type="cost"),
    ChartAccount(code="6", name="هزینه‌ها", level="group", nature="debit", account_type="expense", is_group=True),
    ChartAccount(code="6101", name="هزینه‌های اداری و عمومی", parent_code="6", level="general", nature="debit", account_type="expense", is_group=True),
    ChartAccount(code="610101", name="هزینه حقوق و دستمزد", parent_code="6101", level="subsidiary", nature="debit", account_type="expense"),
    ChartAccount(code="610102", name="هزینه اجاره", parent_code="6101", level="subsidiary", nature="debit", account_type="expense"),
    ChartAccount(code="610103", name="هزینه آب، برق، گاز و تلفن", parent_code="6101", level="subsidiary", nature="debit", account_type="expense"),
    ChartAccount(code="610104", name="هزینه ملزومات و نوشت‌افزار", parent_code="6101", level="subsidiary", nature="debit", account_type="expense"),
    ChartAccount(code="610105", name="هزینه تعمیر و نگهداری", parent_code="6101", level="subsidiary", nature="debit", account_type="expense"),
    ChartAccount(code="610106", name="هزینه استهلاک", parent_code="6101", level="subsidiary", nature="debit", account_type="expense"),
    ChartAccount(code="6201", name="هزینه‌های فروش و بازاریابی", parent_code="6", level="general", nature="debit", account_type="expense"),
    ChartAccount(code="6301", name="هزینه‌های مالی", parent_code="6", level="general", nature="debit", account_type="expense"),
    ChartAccount(code="6401", name="سایر هزینه‌های غیرعملیاتی", parent_code="6", level="general", nature="debit", account_type="expense"),
    ChartAccount(code="7", name="حساب‌های مالیاتی", level="group", nature="debit", account_type="tax", is_group=True),
    ChartAccount(code="7101", name="اعتبار مالیات بر ارزش افزوده خرید", parent_code="7", level="general", nature="debit", account_type="tax"),
    ChartAccount(code="7102", name="هزینه مالیات بر درآمد", parent_code="7", level="general", nature="debit", account_type="tax"),
    ChartAccount(code="9", name="حساب‌های انتظامی", level="group", nature="debit", account_type="off_balance", is_group=True),
    ChartAccount(code="9101", name="حساب‌های انتظامی به نفع شرکت", parent_code="9", level="general", nature="debit", account_type="off_balance"),
    ChartAccount(code="9201", name="طرف حساب‌های انتظامی", parent_code="9", level="general", nature="credit", account_type="off_balance"),
]


def chart_for(template: str) -> list[ChartAccount]:
    excluded: set[str] = set()
    if template == "service":
        excluded = {"1301", "4101", "5101"}
    elif template == "trading":
        excluded = {"4102", "5102"}
    return [account.model_copy(deep=True) for account in BASE_CHART if account.code not in excluded]


class SetupStore:
    def __init__(self, data_root: Path) -> None:
        self.root = data_root / "system"
        self.profile_path = self.root / "company.json"
        self.accounts_path = self.root / "chart_of_accounts.json"
        self.root.mkdir(parents=True, exist_ok=True)

    def is_initialized(self) -> bool:
        return self.profile_path.exists() and self.accounts_path.exists()

    def initialize(self, request: CompanySetupRequest) -> CompanyProfile:
        if self.is_initialized():
            raise ValueError("سیستم قبلاً راه‌اندازی شده است؛ برای شروع مجدد ابتدا بازنشانی کنید")
        profile = CompanyProfile(
            company_id=uuid4().hex, initialized_at=datetime.now(timezone.utc),
            **request.model_dump(),
        )
        accounts = chart_for(request.chart_template)
        self.profile_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        self.accounts_path.write_text(
            json.dumps([item.model_dump(mode="json") for item in accounts], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return profile

    def profile(self) -> CompanyProfile | None:
        if not self.profile_path.exists():
            return None
        return CompanyProfile.model_validate_json(self.profile_path.read_text(encoding="utf-8"))

    def accounts(self) -> list[ChartAccount]:
        if not self.accounts_path.exists():
            return []
        return [ChartAccount.model_validate(item) for item in json.loads(self.accounts_path.read_text(encoding="utf-8"))]

    def reset(self) -> None:
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)

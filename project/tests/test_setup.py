from pathlib import Path

from core.setup import CompanySetupRequest, SetupStore, chart_for


def test_first_run_creates_company_fiscal_year_and_chart(tmp_path: Path) -> None:
    store = SetupStore(tmp_path)
    assert not store.is_initialized()
    profile = store.initialize(CompanySetupRequest(
        legal_name="شرکت خدمات حسابداری نمونه",
        activity_type="service",
        fiscal_year_title="سال مالی ۱۴۰۳",
        fiscal_year_start="1403/01/01",
        fiscal_year_end="1403/12/29",
        chart_template="service",
        base_currency="IRR",
    ))
    assert store.is_initialized()
    assert profile.legal_name == "شرکت خدمات حسابداری نمونه"
    accounts = store.accounts()
    assert len(accounts) == len(chart_for("service"))
    assert any(item.code == "110102" and item.name == "بانک‌ها" for item in accounts)
    assert not any(item.code == "1301" for item in accounts)
    store.reset()
    assert not store.is_initialized()

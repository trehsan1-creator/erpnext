#!/usr/bin/env python3
"""Run or resume the complete offline accounting pipeline."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from ai_bridge.client import OfflineAIBridge
from exporters.excel_report import PersianExcelReport
from parsers.excel_parser import ExcelParser

ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="پردازش آفلاین فایل حسابداری ایران")
    parser.add_argument("input", nargs="?", type=Path, default=ROOT / "examples" / "sample_input.xlsx")
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "گزارش_حسابداری.xlsx")
    args = parser.parse_args()
    accounting_parser = ExcelParser()
    result = accounting_parser.parse(args.input)
    bridge = OfflineAIBridge(ROOT, accounting_parser.accounts)
    bridge.apply_responses(result)
    tasks = bridge.create_tasks(result)
    report = PersianExcelReport(ROOT).export(result, args.output)
    state = ROOT / "output" / "last_run.json"
    state.write_text(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ گزارش ساخته شد: {report}")
    print(f"✓ اسناد: {len(result.documents)} | ردیف‌ها: {len(result.lines)} | هشدارها: {len(result.warnings)}")
    if result.pending_task_ids:
        print(f"⚠ {len(result.pending_task_ids)} وظیفه هوش مصنوعی در ai_tasks/pending موجود است.")
        print("  فایل *.prompt.md را به AI بدهید، پاسخ JSON را کنار آن ذخیره و همین دستور را دوباره اجرا کنید.")
    else:
        print("✓ هیچ تصمیم هوش مصنوعی معلقی وجود ندارد.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

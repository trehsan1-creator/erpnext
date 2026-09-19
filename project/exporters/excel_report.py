"""Professional Persian accounting workbook built directly with openpyxl."""
from __future__ import annotations
import json
from copy import copy
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from core.models import PipelineResult, ReviewStatus


class PersianExcelReport:
    MONEY_FORMAT = '#,##0;[Red](#,##0);-'

    def __init__(self, project_root: Path) -> None:
        style_path = project_root / "exporters" / "templates" / "default.json"
        self.theme: dict[str, str] = json.loads(style_path.read_text(encoding="utf-8"))
        self.font_name = self.theme["font"]

    def export(self, result: PipelineResult, output: Path) -> Path:
        output.parent.mkdir(parents=True, exist_ok=True)
        workbook = Workbook()
        summary = workbook.active
        summary.title = "خلاصه مدیریتی"
        self._summary(summary, result)
        self._journal(workbook.create_sheet("دفتر روزنامه"), result)
        self._trial_balance(workbook.create_sheet("تراز آزمایشی"), result)
        self._account_ledger(workbook.create_sheet("گردش حساب‌ها"), result)
        self._monthly_analysis(workbook.create_sheet("تحلیل ماهانه"), result)
        self._documents(workbook.create_sheet("کنترل اسناد"), result)
        self._review_queue(workbook.create_sheet("کارتابل رسیدگی"), result)
        self._warnings(workbook.create_sheet("هشدارها"), result)
        self._invalid(workbook.create_sheet("ردیف‌های نامعتبر"), result)
        for sheet in workbook.worksheets:
            self._finalize(sheet)
        workbook.save(output)
        return output

    def _summary(self, ws: Any, result: PipelineResult) -> None:
        ws.merge_cells("A1:F2")
        ws["A1"] = "داشبورد کنترل حسابداری"
        ws["A1"].font = Font(name=self.font_name, size=20, bold=True, color="FFFFFF")
        ws["A1"].fill = PatternFill("solid", fgColor=self.theme["header_fill"])
        ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
        lines = result.lines
        total_debit = sum((x.debit for x in lines), Decimal(0))
        total_credit = sum((x.credit for x in lines), Decimal(0))
        pending = sum(x.status != ReviewStatus.RESOLVED for x in lines)
        cards = [
            ("تعداد اسناد", len(result.documents)), ("تعداد ردیف‌ها", len(lines)),
            ("جمع بدهکار (ریال)", total_debit), ("جمع بستانکار (ریال)", total_credit),
            ("اختلاف تراز (ریال)", total_debit-total_credit), ("نیازمند بررسی", pending),
            ("هشدارها", len(result.warnings)), ("ردیف نامعتبر", len(result.invalid_rows)),
        ]
        for idx, (label, value) in enumerate(cards):
            row = 4 + (idx // 2) * 2
            col = 1 + (idx % 2) * 3
            ws.cell(row, col, label)
            ws.cell(row, col).font = Font(name=self.font_name, bold=True, color="FFFFFF")
            ws.cell(row, col).fill = PatternFill("solid", fgColor=self.theme["header_fill"])
            ws.merge_cells(start_row=row, start_column=col, end_row=row, end_column=col+1)
            ws.cell(row+1, col, float(value) if isinstance(value, Decimal) else value)
            ws.cell(row+1, col).font = Font(name=self.font_name, size=15, bold=True, color=self.theme["header_fill"])
            ws.cell(row+1, col).fill = PatternFill("solid", fgColor=self.theme["accent_fill"])
            ws.cell(row+1, col).number_format = self.MONEY_FORMAT
            ws.merge_cells(start_row=row+1, start_column=col, end_row=row+1, end_column=col+1)
        ws["A14"] = "وضعیت"
        ws["B14"] = "تعداد"
        status_data = [("حل‌شده", sum(x.status == ReviewStatus.RESOLVED for x in lines)),
                       ("در انتظار AI", sum(x.status == ReviewStatus.PENDING_AI for x in lines)),
                       ("بررسی انسانی", sum(x.status == ReviewStatus.HUMAN_REVIEW for x in lines))]
        for row, item in enumerate(status_data, 15):
            ws.cell(row, 1, item[0]); ws.cell(row, 2, item[1])
        self._style_header(ws, 14, 2)
        chart = BarChart(); chart.title = "وضعیت پردازش"; chart.legend = None
        chart.add_data(Reference(ws, min_col=2, min_row=14, max_row=17), titles_from_data=True)
        chart.set_categories(Reference(ws, min_col=1, min_row=15, max_row=17)); chart.height = 6; chart.width = 12
        ws.add_chart(chart, "D14")
        ws["A20"] = "تولید گزارش"
        ws["B20"] = result.generated_at.astimezone().strftime("%Y-%m-%d %H:%M")
        ws["A21"] = "فایل منبع"; ws["B21"] = result.source_file
        ws.freeze_panes = "A4"

    def _journal(self, ws: Any, result: PipelineResult) -> None:
        headers = ["ردیف", "شماره سند", "تاریخ شمسی", "تاریخ میلادی", "شرح", "کد حساب", "نام حساب",
                   "بدهکار (ریال)", "بستانکار (ریال)", "وضعیت", "اطمینان", "یادداشت بررسی", "ردیف منبع"]
        ws.append(headers)
        status_names = {"resolved": "حل‌شده", "pending_ai": "در انتظار AI", "human_review": "بررسی انسانی", "invalid": "نامعتبر"}
        for idx, line in enumerate(result.lines, 1):
            ws.append([idx, line.document_number, line.jalali_date, line.gregorian_date, line.description,
                line.account_code, line.account_name, float(line.debit), float(line.credit), status_names[line.status.value],
                line.confidence, line.review_note, line.source_row])
        self._style_header(ws, 1, len(headers)); ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
        ws.column_dimensions["D"].hidden = True
        for row in range(2, ws.max_row + 1):
            ws.cell(row, 4).number_format = "yyyy-mm-dd"
            for col in (8, 9): ws.cell(row, col).number_format = self.MONEY_FORMAT
            ws.cell(row, 11).number_format = "0%"
        if ws.max_row > 1:
            table = Table(displayName="JournalTable", ref=f"A1:M{ws.max_row}")
            table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True, showFirstColumn=False, showLastColumn=False)
            ws.add_table(table)
            yellow = PatternFill("solid", fgColor=self.theme["warning_fill"])
            ws.conditional_formatting.add(f"A2:M{ws.max_row}", FormulaRule(formula=['$J2<>"حل‌شده"'], fill=yellow))

    def _trial_balance(self, ws: Any, result: PipelineResult) -> None:
        headers = ["ردیف", "کد حساب", "نام حساب", "گردش بدهکار", "گردش بستانکار",
                   "مانده بدهکار", "مانده بستانکار", "تعداد ردیف"]
        ws.append(headers)
        accounts: dict[tuple[str, str], dict[str, Any]] = {}
        for line in result.lines:
            key = (line.account_code or "نامشخص", line.account_name or "حساب تعیین‌نشده")
            item = accounts.setdefault(key, {"debit": Decimal("0"), "credit": Decimal("0"), "count": 0})
            item["debit"] += line.debit; item["credit"] += line.credit; item["count"] += 1
        for index, ((code, name), item) in enumerate(sorted(accounts.items()), 1):
            balance = item["debit"] - item["credit"]
            ws.append([index, code, name, float(item["debit"]), float(item["credit"]),
                       float(max(balance, Decimal("0"))), float(max(-balance, Decimal("0"))), item["count"]])
        total_row = ws.max_row + 1
        ws.cell(total_row, 3, "جمع کل")
        for column in range(4, 8):
            ws.cell(total_row, column, f"=SUM({get_column_letter(column)}2:{get_column_letter(column)}{total_row-1})")
            ws.cell(total_row, column).number_format = self.MONEY_FORMAT
        for cell in ws[total_row]:
            cell.font = Font(name=self.font_name, bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=self.theme["header_fill"])
        self._style_header(ws, 1, len(headers)); ws.freeze_panes = "A2"; ws.auto_filter.ref = f"A1:H{max(1,total_row-1)}"
        for row in range(2, total_row):
            for column in range(4, 8): ws.cell(row, column).number_format = self.MONEY_FORMAT

    def _account_ledger(self, ws: Any, result: PipelineResult) -> None:
        headers = ["ردیف", "کد حساب", "نام حساب", "تاریخ شمسی", "شماره سند", "شرح",
                   "بدهکار", "بستانکار", "مانده جاری", "مرجع", "وضعیت"]
        ws.append(headers)
        lines = sorted(result.lines, key=lambda line: (
            line.account_code or "~", line.gregorian_date, line.document_number, line.source_row
        ))
        balances: dict[str, Decimal] = {}
        for index, line in enumerate(lines, 1):
            code = line.account_code or "نامشخص"
            balances[code] = balances.get(code, Decimal("0")) + line.debit - line.credit
            ws.append([index, code, line.account_name or "حساب تعیین‌نشده", line.jalali_date,
                       line.document_number, line.description, float(line.debit), float(line.credit),
                       float(balances[code]), line.reference, line.status.value])
        self._style_header(ws, 1, len(headers)); ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
        for row in range(2, ws.max_row + 1):
            for column in (7, 8, 9): ws.cell(row, column).number_format = self.MONEY_FORMAT
        if ws.max_row > 1:
            table = Table(displayName="AccountLedgerTable", ref=f"A1:K{ws.max_row}")
            table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
            ws.add_table(table)

    def _monthly_analysis(self, ws: Any, result: PipelineResult) -> None:
        headers = ["ماه شمسی", "تعداد اسناد", "تعداد ردیف", "گردش بدهکار", "گردش بستانکار",
                   "اختلاف", "موارد نیازمند بررسی"]
        ws.append(headers)
        months: dict[str, dict[str, Any]] = {}
        for document in result.documents:
            month = document.jalali_date[:7]
            item = months.setdefault(month, {"documents": set(), "lines": 0, "debit": Decimal("0"),
                                             "credit": Decimal("0"), "review": 0})
            item["documents"].add(document.number)
            for line in document.lines:
                item["lines"] += 1; item["debit"] += line.debit; item["credit"] += line.credit
                item["review"] += line.status != ReviewStatus.RESOLVED
        for month, item in sorted(months.items()):
            ws.append([month, len(item["documents"]), item["lines"], float(item["debit"]),
                       float(item["credit"]), float(item["debit"]-item["credit"]), item["review"]])
        self._style_header(ws, 1, len(headers)); ws.freeze_panes = "A2"
        for row in range(2, ws.max_row + 1):
            for column in (4, 5, 6): ws.cell(row, column).number_format = self.MONEY_FORMAT
        if ws.max_row > 1:
            chart = BarChart(); chart.title = "روند گردش ماهانه"; chart.height = 7; chart.width = 14
            chart.add_data(Reference(ws, min_col=4, max_col=5, min_row=1, max_row=ws.max_row), titles_from_data=True)
            chart.set_categories(Reference(ws, min_col=1, min_row=2, max_row=ws.max_row)); ws.add_chart(chart, "I2")

    def _review_queue(self, ws: Any, result: PipelineResult) -> None:
        headers = ["ردیف", "وضعیت", "شماره سند", "تاریخ", "شرح", "بدهکار", "بستانکار",
                   "کد پیشنهادی", "حساب پیشنهادی", "اطمینان", "دلیل بررسی"]
        ws.append(headers)
        pending = [line for line in result.lines if line.status != ReviewStatus.RESOLVED]
        for index, line in enumerate(pending, 1):
            ws.append([index, line.status.value, line.document_number, line.jalali_date, line.description,
                       float(line.debit), float(line.credit), line.account_code, line.account_name,
                       line.confidence, line.review_note])
        if not pending: ws.append([None, "resolved", None, None, "مورد بازی برای رسیدگی وجود ندارد"])
        self._style_header(ws, 1, len(headers)); ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
        for row in range(2, ws.max_row + 1):
            ws.cell(row, 6).number_format = self.MONEY_FORMAT; ws.cell(row, 7).number_format = self.MONEY_FORMAT
            ws.cell(row, 10).number_format = "0%"

    def _documents(self, ws: Any, result: PipelineResult) -> None:
        headers = ["شماره سند", "تاریخ شمسی", "تعداد ردیف", "جمع بدهکار", "جمع بستانکار", "اختلاف", "وضعیت تراز"]
        ws.append(headers)
        for doc in result.documents:
            ws.append([doc.number, doc.jalali_date, len(doc.lines), float(doc.total_debit), float(doc.total_credit),
                       float(doc.total_debit-doc.total_credit), "تراز" if doc.is_balanced else "نامتوازن"])
        self._style_header(ws, 1, len(headers)); ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
        for row in range(2, ws.max_row+1):
            for col in (4, 5, 6): ws.cell(row, col).number_format = self.MONEY_FORMAT
        if ws.max_row > 1:
            ws.conditional_formatting.add(f"A2:G{ws.max_row}", FormulaRule(formula=['$G2="نامتوازن"'], fill=PatternFill("solid", fgColor=self.theme["error_fill"])))

    def _warnings(self, ws: Any, result: PipelineResult) -> None:
        ws.append(["ردیف", "سطح", "کد", "پیام", "شماره سند", "ردیف منبع"])
        for idx, warning in enumerate(result.warnings, 1):
            ws.append([idx, warning.severity.value, warning.code, warning.message, warning.document_number, warning.row_number])
        if not result.warnings: ws.append([1, "info", "OK", "هشداری ثبت نشده است", None, None])
        self._style_header(ws, 1, 6); ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions

    def _invalid(self, ws: Any, result: PipelineResult) -> None:
        ws.append(["ردیف منبع", "خطا", "داده خام"])
        for row in result.invalid_rows:
            ws.append([row["source_row"], row["error"], json.dumps(row["raw_data"], ensure_ascii=False, default=str)])
        if not result.invalid_rows: ws.append([None, "ردیف نامعتبری ثبت نشده است", None])
        self._style_header(ws, 1, 3); ws.freeze_panes = "A2"

    def _style_header(self, ws: Any, row: int, columns: int) -> None:
        for col in range(1, columns+1):
            cell = ws.cell(row, col); cell.font = Font(name=self.font_name, bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=self.theme["header_fill"])
            cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[row].height = 28

    def _finalize(self, ws: Any) -> None:
        ws.sheet_view.rightToLeft = True
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0; ws.sheet_properties.outlinePr.summaryBelow = True
        ws.oddHeader.center.text = f"&B{ws.title}"
        ws.oddFooter.center.text = "صفحه &P از &N"; ws.oddFooter.right.text = "گزارش حسابداری محرمانه"
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        thin = Side(style="thin", color=self.theme["border_color"])
        for row in ws.iter_rows():
            for cell in row:
                font = copy(cell.font); font.name = self.font_name; cell.font = font
                alignment = copy(cell.alignment)
                alignment.vertical = "center"; alignment.readingOrder = 2
                alignment.wrap_text = cell.column in (4, 5, 12); cell.alignment = alignment
                if cell.value is not None: cell.border = Border(bottom=thin)
        for idx, column in enumerate(ws.columns, 1):
            values = [str(c.value) if c.value is not None else "" for c in column]
            width = min(max(max((len(v) for v in values), default=8) + 3, 10), 55)
            ws.column_dimensions[get_column_letter(idx)].width = width
        ws.sheet_view.showGridLines = False

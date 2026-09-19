"""Web control room for Agha — the offline Iranian accounting agent."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ai_bridge.client import OfflineAIBridge
from core.models import PipelineResult, ReviewStatus
from exporters.excel_report import PersianExcelReport
from parsers.excel_parser import ExcelParser

ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = Path(__file__).resolve().parent
RUNTIME = UI_ROOT / "runtime"
UPLOADS = RUNTIME / "uploads"
REPORTS = RUNTIME / "reports"
for folder in (UPLOADS, REPORTS):
    folder.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="آقا — عامل حسابداری", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=UI_ROOT / "static"), name="static")
lock = Lock()
state: dict[str, Any] = {"result": None, "input": None, "report": None, "display_name": None}


class AIAnswer(BaseModel):
    answer: dict[str, Any]


def _serialize(result: PipelineResult) -> dict[str, Any]:
    lines = result.lines
    debit = sum(float(line.debit) for line in lines)
    credit = sum(float(line.credit) for line in lines)
    pending = [line for line in lines if line.status == ReviewStatus.PENDING_AI]
    review = [line for line in lines if line.status == ReviewStatus.HUMAN_REVIEW]
    return {
        "source": Path(result.source_file).name,
        "documents": len(result.documents),
        "lines": len(lines),
        "debit": debit,
        "credit": credit,
        "balance": debit - credit,
        "warnings": len(result.warnings),
        "invalid": len(result.invalid_rows),
        "pending": len(pending),
        "review": len(review),
        "resolved": sum(line.status == ReviewStatus.RESOLVED for line in lines),
        "tasks": [
            {
                "task_id": f"TX-{line.line_id}",
                "description": line.description,
                "document": line.document_number,
                "date": line.jalali_date,
                "debit": float(line.debit),
                "credit": float(line.credit),
            }
            for line in pending
        ],
        "warnings_list": [
            {"code": item.code, "message": item.message, "severity": item.severity.value,
             "document": item.document_number, "row": item.row_number}
            for item in result.warnings
        ],
        "recent_lines": [
            {"document": line.document_number, "date": line.jalali_date, "description": line.description,
             "account": line.account_name or "در انتظار تشخیص", "debit": float(line.debit),
             "credit": float(line.credit), "status": line.status.value}
            for line in lines[:8]
        ],
    }


def _process(path: Path, display_name: str | None = None) -> dict[str, Any]:
    parser = ExcelParser()
    result = parser.parse(path)
    if display_name:
        result.source_file = display_name
    bridge = OfflineAIBridge(ROOT, parser.accounts)
    bridge.apply_responses(result)
    bridge.create_tasks(result)
    report = REPORTS / "گزارش_آقا.xlsx"
    PersianExcelReport(ROOT).export(result, report)
    state.update(result=result, input=path, report=report, display_name=display_name or path.name)
    return _serialize(result)


def _ensure_state() -> PipelineResult:
    result = state.get("result")
    if isinstance(result, PipelineResult):
        return result
    sample = ROOT / "examples" / "sample_input.xlsx"
    _process(sample)
    return state["result"]


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((UI_ROOT / "templates" / "index.html").read_text(encoding="utf-8"))


@app.get("/api/status")
def status() -> dict[str, Any]:
    with lock:
        return _serialize(_ensure_state())


@app.post("/api/process")
def process_file(file: UploadFile = File(...)) -> dict[str, Any]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".xlsx", ".xls", ".csv"}:
        raise HTTPException(400, "فقط فایل Excel یا CSV قابل پردازش است.")
    destination = UPLOADS / f"current{suffix}"
    with lock:
        for old in UPLOADS.glob("current.*"):
            old.unlink(missing_ok=True)
        with destination.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)
        try:
            return _process(destination, file.filename or destination.name)
        except Exception as exc:
            destination.unlink(missing_ok=True)
            raise HTTPException(422, f"پردازش فایل ممکن نشد: {exc}") from exc


@app.get("/api/report")
def download_report() -> FileResponse:
    with lock:
        _ensure_state()
        report: Path = state["report"]
    return FileResponse(report, filename="Agha-Accounting-Report.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/api/tasks/{task_id}/prompt")
def download_prompt(task_id: str) -> FileResponse:
    if not task_id.startswith("TX-") or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for char in task_id):
        raise HTTPException(400, "شناسه وظیفه نامعتبر است")
    path = ROOT / "ai_tasks" / "pending" / f"{task_id}.prompt.md"
    if not path.exists():
        raise HTTPException(404, "پرامپت پیدا نشد")
    return FileResponse(path, filename=f"{task_id}.prompt.md", media_type="text/markdown; charset=utf-8")


@app.post("/api/tasks/{task_id}/answer")
def submit_answer(task_id: str, payload: AIAnswer) -> dict[str, Any]:
    task_path = ROOT / "ai_tasks" / "pending" / f"{task_id}.task.json"
    if not task_path.exists():
        raise HTTPException(404, "وظیفه فعال پیدا نشد")
    response_path = ROOT / "ai_tasks" / "pending" / f"{task_id}.response.json"
    response_path.write_text(json.dumps(payload.answer, ensure_ascii=False, indent=2), encoding="utf-8")
    with lock:
        input_path: Path = state.get("input") or ROOT / "examples" / "sample_input.xlsx"
        data = _process(input_path, state.get("display_name"))
    return data

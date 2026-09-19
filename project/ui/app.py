"""Web control room for Agha — the offline Iranian accounting agent."""
from __future__ import annotations

import base64
import json
import os
import secrets
import shutil
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ai_bridge.client import OfflineAIBridge
from ai_bridge.parser_learning import ParserLearningBridge
from core.models import PipelineResult, ReviewStatus
from core.parser_config import ParserProfile
from exporters.excel_report import PersianExcelReport
from parsers.errors import UnsupportedFormatError
from parsers.excel_parser import ExcelParser
from parsers.profile_store import ParserProfileStore

ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ.get("AGHA_DATA_DIR", str(ROOT))).expanduser().resolve()
RUNTIME = DATA_ROOT / "ui-runtime"
UPLOADS = RUNTIME / "uploads"
REPORTS = RUNTIME / "reports"
for folder in (UPLOADS, REPORTS):
    folder.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="آقا — عامل حسابداری", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=UI_ROOT / "static"), name="static")
lock = Lock()


@app.middleware("http")
async def optional_basic_auth(request: Request, call_next: Any) -> Response:
    """Protect public deployments when AGHA_PASSWORD is configured."""
    password = os.environ.get("AGHA_PASSWORD", "")
    if not password or request.url.path == "/api/health":
        return await call_next(request)
    expected_user = os.environ.get("AGHA_USERNAME", "agha")
    authorization = request.headers.get("Authorization", "")
    try:
        scheme, encoded = authorization.split(" ", 1)
        username, supplied_password = base64.b64decode(encoded).decode("utf-8").split(":", 1)
        authenticated = scheme.lower() == "basic" and secrets.compare_digest(username, expected_user) \
            and secrets.compare_digest(supplied_password, password)
    except (ValueError, UnicodeDecodeError):
        authenticated = False
    if not authenticated:
        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Agha Accounting"'})
    return await call_next(request)
state: dict[str, Any] = {
    "result": None, "input": None, "report": None, "display_name": None,
    "active_profile": None, "parser_task": None,
}
profile_store = ParserProfileStore(DATA_ROOT)
parser_learning = ParserLearningBridge(ROOT, DATA_ROOT)


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
        "parser_profiles": profile_store.summary(),
        "active_profile": state.get("active_profile"),
        "recent_lines": [
            {"document": line.document_number, "date": line.jalali_date, "description": line.description,
             "account": line.account_name or "در انتظار تشخیص", "debit": float(line.debit),
             "credit": float(line.credit), "status": line.status.value}
            for line in lines[:8]
        ],
    }


def _process(path: Path, display_name: str | None = None,
             forced_profile: ParserProfile | None = None) -> dict[str, Any]:
    profile = forced_profile or profile_store.find_match(path)
    parser = ExcelParser(profile=profile)
    result = parser.parse(path)
    if display_name:
        result.source_file = display_name
    bridge = OfflineAIBridge(ROOT, parser.accounts, data_root=DATA_ROOT)
    bridge.apply_responses(result)
    bridge.create_tasks(result)
    report = REPORTS / "گزارش_آقا.xlsx"
    PersianExcelReport(ROOT).export(result, report)
    state.update(
        result=result, input=path, report=report, display_name=display_name or path.name,
        active_profile=profile.profile_name if profile else "Parser استاندارد آقا", parser_task=None,
    )
    return _serialize(result)


def _ensure_state() -> PipelineResult:
    result = state.get("result")
    if isinstance(result, PipelineResult):
        return result
    sample = ROOT / "examples" / "sample_input.xlsx"
    _process(sample)
    return state["result"]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "agha-accounting"}


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
        except UnsupportedFormatError as exc:
            task = parser_learning.create_task(destination, exc.reason)
            state.update(input=destination, display_name=file.filename or destination.name, parser_task=task)
            return {
                "needs_parser": True,
                "message": "قالب فایل برای آقا ناشناخته است؛ مأموریت ساخت Parser آماده شد.",
                "parser_task": task,
                "parser_profiles": profile_store.summary(),
            }
        except Exception as exc:
            destination.unlink(missing_ok=True)
            raise HTTPException(422, f"پردازش فایل ممکن نشد: {exc}") from exc


@app.get("/api/parser-profiles")
def parser_profiles() -> dict[str, Any]:
    return {"profiles": profile_store.summary()}


@app.get("/api/parser-tasks/{task_id}/prompt")
def download_parser_prompt(task_id: str) -> FileResponse:
    if not task_id.startswith("PARSER-") or not task_id.replace("PARSER-", "").isalnum():
        raise HTTPException(400, "شناسه مأموریت Parser نامعتبر است")
    path = DATA_ROOT / "parser_tasks" / "pending" / f"{task_id}.prompt.md"
    if not path.exists():
        raise HTTPException(404, "پرامپت ساخت Parser پیدا نشد")
    return FileResponse(path, filename=f"{task_id}.prompt.md", media_type="text/markdown; charset=utf-8")


@app.post("/api/parser-tasks/{task_id}/config")
def submit_parser_config(task_id: str, payload: AIAnswer) -> dict[str, Any]:
    with lock:
        source = state.get("input")
        if not isinstance(source, Path) or not source.exists():
            raise HTTPException(409, "فایل منبع این مأموریت دیگر در دسترس نیست")
        try:
            profile = parser_learning.accept_config(task_id, payload.answer, source, persist=False)
            result = _process(source, state.get("display_name"), forced_profile=profile)
            parser_learning.complete_config(task_id, payload.answer, profile, source.name)
            result["parser_profiles"] = profile_store.summary()
            return result
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc


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
    path = DATA_ROOT / "ai_tasks" / "pending" / f"{task_id}.prompt.md"
    if not path.exists():
        raise HTTPException(404, "پرامپت پیدا نشد")
    return FileResponse(path, filename=f"{task_id}.prompt.md", media_type="text/markdown; charset=utf-8")


@app.post("/api/tasks/{task_id}/answer")
def submit_answer(task_id: str, payload: AIAnswer) -> dict[str, Any]:
    task_path = DATA_ROOT / "ai_tasks" / "pending" / f"{task_id}.task.json"
    if not task_path.exists():
        raise HTTPException(404, "وظیفه فعال پیدا نشد")
    response_path = DATA_ROOT / "ai_tasks" / "pending" / f"{task_id}.response.json"
    response_path.write_text(json.dumps(payload.answer, ensure_ascii=False, indent=2), encoding="utf-8")
    with lock:
        input_path: Path = state.get("input") or ROOT / "examples" / "sample_input.xlsx"
        data = _process(input_path, state.get("display_name"))
    return data

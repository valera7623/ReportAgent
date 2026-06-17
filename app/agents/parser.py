"""Agent 1: validate input and normalize data to a unified DataFrame."""

from __future__ import annotations

import os
import re
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import pandas as pd

from app.models.schemas import AgentError
from app.self_healing.healing_decorator import with_self_healing
from app.self_healing.fix_executor import get_active_fix_context
from app.utils.logger import get_logger
from app.utils.metrics import track_agent_metrics

logger = get_logger("agent_parser", "log_parser.log")

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/storage/uploads"))
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "25"))
GOOGLE_SHEETS_PATTERN = re.compile(
    r"https?://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)"
)
GOOGLE_SA_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "./secrets/google-sa.json").strip()


def _extract_sheet_id(url: str) -> str:
    match = GOOGLE_SHEETS_PATTERN.search(url)
    if not match:
        raise AgentError(
            "Invalid Google Sheets URL. Use a public link like "
            "https://docs.google.com/spreadsheets/d/SHEET_ID/edit",
            agent="parser",
        )
    return match.group(1)


def _export_url(sheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"


def _service_account_email() -> str | None:
    sa_path = Path(GOOGLE_SA_JSON)
    if not sa_path.is_file():
        return None
    try:
        import json

        payload = json.loads(sa_path.read_text(encoding="utf-8"))
        return payload.get("client_email")
    except Exception:
        return None


def _sheet_access_hint() -> str:
    hint = (
        "Google Sheet is not publicly accessible. "
        "Set sharing to 'Anyone with the link can view'."
    )
    sa_email = _service_account_email()
    if sa_email:
        hint += f" Or share the sheet with the service account: {sa_email}"
    return hint


def _fetch_google_sheet_via_service_account(sheet_id: str) -> pd.DataFrame:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    sa_path = Path(GOOGLE_SA_JSON)
    if not sa_path.is_file():
        raise AgentError(_sheet_access_hint(), agent="parser")

    creds = service_account.Credentials.from_service_account_file(
        str(sa_path),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    try:
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range="A:ZZ")
            .execute()
        )
    except Exception as exc:
        raise AgentError(
            f"{_sheet_access_hint()} ({exc})",
            agent="parser",
        ) from exc

    values = result.get("values", [])
    if not values:
        raise AgentError("The dataset is empty. Add at least one row of data.", agent="parser")

    if len(values) == 1:
        df = pd.DataFrame(values)
    else:
        header, *rows = values
        width = len(header)
        normalized_rows = [row + [""] * (width - len(row)) for row in rows]
        df = pd.DataFrame(normalized_rows, columns=header)

    return df


def _validate_email_optional(email: str | None) -> None:
    if email is None or not email.strip():
        return
    if "@" not in email:
        raise AgentError("Invalid email format.", agent="parser")


def _file_starts_with(file_path: Path, magic: bytes) -> bool:
    with file_path.open("rb") as fh:
        return fh.read(len(magic)) == magic


def _read_csv_robust(source: Path | BytesIO, *, label: str = "file") -> pd.DataFrame:
    """Read CSV with common encodings (UTF-8, Windows-1251) and Excel RU separators."""
    encodings = ("utf-8-sig", "utf-8", "cp1251", "latin-1")
    last_error: Exception | None = None

    for encoding in encodings:
        for sep in (None, ",", ";", "\t"):
            try:
                if isinstance(source, Path):
                    return pd.read_csv(source, encoding=encoding, sep=sep, engine="python")
                source.seek(0)
                return pd.read_csv(source, encoding=encoding, sep=sep, engine="python")
            except UnicodeDecodeError as exc:
                last_error = exc
                break
            except pd.errors.EmptyDataError:
                raise AgentError("The dataset is empty. Add at least one row of data.", agent="parser")
            except Exception as exc:
                last_error = exc
                if "codec can't decode" in str(exc).lower():
                    break

    hint = (
        f"Could not read the uploaded file: {last_error}. "
        "Save CSV as UTF-8 or upload .xlsx/.xls."
        if last_error
        else f"Could not read {label} as CSV."
    )
    raise AgentError(hint, agent="parser") from last_error


def _read_uploaded_file(file_path: Path) -> pd.DataFrame:
    suffix = file_path.suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise AgentError(
            f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            agent="parser",
        )

    try:
        fix_ctx = get_active_fix_context()
        if suffix == ".csv":
            if _file_starts_with(file_path, b"PK\x03\x04") or _file_starts_with(file_path, b"\xd0\xcf\x11\xe0"):
                engine = fix_ctx.get("excel_engine") or "openpyxl"
                return pd.read_excel(file_path, engine=engine)
            return _read_csv_robust(file_path, label=str(file_path.name))

        engine = fix_ctx.get("excel_engine")
        if engine:
            return pd.read_excel(file_path, engine=engine)
        return pd.read_excel(file_path)
    except AgentError:
        raise
    except Exception as exc:
        raise AgentError(
            f"Could not read the uploaded file: {exc}. "
            "Ensure the file is a valid CSV or Excel spreadsheet.",
            agent="parser",
        ) from exc


def _fetch_google_sheet(url: str) -> pd.DataFrame:
    sheet_id = _extract_sheet_id(url)
    export_url = _export_url(sheet_id)

    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(export_url)
            if response.status_code in (401, 403):
                logger.info(
                    "Public Google Sheet export denied (%s), trying service account",
                    response.status_code,
                )
                return _normalize_dataframe(_fetch_google_sheet_via_service_account(sheet_id))
            response.raise_for_status()
            content = response.content
    except AgentError:
        raise
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            try:
                return _normalize_dataframe(_fetch_google_sheet_via_service_account(sheet_id))
            except AgentError:
                raise AgentError(_sheet_access_hint(), agent="parser") from exc
        raise AgentError(
            f"Failed to download Google Sheet: {exc}",
            agent="parser",
        ) from exc
    except Exception as exc:
        raise AgentError(
            f"Failed to download Google Sheet: {exc}",
            agent="parser",
        ) from exc

    try:
        df = _read_csv_robust(BytesIO(content), label="Google Sheet export")
    except AgentError:
        raise
    except Exception as exc:
        raise AgentError(
            f"Downloaded sheet is not valid CSV data: {exc}",
            agent="parser",
        ) from exc

    return df


def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        raise AgentError("The dataset is empty. Add at least one row of data.", agent="parser")

    df = df.copy()
    df.columns = [str(col).strip() for col in df.columns]

    if all(str(col).startswith("Unnamed") for col in df.columns):
        raise AgentError(
            "Could not detect column headers. Ensure the first row contains column names.",
            agent="parser",
        )

    df = df.dropna(how="all")
    if df.empty:
        raise AgentError("All rows are empty after cleanup.", agent="parser")

    return df.reset_index(drop=True)


def validate_request(
    email: str | None,
    sheets_url: str | None,
    has_file: bool,
) -> None:
    """Synchronous validation before queuing the Celery task."""
    _validate_email_optional(email)

    if not has_file and not sheets_url:
        raise AgentError(
            "Provide either a file upload (CSV/Excel) or a public Google Sheets URL.",
            agent="parser",
        )

    if has_file and sheets_url:
        raise AgentError(
            "Provide only one data source: either a file upload or a Google Sheets URL.",
            agent="parser",
        )

    if sheets_url:
        parsed = urlparse(sheets_url)
        if parsed.scheme not in ("http", "https"):
            raise AgentError("Google Sheets URL must start with http:// or https://", agent="parser")
        _extract_sheet_id(sheets_url)


def save_upload(file_content: bytes, original_filename: str) -> Path:
    """Persist uploaded bytes to disk and return the path."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    size_mb = len(file_content) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise AgentError(
            f"File too large ({size_mb:.1f} MB). Maximum allowed: {MAX_FILE_SIZE_MB} MB.",
            agent="parser",
        )

    suffix = Path(original_filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise AgentError(
            f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            agent="parser",
        )

    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
    dest.write_bytes(file_content)
    logger.info("Saved upload to %s (%d bytes)", dest, len(file_content))
    return dest


@with_self_healing("parser")
@track_agent_metrics("parser")
def run_parser(
    task_id: str,
    email: str | None = None,
    sheets_url: str | None = None,
    file_path: str | None = None,
) -> dict[str, Any]:
    """
    Load and normalize data. Returns a dict with serialized DataFrame and metadata.
    """
    try:
        logger.info("Parser started for task %s", task_id)
        _validate_email_optional(email)
        email_value = email.strip() if email and email.strip() else None

        if file_path:
            df = _read_uploaded_file(Path(file_path))
            source = f"file:{Path(file_path).name}"
        elif sheets_url:
            df = _fetch_google_sheet(sheets_url)
            source = f"sheets:{sheets_url}"
        else:
            raise AgentError(
                "No data source provided. Upload a file or provide a Google Sheets URL.",
                agent="parser",
            )

        df = _normalize_dataframe(df)

        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        text_cols = [c for c in df.columns if c not in numeric_cols]

        result = {
            "task_id": task_id,
            "email": email_value,
            "source": source,
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": list(df.columns),
            "numeric_columns": numeric_cols,
            "text_columns": text_cols,
            "data": df.to_dict(orient="records"),
        }
        logger.info(
            "Parser finished: %d rows, %d columns (%d numeric)",
            result["row_count"],
            result["column_count"],
            len(numeric_cols),
        )
        return result

    except AgentError:
        raise
    except Exception as exc:
        logger.exception("Unexpected parser error for task %s", task_id)
        raise AgentError(f"Unexpected error while parsing data: {exc}", agent="parser") from exc

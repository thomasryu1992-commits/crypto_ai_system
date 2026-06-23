from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def sync_rows_to_google_sheet(
    worksheet_name: str,
    rows: List[Dict[str, Any]],
    replace: bool = True,
) -> Dict[str, Any]:
    """
    Optional Google Sheets sync.

    Required .env:
    - GOOGLE_SHEETS_ENABLED=true
    - GOOGLE_SHEETS_SPREADSHEET_ID=...
    - GOOGLE_SERVICE_ACCOUNT_JSON=path/to/service_account.json

    If disabled or credentials are missing, this safely returns SKIPPED.
    """

    load_dotenv(PROJECT_ROOT / ".env")

    enabled = _env_bool("GOOGLE_SHEETS_ENABLED", False)
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "").strip()
    credentials_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()

    if not enabled:
        return {
            "status": "SKIPPED",
            "reason": "GOOGLE_SHEETS_ENABLED=false",
            "worksheet_name": worksheet_name,
            "row_count": len(rows),
        }

    if not spreadsheet_id:
        return {
            "status": "SKIPPED",
            "reason": "GOOGLE_SHEETS_SPREADSHEET_ID is missing",
            "worksheet_name": worksheet_name,
            "row_count": len(rows),
        }

    if not credentials_path:
        return {
            "status": "SKIPPED",
            "reason": "GOOGLE_SERVICE_ACCOUNT_JSON is missing",
            "worksheet_name": worksheet_name,
            "row_count": len(rows),
        }

    credential_file = Path(credentials_path)
    if not credential_file.is_absolute():
        credential_file = PROJECT_ROOT / credential_file

    if not credential_file.exists():
        return {
            "status": "SKIPPED",
            "reason": f"Google service account file not found: {credential_file}",
            "worksheet_name": worksheet_name,
            "row_count": len(rows),
        }

    try:
        import gspread  # type: ignore
    except Exception as error:
        return {
            "status": "ERROR",
            "error_type": type(error).__name__,
            "error_message": "gspread is not installed. Run: pip install gspread google-auth",
            "worksheet_name": worksheet_name,
            "row_count": len(rows),
        }

    try:
        client = gspread.service_account(filename=str(credential_file))
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = _get_or_create_worksheet(spreadsheet, worksheet_name)

        values = _rows_to_values(rows)

        if replace:
            worksheet.clear()

        if values:
            worksheet.update(values, value_input_option="USER_ENTERED")

        return {
            "status": "SYNCED",
            "worksheet_name": worksheet_name,
            "row_count": len(rows),
            "column_count": len(values[0]) if values else 0,
        }

    except Exception as error:
        return {
            "status": "ERROR",
            "error_type": type(error).__name__,
            "error_message": str(error),
            "worksheet_name": worksheet_name,
            "row_count": len(rows),
        }


def _get_or_create_worksheet(spreadsheet: Any, title: str) -> Any:
    try:
        return spreadsheet.worksheet(title)
    except Exception:
        return spreadsheet.add_worksheet(title=title, rows=1000, cols=30)


def _rows_to_values(rows: List[Dict[str, Any]]) -> List[List[Any]]:
    if not rows:
        return []

    headers: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in headers:
                headers.append(key)

    values = [headers]
    for row in rows:
        values.append([_cell_value(row.get(header)) for header in headers])

    return values


def _cell_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _env_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"true", "1", "yes", "y", "on"}

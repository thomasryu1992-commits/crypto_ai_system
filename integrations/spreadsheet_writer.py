from __future__ import annotations

import hashlib
import json
from typing import Any

from config.settings import (
    SPREADSHEET_DEAD_LETTER_PATH,
    SPREADSHEET_MAX_RETRY,
    SPREADSHEET_RETRY_QUEUE_PATH,
    SPREADSHEET_SYNC_RESULT_PATH,
)
from core.json_io import append_jsonl, atomic_write_json, read_jsonl
from core.time_utils import utc_now_iso
from integrations.local_csv_backup import append_local_csv
from integrations.spreadsheet_client import SpreadsheetClient
from integrations.spreadsheet_schema import SCHEMA_VERSION, get_schema


def make_row_id(tab: str, event_time: str, symbol: str, event_type: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(
        {"tab": tab, "event_time": event_time, "symbol": symbol, "event_type": event_type, "payload": payload},
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{tab}_{symbol}_{event_type}_{digest}"


def normalize_row(tab: str, row: dict[str, Any]) -> dict[str, Any]:
    columns = get_schema(tab)
    event_time = str(row.get("event_time") or row.get("timestamp") or utc_now_iso())
    symbol = str(row.get("symbol") or "BTCUSDT")
    event_type = str(row.get("event_type") or tab)
    normalized = {col: "" for col in columns}
    normalized.update({k: _stringify(v) for k, v in row.items() if k in normalized})
    normalized["created_at"] = normalized.get("created_at") or utc_now_iso()
    normalized["event_time"] = event_time
    normalized["symbol"] = symbol
    normalized["event_type"] = event_type
    normalized["schema_version"] = SCHEMA_VERSION
    normalized["row_id"] = normalized.get("row_id") or make_row_id(tab, event_time, symbol, event_type, row)
    return normalized


def _stringify(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, default=str)
    if value is None:
        return ""
    return value


class SpreadsheetWriter:
    def __init__(self):
        self.client = SpreadsheetClient()

    def append(self, tab: str, row: dict[str, Any]) -> dict[str, Any]:
        return self.batch_append({tab: [row]})

    def batch_append(self, rows_by_tab: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        normalized_by_tab: dict[str, list[dict[str, Any]]] = {}
        local_paths = []
        for tab, rows in rows_by_tab.items():
            normalized_by_tab[tab] = [normalize_row(tab, row) for row in rows]
            for normalized in normalized_by_tab[tab]:
                local_paths.append(append_local_csv(tab, normalized))

        client_result = self.client.append_rows(normalized_by_tab)
        status = "EXPORTED_LOCAL_BACKUP"
        if client_result.get("status", "").startswith("SKIPPED_GOOGLE"):
            for tab, rows in normalized_by_tab.items():
                for row in rows:
                    append_jsonl(
                        SPREADSHEET_RETRY_QUEUE_PATH,
                        {
                            "created_at": utc_now_iso(),
                            "target_tab": tab,
                            "status": "PENDING_RETRY",
                            "payload": row,
                            "retry_count": 0,
                            "last_error": client_result.get("status"),
                        },
                    )
            status = "QUEUED_FOR_GOOGLE_SHEETS_RETRY"

        result = {
            "created_at": utc_now_iso(),
            "status": status,
            "provider_result": client_result,
            "tabs": list(normalized_by_tab.keys()),
            "rows": sum(len(v) for v in normalized_by_tab.values()),
            "local_backup_paths": sorted(set(local_paths)),
        }
        atomic_write_json(SPREADSHEET_SYNC_RESULT_PATH, result)
        return result

    def process_retry_queue(self) -> dict[str, Any]:
        pending = read_jsonl(SPREADSHEET_RETRY_QUEUE_PATH)
        if not pending:
            return {"created_at": utc_now_iso(), "status": "NO_PENDING_RETRY", "processed": 0}

        processed = 0
        for item in pending:
            if int(item.get("retry_count", 0)) >= SPREADSHEET_MAX_RETRY:
                item["status"] = "DEAD_LETTER"
                item["moved_at"] = utc_now_iso()
                append_jsonl(SPREADSHEET_DEAD_LETTER_PATH, item)
                processed += 1

        return {"created_at": utc_now_iso(), "status": "RETRY_QUEUE_SCANNED", "processed": processed}

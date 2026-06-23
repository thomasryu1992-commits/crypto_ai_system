from __future__ import annotations

from typing import Any

from core.json_io import atomic_write_json
from core.time_utils import utc_now_iso
from integrations.spreadsheet_writer import SpreadsheetWriter


class StorageRouter:
    """Step150 storage policy.

    latest JSON = current state cache
    Spreadsheet/local CSV = history and operations log
    retry queue = failed Google Sheets writes
    """

    def __init__(self):
        self.writer = SpreadsheetWriter()

    def save_latest_and_append(self, latest_path, tab: str, row: dict[str, Any], latest_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = latest_payload if latest_payload is not None else row
        atomic_write_json(latest_path, payload)
        return self.writer.append(tab, row)

    def append_history(self, tab: str, row: dict[str, Any]) -> dict[str, Any]:
        return self.writer.append(tab, row)


def with_event_defaults(event_type: str, symbol: str = "BTCUSDT", **kwargs: Any) -> dict[str, Any]:
    return {
        "created_at": utc_now_iso(),
        "event_time": kwargs.pop("event_time", utc_now_iso()),
        "symbol": symbol,
        "event_type": event_type,
        **kwargs,
    }

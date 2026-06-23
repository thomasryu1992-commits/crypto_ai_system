from __future__ import annotations

from typing import Any

from config.settings import SPREADSHEET_ENABLED, SPREADSHEET_PROVIDER


class SpreadsheetClient:
    """Spreadsheet-first client.

    Step150 defaults to local_csv. Google Sheets write support is intentionally guarded.
    Implement actual Google Sheets API calls after credentials and quota handling are tested.
    """

    def __init__(self, provider: str | None = None):
        self.provider = provider or SPREADSHEET_PROVIDER
        self.enabled = SPREADSHEET_ENABLED

    def append_rows(self, rows_by_tab: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        if self.provider == "google_sheets" and self.enabled:
            # Guarded scaffold. Do not silently pretend real Google Sheets writes.
            return {
                "status": "SKIPPED_GOOGLE_SHEETS_NOT_IMPLEMENTED_IN_GUARDED_PACKAGE",
                "provider": self.provider,
                "rows_requested": sum(len(v) for v in rows_by_tab.values()),
            }

        return {
            "status": "LOCAL_CSV_ONLY",
            "provider": "local_csv",
            "rows_requested": sum(len(v) for v in rows_by_tab.values()),
        }

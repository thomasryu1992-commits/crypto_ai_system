from __future__ import annotations

import csv
from config.settings import storage_path
from core.json_io import read_json, write_json
from core.time_utils import utc_now_iso


def sync_spreadsheet() -> dict:
    trading = read_json(storage_path("trading_cycle_result.json"), default={})
    csv_path = storage_path("reports/spreadsheet_sync_export.csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp_utc", "status", "current_price", "signal", "confidence"])
        signal = trading.get("signal", {})
        writer.writerow([
            trading.get("timestamp_utc"),
            trading.get("status"),
            trading.get("current_price"),
            signal.get("side"),
            signal.get("confidence"),
        ])

    result = {
        "name": "SPREADSHEET_SYNC",
        "status": "SYNC_COMPLETED",
        "local_export_path": str(csv_path.resolve()),
        "timestamp_utc": utc_now_iso(),
    }
    write_json(storage_path("spreadsheet_sync_result.json"), result)
    return result

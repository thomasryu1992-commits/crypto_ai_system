from __future__ import annotations

import subprocess
import sys

from config.settings import STORAGE_DIR, ensure_base_dirs, env_bool
from integrations.spreadsheet_exporter import run_spreadsheet_sync
from run_research_cycle import run_research_cycle
from scripts.json_utils import now_utc_iso, save_json


def main() -> None:
    ensure_base_dirs()
    research = run_research_cycle()

    trading_proc = subprocess.run(
        [sys.executable, "run_trading_cycle.py"],
        cwd=str(STORAGE_DIR.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    spreadsheet_result = {"status": "SKIPPED", "reason": "SPREADSHEET_SYNC_AFTER_FULL_CYCLE=false"}
    if env_bool("SPREADSHEET_SYNC_AFTER_FULL_CYCLE", False):
        spreadsheet_result = run_spreadsheet_sync()

    result = {
        "status": "FULL_CYCLE_COMPLETED" if trading_proc.returncode == 0 else "FULL_CYCLE_ERROR",
        "timestamp_utc": now_utc_iso(),
        "research_cycle": research,
        "trading_process": {
            "return_code": trading_proc.returncode,
            "stdout": trading_proc.stdout[-5000:],
            "stderr": trading_proc.stderr[-5000:],
        },
        "spreadsheet_sync": {
            "status": spreadsheet_result.get("status"),
            "summary": spreadsheet_result.get("summary"),
            "files": spreadsheet_result.get("files"),
            "reason": spreadsheet_result.get("reason"),
        },
    }

    save_json(STORAGE_DIR / "full_cycle_result.json", result)

    print("[FULL CYCLE]")
    print(f"Status: {result.get('status')}")
    print(f"Spreadsheet Sync: {result.get('spreadsheet_sync')}")
    print(trading_proc.stdout)

    if trading_proc.returncode != 0:
        print(trading_proc.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

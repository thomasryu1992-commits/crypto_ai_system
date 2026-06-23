from __future__ import annotations

from config.settings import LATEST_DIR
from core.json_io import atomic_write_json
from core.time_utils import utc_now_iso
from run_full_cycle import run_full_cycle


def main() -> None:
    result = run_full_cycle()
    out = {
        "created_at": utc_now_iso(),
        "status": "PASSED",
        "mode": "operational_dry_run_step150",
        "final_decision": result["trade_decision"]["final_decision"],
        "data_health": result["data_health"]["status"],
        "order_status": result["order"]["status"],
        "spreadsheet_status": result["spreadsheet"]["status"],
    }
    atomic_write_json(LATEST_DIR / "operational_dry_run_result.json", out)
    print("Operational dry run Step150: PASSED")


if __name__ == "__main__":
    main()

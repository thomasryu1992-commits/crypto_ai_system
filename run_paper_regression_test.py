from __future__ import annotations

import os
import subprocess
import sys

from config.settings import PROJECT_ROOT, STORAGE_DIR, ensure_base_dirs
from scripts.json_utils import load_json, now_utc_iso, save_json


def main() -> None:
    ensure_base_dirs()
    steps = []
    subprocess.run([sys.executable, "reset_paper_state.py"], cwd=str(PROJECT_ROOT), check=False)
    research = subprocess.run([sys.executable, "run_research_cycle.py"], cwd=str(PROJECT_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    steps.append({"name": "research_cycle", "return_code": research.returncode})

    market = load_json(STORAGE_DIR / "market_context.json", default={})
    if isinstance(market, dict):
        market["current_price"] = 106850
        save_json(STORAGE_DIR / "market_context.json", market)
    cycle1 = subprocess.run([sys.executable, "run_trading_cycle.py"], cwd=str(PROJECT_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    steps.append({"name": "watch_create", "return_code": cycle1.returncode})

    market = load_json(STORAGE_DIR / "market_context.json", default={})
    if isinstance(market, dict):
        market["current_price"] = 107600
        save_json(STORAGE_DIR / "market_context.json", market)
    cycle2 = subprocess.run([sys.executable, "run_trading_cycle.py"], cwd=str(PROJECT_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    steps.append({"name": "trigger_position", "return_code": cycle2.returncode})

    trading = load_json(STORAGE_DIR / "trading_bot_result.json", default={})
    recon = load_json(STORAGE_DIR / "execution_reconciliation_result.json", default={})
    result = {
        "status": "PAPER_REGRESSION_COMPLETED",
        "timestamp_utc": now_utc_iso(),
        "steps": steps,
        "trading_bot_status": trading.get("status") if isinstance(trading, dict) else None,
        "bridge_status": trading.get("order_executor_bridge_status") if isinstance(trading, dict) else None,
        "reconciliation_status": recon.get("status") if isinstance(recon, dict) else None,
        "reconciled": recon.get("reconciled") if isinstance(recon, dict) else None,
        "note": "For MOCK_ORDER_ACCEPTED, set ORDER_EXECUTOR_INTEGRATION_ENABLED=true and EXCHANGE_ORDER_ENABLED=true before running.",
    }
    save_json(STORAGE_DIR / "paper_regression_test_result.json", result)
    print("[PAPER REGRESSION TEST]")
    print(result)


if __name__ == "__main__":
    main()

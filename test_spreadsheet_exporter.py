from __future__ import annotations

import sys

from integrations.spreadsheet_exporter import build_spreadsheet_tables, run_spreadsheet_sync


def main() -> None:
    tables = build_spreadsheet_tables()
    required_tables = {
        "dashboard_summary",
        "market_snapshot",
        "research_decision",
        "trading_cycle",
        "paper_trade_history",
        "paper_performance",
        "setup_performance",
        "setup_weight",
        "risk_check",
        "order_execution",
        "execution_reconciliation",
        "kb_lint",
    }

    missing = required_tables - set(tables.keys())

    print("=" * 80)
    print("[SPREADSHEET EXPORTER TEST]")
    print("=" * 80)
    print(f"Table Count: {len(tables)}")
    print(f"Missing Tables: {sorted(missing)}")

    for name, rows in tables.items():
        print(f"- {name}: {len(rows)} rows")

    if missing:
        sys.exit(1)

    result = run_spreadsheet_sync()
    print("-" * 80)
    print(f"Sync Status: {result.get('status')}")
    print(f"Summary: {result.get('summary')}")

    if result.get("status") == "SYNC_COMPLETED_WITH_ERRORS":
        sys.exit(1)


if __name__ == "__main__":
    main()

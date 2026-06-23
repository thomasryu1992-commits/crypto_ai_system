from __future__ import annotations

from config.settings import STORAGE_DIR, ensure_base_dirs

RESET_FILES = [
    "paper_watchlist.json", "paper_watch_result.json", "paper_positions.json", "paper_position_result.json", "paper_trade_history.json",
    "paper_performance_report.json", "setup_performance_report.json", "setup_weight_report.json", "setup_decision_filter_result.json",
    "bot_state.json", "trading_bot_result.json", "trading_cycle_result.json", "trading_cycle_log.json", "telegram_alert_result.json",
    "risk_check_result.json", "risk_check_log.json", "order_execution_result.json", "order_execution_log.json", "exchange_router_result.json", "exchange_router_log.json",
    "mock_order_result.json", "mock_order_log.json", "paper_order_execution_map.json", "execution_reconciliation_result.json", "execution_reconciliation_log.json",
    "forward_test_result.json", "forward_test_log.json", "full_cycle_result.json", "research_cycle_result.json",
    "full_regression_test_result.json", "full_regression_test_log.json",
    "spreadsheet_sync_result.json", "spreadsheet_sync_log.json",
]


def main() -> None:
    ensure_base_dirs()
    removed = []
    for name in RESET_FILES:
        path = STORAGE_DIR / name
        if path.exists():
            path.unlink()
            removed.append(str(path))
    print("[RESET PAPER STATE]")
    print(f"Removed files: {len(removed)}")
    for item in removed:
        print(f"- {item}")


if __name__ == "__main__":
    main()

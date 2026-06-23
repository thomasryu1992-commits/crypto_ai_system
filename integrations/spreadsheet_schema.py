from __future__ import annotations

SCHEMA_VERSION = "v3"

COMMON_COLUMNS = ["row_id", "created_at", "event_time", "symbol", "event_type", "schema_version"]

SCHEMAS: dict[str, list[str]] = {
    "01_Config": COMMON_COLUMNS + ["key", "value", "description"],
    "02_Market_Snapshot": COMMON_COLUMNS + [
        "timeframe", "last_close", "change_24h_pct", "ma20", "ma50", "volume_ratio",
        "funding_rate", "open_interest_change_24h", "trend_bias", "source_type",
        "data_quality", "is_synthetic", "is_fallback",
    ],
    "03_Data_Health": COMMON_COLUMNS + [
        "status", "allow_trading", "source_type", "data_quality", "is_synthetic",
        "is_fallback", "candle_count", "latest_candle_time", "problems", "warnings",
    ],
    "04_Research_Score": COMMON_COLUMNS + [
        "final_score", "market_structure_score", "momentum_score", "derivatives_score",
        "data_quality_penalty", "scenario", "signal_quality", "signal_timing", "positives", "risks",
    ],
    "05_Research_Decision": COMMON_COLUMNS + [
        "research_bias", "scenario", "signal_quality", "signal_timing", "final_score",
        "allow_long", "allow_short", "reasons",
    ],
    "06_Trading_Signal": COMMON_COLUMNS + [
        "signal", "confidence", "reasons", "entry_candidate_price", "source_snapshot_time",
    ],
    "07_Trade_Decision": COMMON_COLUMNS + [
        "research_scenario", "signal_quality", "signal_timing", "trading_signal",
        "data_health_status", "risk_status", "final_decision", "allow_order_intent",
        "direction", "confidence", "reasons",
    ],
    "08_Order_Intent": COMMON_COLUMNS + [
        "intent_id", "idempotency_key", "client_order_id", "direction", "side", "order_type",
        "notional_usdt", "state", "source_decision",
    ],
    "09_Order_Result": COMMON_COLUMNS + [
        "intent_id", "client_order_id", "state", "status", "mode", "exchange_order_id",
        "filled", "error_code", "error_message",
    ],
    "10_Paper_Trades": COMMON_COLUMNS + [
        "trade_id", "direction", "entry_time", "entry_price", "stop_loss", "take_profit",
        "exit_time", "exit_price", "result", "pnl_r", "entry_reason", "exit_reason",
        "holding_candles", "max_favorable_excursion", "max_adverse_excursion",
    ],
    "11_Risk_Events": COMMON_COLUMNS + [
        "status", "allow_new_position", "daily_pnl_r", "weekly_pnl_r",
        "consecutive_losses", "drawdown_r", "problems",
    ],
    "12_Live_Shadow": COMMON_COLUMNS + [
        "decision", "order_status", "live_ready", "estimated_roundtrip_cost_bps",
        "slippage_assumption_bps", "fee_assumption_bps", "latency_assumption_ms", "notes",
    ],
    "13_System_Health": COMMON_COLUMNS + [
        "scheduler_status", "missing_outputs", "data_health_status", "allow_trading",
        "last_success_time", "last_error",
    ],
    "14_Forward_Test": COMMON_COLUMNS + [
        "iteration", "final_decision", "data_health", "risk_status", "order_status",
        "paper_position_status", "notes",
    ],
    "15_Testnet_Orders": COMMON_COLUMNS + [
        "intent_id", "client_order_id", "state", "status", "request_type", "response_summary",
    ],
    "16_Testnet_Reconciliation": COMMON_COLUMNS + [
        "intent_id", "client_order_id", "local_state", "exchange_state", "reconciliation_status", "notes",
    ],
    "17_Limited_Live_Readiness": COMMON_COLUMNS + [
        "readiness_status", "checks_passed", "checks_failed", "max_live_position_usdt",
        "max_order_notional_usdt", "required_next_steps",
    ],
}


def get_schema(tab: str) -> list[str]:
    if tab not in SCHEMAS:
        raise KeyError(f"Unknown spreadsheet tab: {tab}")
    return SCHEMAS[tab]


def all_tabs() -> list[str]:
    return list(SCHEMAS.keys())

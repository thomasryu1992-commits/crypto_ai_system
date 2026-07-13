from __future__ import annotations

from config.settings import (
    DATA_HEALTH_PATH,
    LIMITED_LIVE_READINESS_REPORT_PATH,
    LIVE_SHADOW_REPORT_PATH,
    MARKET_SNAPSHOT_PATH,
    ORDER_INTENT_PATH,
    ORDER_RESULT_PATH,
    RESEARCH_DECISION_PATH,
    RESEARCH_RESULT_PATH,
    RISK_STATUS_PATH,
    SCHEDULER_HEALTH_PATH,
    TRADE_DECISION_PATH,
    TRADING_CYCLE_PATH,
)
from core.json_io import read_json
from integrations.spreadsheet_writer import SpreadsheetWriter


def export_spreadsheet_schema_v3() -> dict:
    snapshot = read_json(MARKET_SNAPSHOT_PATH, {})
    health = read_json(DATA_HEALTH_PATH, {})
    research = read_json(RESEARCH_RESULT_PATH, {})
    research_decision = read_json(RESEARCH_DECISION_PATH, {})
    trading = read_json(TRADING_CYCLE_PATH, {})
    trade_decision = read_json(TRADE_DECISION_PATH, {})
    order_intent = read_json(ORDER_INTENT_PATH, {})
    order_result = read_json(ORDER_RESULT_PATH, {})
    risk = read_json(RISK_STATUS_PATH, {})
    live_shadow = read_json(LIVE_SHADOW_REPORT_PATH, {})
    scheduler = read_json(SCHEDULER_HEALTH_PATH, {})
    limited_live = read_json(LIMITED_LIVE_READINESS_REPORT_PATH, {})

    symbol = snapshot.get("symbol") or trade_decision.get("research", {}).get("symbol", "BTCUSDT")
    rows = {
        "02_Market_Snapshot": [{
            "symbol": symbol,
            "event_type": "MARKET_SNAPSHOT",
            "event_time": snapshot.get("created_at"),
            **{k: snapshot.get(k, "") for k in [
                "timeframe", "last_close", "change_24h_pct", "ma20", "ma50", "volume_ratio",
                "funding_rate", "open_interest_change_24h", "trend_bias", "source_type",
                "data_quality", "is_synthetic", "is_fallback"
            ]},
        }],
        "03_Data_Health": [{
            "symbol": symbol,
            "event_type": "DATA_HEALTH",
            "event_time": health.get("created_at"),
            **{k: health.get(k, "") for k in [
                "status", "allow_trading", "source_type", "data_quality", "is_synthetic",
                "is_fallback", "candle_count", "latest_candle_time", "problems", "warnings"
            ]},
        }],
        "04_Research_Score": [{
            "symbol": symbol,
            "event_type": "RESEARCH_SCORE",
            "event_time": research.get("created_at"),
            "scenario": research.get("scenario"),
            "signal_quality": research.get("signal_quality"),
            "signal_timing": research.get("signal_timing"),
            **research.get("scores", {}),
        }],
        "05_Research_Decision": [{
            "symbol": symbol,
            "event_type": "RESEARCH_DECISION",
            "event_time": research_decision.get("created_at"),
            **{k: research_decision.get(k, "") for k in [
                "research_bias", "scenario", "signal_quality", "signal_timing", "final_score",
                "allow_long", "allow_short", "reasons"
            ]},
        }],
        "06_Trading_Signal": [{
            "symbol": symbol,
            "event_type": "TRADING_SIGNAL",
            "event_time": trading.get("created_at"),
            "signal": trading.get("trading_signal", {}).get("signal"),
            "confidence": trading.get("trading_signal", {}).get("confidence"),
            "reasons": trading.get("trading_signal", {}).get("reasons"),
            "entry_candidate_price": snapshot.get("last_close"),
            "source_snapshot_time": snapshot.get("last_candle_time"),
        }],
        "07_Trade_Decision": [{
            "symbol": symbol,
            "event_type": "TRADE_DECISION",
            "event_time": trade_decision.get("created_at"),
            "research_scenario": research_decision.get("scenario"),
            "signal_quality": research_decision.get("signal_quality"),
            "signal_timing": research_decision.get("signal_timing"),
            "trading_signal": trading.get("trading_signal", {}).get("signal"),
            "data_health_status": health.get("status"),
            "risk_status": risk.get("status"),
            "final_decision": trade_decision.get("final_decision"),
            "allow_order_intent": trade_decision.get("allow_order_intent"),
            "direction": trade_decision.get("direction"),
            "confidence": trade_decision.get("confidence"),
            "reasons": trade_decision.get("reasons"),
        }],
        "08_Order_Intent": [{
            "symbol": symbol,
            "event_type": "ORDER_INTENT",
            "event_time": order_intent.get("created_at"),
            "intent_id": order_intent.get("intent_id"),
            "idempotency_key": order_intent.get("idempotency_key"),
            "client_order_id": order_intent.get("client_order_id"),
            "direction": order_intent.get("direction"),
            "side": order_intent.get("side"),
            "order_type": order_intent.get("order_type"),
            "notional_usdt": order_intent.get("notional_usdt"),
            "state": order_intent.get("state"),
            "source_decision": order_intent.get("source_decision"),
        }],
        "09_Order_Result": [{
            "symbol": symbol,
            "event_type": "ORDER_RESULT",
            "event_time": order_result.get("created_at"),
            "intent_id": order_result.get("intent", {}).get("intent_id"),
            "client_order_id": order_result.get("intent", {}).get("client_order_id"),
            "state": order_result.get("state"),
            "status": order_result.get("status"),
            "mode": order_result.get("mode"),
            "exchange_order_id": order_result.get("exchange_order_id"),
            "filled": order_result.get("filled"),
        }],
        "11_Risk_Events": [{
            "symbol": symbol,
            "event_type": "RISK_EVENT",
            "event_time": risk.get("created_at"),
            **{k: risk.get(k, "") for k in [
                "status", "allow_new_position", "daily_pnl_r", "weekly_pnl_r",
                "consecutive_losses", "drawdown_r", "problems"
            ]},
        }],
        "12_Live_Shadow": [{
            "symbol": symbol,
            "event_type": "LIVE_SHADOW",
            "event_time": live_shadow.get("created_at"),
            **{k: live_shadow.get(k, "") for k in [
                "decision", "order_status", "live_ready", "estimated_roundtrip_cost_bps",
                "slippage_assumption_bps", "fee_assumption_bps", "latency_assumption_ms", "notes"
            ]},
        }],
        "13_System_Health": [{
            "symbol": symbol,
            "event_type": "SYSTEM_HEALTH",
            "event_time": scheduler.get("created_at"),
            "scheduler_status": scheduler.get("status"),
            "missing_outputs": scheduler.get("missing_outputs"),
            "data_health_status": scheduler.get("data_health_status"),
            "allow_trading": scheduler.get("allow_trading"),
        }],
    }

    if limited_live:
        rows["17_Limited_Live_Readiness"] = [{
            "symbol": symbol,
            "event_type": "LIMITED_LIVE_READINESS",
            "event_time": limited_live.get("created_at"),
            "readiness_status": limited_live.get("readiness_status"),
            "checks_passed": limited_live.get("checks_passed"),
            "checks_failed": limited_live.get("checks_failed"),
            "max_live_position_usdt": limited_live.get("max_live_position_usdt"),
            "max_order_notional_usdt": limited_live.get("max_order_notional_usdt"),
            "required_next_steps": limited_live.get("required_next_steps"),
        }]

    return SpreadsheetWriter().batch_append(rows)


def export_latest_results_to_csv() -> dict:
    """Compatibility wrapper that exports schema v3 rows to local CSV backup."""
    result = export_spreadsheet_schema_v3()
    return {
        "created_at": result.get("created_at"),
        "status": "EXPORTED_LOCAL_CSV",
        "base_status": result.get("status"),
        "rows": result.get("rows", 0),
        "local_backup_paths": result.get("local_backup_paths", []),
    }


def export_latest_results() -> dict:
    """Compatibility wrapper for older tests and runners."""
    local_csv = export_latest_results_to_csv()
    return {
        "created_at": local_csv.get("created_at"),
        "status": "EXPORTED",
        "local_csv": local_csv,
        "google_sheets": {"status": "SKIPPED_OR_QUEUED_BY_CONFIG"},
    }


def main() -> None:
    result = export_spreadsheet_schema_v3()
    print(f"Spreadsheet export: {result['status']} rows={result['rows']}")


if __name__ == "__main__":
    main()

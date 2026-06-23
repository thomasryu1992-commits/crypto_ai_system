from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from config.settings import env_float, env_int, env_str
from knowledge_engine.wiki_writer import markdown_doc, update_index, update_log, wiki_path, write_markdown


def run_report_builder(market_context: Dict[str, Any]) -> Dict[str, Any]:
    date_label = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    trigger = env_float("FALLBACK_TRIGGER_PRICE", 107500.0)
    invalidation = env_float("FALLBACK_INVALIDATION_PRICE", 106200.0)
    take_profit = env_float("FALLBACK_TAKE_PROFIT", 110000.0)
    setup_type = env_str("FALLBACK_SETUP_TYPE", "breakout_reclaim")
    direction = env_str("FALLBACK_SETUP_DIRECTION", "long")
    expires = env_int("FALLBACK_EXPIRES_AFTER_HOURS", 24)
    current_price = market_context.get("current_price")
    data_mode = market_context.get("data_mode") or market_context.get("source")
    market_data = market_context.get("market_data", {}) if isinstance(market_context.get("market_data"), dict) else {}

    price_signal = _nested_get(market_data, "price", "signal", default="unknown")
    oi_signal = _nested_get(market_data, "open_interest", "signal", default="unknown")
    funding_signal = _nested_get(market_data, "funding_rate", "signal", default="unknown")
    long_short_signal = _nested_get(market_data, "long_short_ratio", "signal", default="unknown")
    liquidation_signal = _nested_get(market_data, "liquidation", "signal", default="unknown")

    daily = markdown_doc(f"Daily Crypto Market Report - {date_label}", {
        "Market Summary": (
            f"BTC is trading around {current_price}. Data mode: {data_mode}. "
            "The structure is neutral-to-bullish, but confirmation is required before entry."
        ),
        "Key Observations": (
            f"- Price signal: {price_signal}\n"
            f"- Open interest signal: {oi_signal}\n"
            f"- Funding signal: {funding_signal}\n"
            f"- Long/short signal: {long_short_signal}\n"
            f"- Liquidation signal: {liquidation_signal}"
        ),
        "Active Scenarios": "1. [[scenario/btc_short_squeeze_scenario]]\n2. [[scenario/btc_breakdown_scenario]]",
        "Trading Bias": "neutral_to_bullish",
        "Conditional Setup": f"- Setup Type: {setup_type}\n- Direction: {direction}\n- Trigger: {trigger}\n- Invalidation: {invalidation}\n- Take Profit: {take_profit}\n- Expires After Hours: {expires}",
        "Risk Notes": "- Avoid entry if funding overheats.\n- Avoid entry if spot CVD remains negative.\n- Do not enter if KB lint status is ERROR.\n- Fallback setup levels must be reviewed before live trading.",
        "Evidence": "- [[source/coinalyze]]\n- [[entity/BTC]]\n- [[concept/open_interest]]\n- [[concept/funding_rate]]\n- [[concept/cvd]]",
        "Final Decision": "Create conditional watch, not market order.",
        "Last Updated": str(market_context.get("timestamp_utc", "unknown")),
    })
    report_path = write_markdown(wiki_path("report", "daily", f"{date_label}.md"), daily)

    hot = markdown_doc("Hot Topics", {
        date_label: "### BTC liquidity expansion watch\n- Status: active\n- Related entity: [[entity/BTC]]\n- Related concept: [[concept/open_interest]], [[concept/funding_rate]], [[concept/cvd]]\n- Related scenario: [[scenario/btc_short_squeeze_scenario]]\n- Confidence: medium",
        "Last Updated": str(market_context.get("timestamp_utc", "unknown")),
    })
    hot_path = write_markdown(wiki_path("hot.md"), hot)
    index_path = update_index()
    log_path = update_log(
        added=[f"report/daily/{date_label}"],
        updated=["hot", "index", "entity/BTC", "scenario/btc_short_squeeze_scenario"],
        reason="Research cycle completed and daily report generated.",
    )
    latest_path = write_markdown(wiki_path("report", "daily", "latest.md"), daily)

    return {
        "status": "REPORT_UPDATED",
        "daily_report": str(report_path),
        "latest_report": str(latest_path),
        "files": [str(report_path), str(latest_path), str(hot_path), str(index_path), str(log_path)],
    }


def _nested_get(data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current

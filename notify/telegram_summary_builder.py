from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


# ============================================================
# Basic Helpers
# ============================================================

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json_file(path: Optional[Path]) -> Dict[str, Any]:
    if path is None:
        return {}

    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data

        return {
            "status": "INVALID_JSON_TYPE",
            "error": "JSON root is not an object.",
            "path": str(path),
        }

    except Exception as exc:
        return {
            "status": "LOAD_FAILED",
            "error": str(exc),
            "path": str(path),
        }


def first_non_empty(*values: Any, default: Any = "-") -> Any:
    for value in values:
        if value is None:
            continue

        if isinstance(value, str) and not value.strip():
            continue

        return value

    return default


def safe_get(data: Dict[str, Any], key: str, default: Any = "-") -> Any:
    value = data.get(key, default)

    if value is None:
        return default

    if isinstance(value, str) and not value.strip():
        return default

    return value


def format_price(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "-"


def format_score(value: Any) -> str:
    try:
        return f"{int(float(value))}/100"
    except Exception:
        return "-"


def format_confidence(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except Exception:
        return "-"


def format_bool(value: Any) -> str:
    if value is True:
        return "Yes"

    if value is False:
        return "No"

    if value is None:
        return "-"

    return str(value)


def format_pct(value: Any) -> str:
    try:
        return f"{float(value):.2f}%"
    except Exception:
        return "-"


# ============================================================
# Daily Report Finder
# ============================================================

def daily_report_quality_score(data: Dict[str, Any]) -> int:
    if not isinstance(data, dict):
        return 0

    score = 0

    if data.get("report_date"):
        score += 1

    if data.get("current_price") is not None:
        score += 3

    if data.get("market_bias"):
        score += 3

    if data.get("research_score") is not None:
        score += 3

    summary = data.get("summary", {})
    if isinstance(summary, dict):
        if summary.get("base_case"):
            score += 2
        if summary.get("key_reason"):
            score += 2
        if summary.get("risk_note"):
            score += 2

    if data.get("status") in {"RESEARCH_CYCLE_COMPLETED", "COMPLETED"}:
        score += 1

    return score


def latest_daily_report_file(storage_path: Path) -> Optional[Path]:
    reports_path = storage_path / "reports"

    candidates = []
    candidates.extend(storage_path.glob("daily_report_*.json"))
    candidates.extend(reports_path.glob("daily_report_*.json"))

    candidates = [
        path
        for path in candidates
        if path.is_file()
        and "scheduler" not in path.name.lower()
        and "health" not in path.name.lower()
        and "result" not in path.name.lower()
    ]

    if not candidates:
        return None

    ranked = []

    for path in candidates:
        data = load_json_file(path)
        quality = daily_report_quality_score(data)
        modified_time = path.stat().st_mtime
        ranked.append((quality, modified_time, path))

    ranked = sorted(
        ranked,
        key=lambda item: (item[0], item[1]),
        reverse=True,
    )

    return ranked[0][2]


# ============================================================
# Data Extractors
# ============================================================

def extract_summary(
    daily_report: Dict[str, Any],
    research_cycle_result: Dict[str, Any],
) -> Dict[str, Any]:
    daily_summary = daily_report.get("summary", {})
    research_summary = research_cycle_result.get("summary", {})

    if not isinstance(daily_summary, dict):
        daily_summary = {}

    if not isinstance(research_summary, dict):
        research_summary = {}

    return {
        "base_case": first_non_empty(
            daily_summary.get("base_case"),
            research_summary.get("base_case"),
            default="-",
        ),
        "key_reason": first_non_empty(
            daily_summary.get("key_reason"),
            research_summary.get("key_reason"),
            default="-",
        ),
        "risk_note": first_non_empty(
            daily_summary.get("risk_note"),
            research_summary.get("risk_note"),
            default="-",
        ),
    }


def extract_signal_quality(signal_quality_report: Dict[str, Any]) -> Dict[str, Any]:
    signal_quality_status = safe_get(signal_quality_report, "status", "-")
    signal_quality_score = safe_get(signal_quality_report, "overall_score", "-")
    signal_quality_total_records = safe_get(signal_quality_report, "total_records", "-")

    components = signal_quality_report.get("components", {})
    if not isinstance(components, dict):
        components = {}

    signal_distribution = components.get("signal_distribution", {})
    if not isinstance(signal_distribution, dict):
        signal_distribution = {}

    watch_ratio = safe_get(signal_distribution, "watch_ratio_pct", "-")
    directional_ratio = safe_get(signal_distribution, "directional_ratio_pct", "-")
    unknown_ratio = safe_get(signal_distribution, "unknown_ratio_pct", "-")

    signal_counts = signal_distribution.get("signal_counts", {})
    if not isinstance(signal_counts, dict):
        signal_counts = {}

    watch_count = signal_counts.get("WATCH", 0)
    long_count = signal_counts.get("LONG", 0)
    short_count = signal_counts.get("SHORT", 0)

    return {
        "status": signal_quality_status,
        "overall_score": signal_quality_score,
        "total_records": signal_quality_total_records,
        "watch_ratio": watch_ratio,
        "directional_ratio": directional_ratio,
        "unknown_ratio": unknown_ratio,
        "watch_count": watch_count,
        "long_count": long_count,
        "short_count": short_count,
    }


def extract_calibration_advice(
    signal_calibration_advice: Dict[str, Any],
) -> Dict[str, Any]:
    action = safe_get(signal_calibration_advice, "recommended_action", "-")
    confidence = safe_get(signal_calibration_advice, "advisor_confidence", "-")
    recent_watch_streak = safe_get(signal_calibration_advice, "recent_watch_streak", "-")
    watch_ratio = safe_get(signal_calibration_advice, "watch_ratio_pct", "-")
    directional_ratio = safe_get(signal_calibration_advice, "directional_ratio_pct", "-")

    recommendations = signal_calibration_advice.get("recommendations", [])
    if not isinstance(recommendations, list):
        recommendations = []

    top_recommendation = "-"
    if recommendations:
        top_recommendation = str(recommendations[0])

    return {
        "action": action,
        "confidence": confidence,
        "recent_watch_streak": recent_watch_streak,
        "watch_ratio": watch_ratio,
        "directional_ratio": directional_ratio,
        "top_recommendation": top_recommendation,
    }




def extract_trade_permission(
    trading_cycle_result: Dict[str, Any] | None = None,
    permission_gate_audit: Dict[str, Any] | None = None,
    paper_risk_level_report: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    trading_cycle_result = trading_cycle_result if isinstance(trading_cycle_result, dict) else {}
    permission_gate_audit = permission_gate_audit if isinstance(permission_gate_audit, dict) else {}
    paper_risk_level_report = paper_risk_level_report if isinstance(paper_risk_level_report, dict) else {}

    permission_gate = trading_cycle_result.get("permission_gate", {})
    if not isinstance(permission_gate, dict):
        permission_gate = {}

    latest_report_gate = paper_risk_level_report.get("latest_permission_gate", {})
    if not isinstance(latest_report_gate, dict):
        latest_report_gate = {}

    source = permission_gate or permission_gate_audit or latest_report_gate
    if not isinstance(source, dict):
        source = {}

    block_reasons = first_non_empty(
        source.get("block_reasons"),
        permission_gate_audit.get("block_reasons"),
        default=[],
    )
    risk_warnings = first_non_empty(
        source.get("risk_warnings"),
        permission_gate_audit.get("risk_warnings"),
        default=[],
    )

    if not isinstance(block_reasons, list):
        block_reasons = [str(block_reasons)] if block_reasons != "-" else []
    if not isinstance(risk_warnings, list):
        risk_warnings = [str(risk_warnings)] if risk_warnings != "-" else []

    by_risk = paper_risk_level_report.get("by_risk_level", {})
    if not isinstance(by_risk, dict):
        by_risk = {}

    return {
        "applied": first_non_empty(source.get("applied"), source.get("permission_gate_applied"), default="-"),
        "allow_long": first_non_empty(source.get("allow_long"), default="-"),
        "allow_short": first_non_empty(source.get("allow_short"), default="-"),
        "allow_new_position": first_non_empty(source.get("allow_new_position"), default="-"),
        "risk_level": first_non_empty(source.get("risk_level"), default="-"),
        "position_size_multiplier": first_non_empty(source.get("position_size_multiplier"), default="-"),
        "research_signal_id": first_non_empty(source.get("research_signal_id"), default="-"),
        "block_reasons": block_reasons,
        "risk_warnings": risk_warnings,
        "blocked_total": first_non_empty(paper_risk_level_report.get("total_blocked_by_permission_gate"), default="-"),
        "opened_total": first_non_empty(paper_risk_level_report.get("total_position_opened"), default="-"),
        "by_risk_level": by_risk,
    }



def format_signed_score(value: Any) -> str:
    try:
        return f"{float(value):+.2f}"
    except Exception:
        return "-"


def format_ratio_pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:+.2f}%"
    except Exception:
        return "-"


def extract_extra_data_summary(research_cycle_result: Dict[str, Any]) -> Dict[str, Any]:
    research_cycle_result = research_cycle_result if isinstance(research_cycle_result, dict) else {}
    signal = research_cycle_result.get("research_signal", {})
    if not isinstance(signal, dict):
        signal = {}
    snapshot = research_cycle_result.get("snapshot", {})
    if not isinstance(snapshot, dict):
        snapshot = {}
    features = signal.get("features", {})
    if not isinstance(features, dict):
        features = {}
    components = signal.get("score_components", {})
    if not isinstance(components, dict):
        components = {}

    return {
        "binance_derivatives_score": first_non_empty(features.get("binance_derivatives_score"), snapshot.get("binance_derivatives_score"), default="-"),
        "exchange_flow_score": first_non_empty(features.get("exchange_flow_score"), snapshot.get("exchange_flow_score"), default="-"),
        "etf_flow_score": first_non_empty(features.get("etf_flow_score"), snapshot.get("etf_flow_score"), default="-"),
        "stablecoin_liquidity_score": first_non_empty(features.get("stablecoin_liquidity_score"), snapshot.get("stablecoin_liquidity_score"), default="-"),
        "exchange_netflow_zscore_30d": first_non_empty(features.get("exchange_netflow_zscore_30d"), snapshot.get("exchange_netflow_zscore_30d"), default="-"),
        "etf_flow_5d": first_non_empty(features.get("etf_flow_5d"), snapshot.get("etf_flow_5d_sum"), default="-"),
        "stablecoin_supply_change_7d": first_non_empty(features.get("stablecoin_supply_change_7d"), snapshot.get("stablecoin_total_mcap_7d_change"), default="-"),
        "score_derivatives": first_non_empty(components.get("derivatives"), snapshot.get("score_derivatives"), default="-"),
        "score_exchange_flow": first_non_empty(components.get("exchange_flow"), snapshot.get("score_exchange_flow"), default="-"),
        "score_etf_flow": first_non_empty(components.get("etf_flow"), snapshot.get("score_etf_flow"), default="-"),
        "score_stablecoin_liquidity": first_non_empty(components.get("stablecoin_liquidity"), snapshot.get("score_stablecoin_liquidity"), default="-"),
        "score_risk": first_non_empty(components.get("risk"), snapshot.get("score_risk"), default="-"),
    }

def _format_list_for_telegram(values: Any) -> str:
    if not values:
        return "-"
    if isinstance(values, list):
        return ", ".join(str(x) for x in values[:5]) if values else "-"
    return str(values)


def _risk_bucket_count(by_risk_level: Dict[str, Any], level: str, key: str) -> Any:
    bucket = by_risk_level.get(level, {}) if isinstance(by_risk_level, dict) else {}
    if not isinstance(bucket, dict):
        return "-"
    return bucket.get(key, 0)

# ============================================================
# Telegram Message Builder
# ============================================================

def build_daily_telegram_message(
    daily_report: Dict[str, Any],
    research_cycle_result: Dict[str, Any],
    paper_report: Dict[str, Any],
    scheduler_health: Dict[str, Any],
    markdown_report_result: Dict[str, Any],
    signal_quality_report: Dict[str, Any],
    signal_calibration_advice: Dict[str, Any],
    trading_cycle_result: Dict[str, Any] | None = None,
    permission_gate_audit: Dict[str, Any] | None = None,
    paper_risk_level_report: Dict[str, Any] | None = None,
) -> str:
    report_date = first_non_empty(
        daily_report.get("report_date"),
        research_cycle_result.get("report_date"),
        datetime.now(timezone.utc).date().isoformat(),
    )

    current_price = first_non_empty(
        daily_report.get("current_price"),
        research_cycle_result.get("current_price"),
        scheduler_health.get("current_price"),
        paper_report.get("current_price"),
        default="-",
    )

    market_bias = first_non_empty(
        daily_report.get("market_bias"),
        research_cycle_result.get("market_bias"),
        default="-",
    )

    research_score = first_non_empty(
        daily_report.get("research_score"),
        research_cycle_result.get("research_score"),
        default="-",
    )

    summary = extract_summary(
        daily_report=daily_report,
        research_cycle_result=research_cycle_result,
    )

    base_case = summary["base_case"]
    key_reason = summary["key_reason"]
    risk_note = summary["risk_note"]

    signal = paper_report.get("signal", {})
    if not isinstance(signal, dict):
        signal = {}

    trading_cycle_signal = {}
    if isinstance(scheduler_health.get("signal"), dict):
        trading_cycle_signal = scheduler_health.get("signal", {})

    signal_side = first_non_empty(
        signal.get("side"),
        paper_report.get("side"),
        trading_cycle_signal.get("side"),
        default="-",
    )

    signal_confidence = first_non_empty(
        signal.get("confidence"),
        paper_report.get("confidence"),
        trading_cycle_signal.get("confidence"),
        default="-",
    )

    signal_reason = first_non_empty(
        signal.get("reason"),
        paper_report.get("reason"),
        default="-",
    )

    position_opened = safe_get(paper_report, "position_opened", "-")
    paper_mode = safe_get(paper_report, "mode", "-")

    trade_permission = extract_trade_permission(
        trading_cycle_result=trading_cycle_result,
        permission_gate_audit=permission_gate_audit,
        paper_risk_level_report=paper_risk_level_report,
    )

    scheduler_status = safe_get(scheduler_health, "status", "-")
    operational_dry_run = safe_get(scheduler_health, "operational_dry_run", "-")
    trading_cycle = safe_get(scheduler_health, "trading_cycle", "-")
    trading_bot = safe_get(scheduler_health, "trading_bot", "-")
    spreadsheet = safe_get(scheduler_health, "spreadsheet", "-")
    telegram_status = safe_get(scheduler_health, "telegram", "-")

    markdown_status = first_non_empty(
        markdown_report_result.get("status"),
        scheduler_health.get("markdown_report"),
        default="-",
    )

    error_failures = scheduler_health.get("error_failures", [])
    warning_failures = scheduler_health.get("warning_failures", [])

    error_count = len(error_failures) if isinstance(error_failures, list) else "-"
    warning_count = len(warning_failures) if isinstance(warning_failures, list) else "-"

    signal_quality = extract_signal_quality(signal_quality_report)
    calibration_advice = extract_calibration_advice(signal_calibration_advice)
    extra_data = extract_extra_data_summary(research_cycle_result)

    message_lines = [
        "[Crypto AI Daily Report]",
        "",
        f"Date: {report_date}",
        f"Price: {format_price(current_price)}",
        "",
        "[Market View]",
        f"Bias: {market_bias}",
        f"Research Score: {format_score(research_score)}",
        f"Base Case: {base_case}",
        "",
        "[Trading Signal]",
        f"Signal: {signal_side}",
        f"Confidence: {format_confidence(signal_confidence)}",
        f"Position Opened: {format_bool(position_opened)}",
        f"Mode: {paper_mode}",
        "",
        "[Extra Data Summary]",
        f"Derivatives Score: {format_signed_score(extra_data['binance_derivatives_score'])}",
        f"Exchange Flow Score: {format_signed_score(extra_data['exchange_flow_score'])}",
        f"ETF Flow Score: {format_signed_score(extra_data['etf_flow_score'])}",
        f"Stablecoin Liquidity Score: {format_signed_score(extra_data['stablecoin_liquidity_score'])}",
        f"Exchange Netflow Z 30D: {format_signed_score(extra_data['exchange_netflow_zscore_30d'])}",
        f"ETF Flow 5D: {extra_data['etf_flow_5d']}",
        f"Stablecoin Supply 7D: {format_ratio_pct(extra_data['stablecoin_supply_change_7d'])}",
        "",
        "[Trade Permission]",
        f"Gate Applied: {format_bool(trade_permission['applied'])}",
        f"Allow Long: {format_bool(trade_permission['allow_long'])}",
        f"Allow Short: {format_bool(trade_permission['allow_short'])}",
        f"Allow New Position: {format_bool(trade_permission['allow_new_position'])}",
        f"Risk Level: {trade_permission['risk_level']}",
        f"Position Size Multiplier: {trade_permission['position_size_multiplier']}",
        f"Research Signal ID: {trade_permission['research_signal_id']}",
        f"Block Reasons: {_format_list_for_telegram(trade_permission['block_reasons'])}",
        f"Risk Warnings: {_format_list_for_telegram(trade_permission['risk_warnings'])}",
        "",
        "[Paper Risk-Level Report]",
        f"Opened Total: {trade_permission['opened_total']}",
        f"Blocked Total: {trade_permission['blocked_total']}",
        f"Normal Attempts: {_risk_bucket_count(trade_permission['by_risk_level'], 'normal', 'audit_count')}",
        f"Reduced Attempts: {_risk_bucket_count(trade_permission['by_risk_level'], 'reduced', 'audit_count')}",
        f"Blocked Attempts: {_risk_bucket_count(trade_permission['by_risk_level'], 'blocked', 'audit_count')}",
        "",
        "[Reason]",
        f"Key Reason: {key_reason}",
        f"Signal Reason: {signal_reason}",
        "",
        "[Risk Note]",
        str(risk_note),
        "",
        "[System Health]",
        f"Scheduler: {scheduler_status}",
        f"Operational Dry Run: {operational_dry_run}",
        f"Trading Cycle: {trading_cycle}",
        f"Trading Bot: {trading_bot}",
        f"Spreadsheet: {spreadsheet}",
        f"Telegram: {telegram_status}",
        f"Markdown Report: {markdown_status}",
        f"Errors: {error_count}",
        f"Warnings: {warning_count}",
        "",
        "[Signal Quality]",
        f"Status: {signal_quality['status']}",
        f"Overall Score: {signal_quality['overall_score']}/100",
        f"Total Records: {signal_quality['total_records']}",
        f"Watch Ratio: {format_pct(signal_quality['watch_ratio'])}",
        f"Directional Ratio: {format_pct(signal_quality['directional_ratio'])}",
        f"Unknown Ratio: {format_pct(signal_quality['unknown_ratio'])}",
        f"Signal Counts: WATCH={signal_quality['watch_count']}, LONG={signal_quality['long_count']}, SHORT={signal_quality['short_count']}",
        "",
        "[Calibration Advice]",
        f"Action: {calibration_advice['action']}",
        f"Confidence: {calibration_advice['confidence']}",
        f"Recent Watch Streak: {calibration_advice['recent_watch_streak']}",
        f"Watch Ratio: {format_pct(calibration_advice['watch_ratio'])}",
        f"Directional Ratio: {format_pct(calibration_advice['directional_ratio'])}",
        f"Top Recommendation: {calibration_advice['top_recommendation']}",
    ]

    return "\n".join(message_lines)


# ============================================================
# Save Builder Result
# ============================================================

def build_and_save_daily_telegram_message(
    storage_dir: str | Path = "storage",
) -> Dict[str, Any]:
    storage_path = Path(storage_dir)
    storage_path.mkdir(parents=True, exist_ok=True)

    daily_report_path = latest_daily_report_file(storage_path)

    daily_report = load_json_file(daily_report_path)
    research_cycle_result = load_json_file(storage_path / "research_cycle_result.json")
    paper_report = load_json_file(storage_path / "paper_performance_report.json")
    scheduler_health = load_json_file(storage_path / "scheduler_health_result.json")
    markdown_report_result = load_json_file(storage_path / "daily_markdown_report_result.json")
    signal_quality_report = load_json_file(storage_path / "signal_quality_report.json")
    signal_calibration_advice = load_json_file(storage_path / "signal_calibration_advice.json")
    trading_cycle_result = load_json_file(storage_path / "latest" / "trading_cycle_result.json")
    permission_gate_audit = load_json_file(storage_path / "latest" / "permission_gate_audit_latest.json")
    paper_risk_level_report = load_json_file(storage_path / "latest" / "paper_risk_level_report.json")

    message = build_daily_telegram_message(
        daily_report=daily_report,
        research_cycle_result=research_cycle_result,
        paper_report=paper_report,
        scheduler_health=scheduler_health,
        markdown_report_result=markdown_report_result,
        signal_quality_report=signal_quality_report,
        signal_calibration_advice=signal_calibration_advice,
        trading_cycle_result=trading_cycle_result,
        permission_gate_audit=permission_gate_audit,
        paper_risk_level_report=paper_risk_level_report,
    )

    result = {
        "name": "TELEGRAM_SUMMARY_BUILDER",
        "status": "MESSAGE_BUILT",
        "message": message,
        "message_length": len(message),
        "source_daily_report": str(daily_report_path) if daily_report_path else None,
        "source_signal_quality_report": str(storage_path / "signal_quality_report.json"),
        "source_signal_calibration_advice": str(storage_path / "signal_calibration_advice.json"),
        "daily_report_quality_score": daily_report_quality_score(daily_report),
        "timestamp_utc": now_utc(),
    }

    result_path = storage_path / "telegram_daily_report_message.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    txt_path = storage_path / "telegram_daily_report_message.txt"
    txt_path.write_text(message, encoding="utf-8")

    return result


# ============================================================
# Backward-Compatible Functions
# ============================================================

def build_telegram_summary(storage_dir: str | Path = "storage") -> str:
    result = build_and_save_daily_telegram_message(storage_dir=storage_dir)
    return str(result.get("message", ""))


def build_telegram_alert(*args: Any, **kwargs: Any) -> str:
    storage_dir = kwargs.get("storage_dir", "storage")
    result = build_and_save_daily_telegram_message(storage_dir=storage_dir)
    return str(result.get("message", ""))


def build_alert(*args: Any, **kwargs: Any) -> str:
    return build_telegram_alert(*args, **kwargs)


# ============================================================
# Main
# ============================================================

def main() -> None:
    result = build_and_save_daily_telegram_message(storage_dir="storage")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
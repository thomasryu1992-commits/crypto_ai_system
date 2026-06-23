from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


# ============================================================
# Project Paths
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

STORAGE_DIR = PROJECT_ROOT / os.getenv("STORAGE_DIR", "storage")


# ============================================================
# Console Safety
# ============================================================

def configure_utf8_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def safe_print(value: Any = "") -> None:
    text = "" if value is None else str(value)

    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe_text = text.encode(encoding, errors="backslashreplace").decode(
            encoding,
            errors="replace",
        )
        print(safe_text)


configure_utf8_console()


# ============================================================
# Helpers
# ============================================================

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_storage() -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def load_json_file(path: Path) -> Dict[str, Any]:
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


def write_json_file(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def first_non_empty(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is None:
            continue

        if isinstance(value, str) and not value.strip():
            continue

        return value

    return default


def normalize_status(value: Any) -> str:
    if value is None:
        return "UNKNOWN"

    return str(value).strip().upper()


def latest_daily_report_file() -> Optional[Path]:
    reports_dir = STORAGE_DIR / "reports"

    candidates = []
    candidates.extend(STORAGE_DIR.glob("daily_report_*.json"))
    candidates.extend(reports_dir.glob("daily_report_*.json"))

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

    candidates = sorted(
        candidates,
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    return candidates[0]


def get_current_price(
    market_snapshot: Dict[str, Any],
    market_context: Dict[str, Any],
    research_cycle_result: Dict[str, Any],
    daily_report: Dict[str, Any],
    paper_report: Dict[str, Any],
) -> Any:
    return first_non_empty(
        market_snapshot.get("current_price"),
        market_snapshot.get("price"),
        market_context.get("current_price"),
        market_context.get("price"),
        research_cycle_result.get("current_price"),
        daily_report.get("current_price"),
        paper_report.get("current_price"),
        default=None,
    )


def get_research_score(
    research_cycle_result: Dict[str, Any],
    daily_report: Dict[str, Any],
) -> Any:
    return first_non_empty(
        research_cycle_result.get("research_score"),
        daily_report.get("research_score"),
        default=None,
    )


def get_market_bias(
    market_context: Dict[str, Any],
    research_cycle_result: Dict[str, Any],
    daily_report: Dict[str, Any],
) -> str:
    return str(
        first_non_empty(
            market_context.get("market_bias"),
            research_cycle_result.get("market_bias"),
            daily_report.get("market_bias"),
            default="neutral",
        )
    )


def get_decision_type(
    research_decision: Dict[str, Any],
    dynamic_setup: Dict[str, Any],
    daily_report: Dict[str, Any],
) -> str:
    summary = daily_report.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    return str(
        first_non_empty(
            research_decision.get("decision_type"),
            research_decision.get("type"),
            research_decision.get("base_case"),
            dynamic_setup.get("research_decision_type"),
            dynamic_setup.get("decision_type"),
            summary.get("base_case"),
            default="CONDITIONAL_WATCH",
        )
    )


def build_paper_signal(
    market_bias: str,
    research_score: Any,
    decision_type: str,
) -> Dict[str, Any]:
    decision_upper = normalize_status(decision_type)
    bias_upper = normalize_status(market_bias)

    try:
        score = int(research_score)
    except Exception:
        score = 50

    if "WATCH" in decision_upper or "CONDITIONAL" in decision_upper:
        return {
            "side": "WATCH",
            "confidence": 0.52,
            "reason": "Research decision requires conditional confirmation.",
        }

    if score >= 70 and bias_upper in {"BULLISH", "LONG", "UP"}:
        return {
            "side": "LONG",
            "confidence": min(0.95, score / 100),
            "reason": "Bullish bias and high research score detected.",
        }

    if score <= 30 and bias_upper in {"BEARISH", "SHORT", "DOWN"}:
        return {
            "side": "SHORT",
            "confidence": min(0.95, (100 - score) / 100),
            "reason": "Bearish bias and low research score detected.",
        }

    return {
        "side": "WATCH",
        "confidence": 0.50,
        "reason": "No high-confidence directional setup detected.",
    }


def build_telegram_skipped_result() -> Dict[str, Any]:
    return {
        "name": "TELEGRAM_ALERT",
        "status": "SKIPPED_BY_DAILY_REPORT_MODE",
        "ok": True,
        "reason": "Telegram sending is handled by check_scheduler_health.py using the daily report format.",
        "timestamp_utc": now_utc(),
    }


# ============================================================
# Main Trading Cycle
# ============================================================

def run_trading_cycle() -> Dict[str, Any]:
    ensure_storage()

    started_at = now_utc()

    market_snapshot = load_json_file(STORAGE_DIR / "market_snapshot.json")
    market_context = load_json_file(STORAGE_DIR / "market_context.json")
    research_cycle_result = load_json_file(STORAGE_DIR / "research_cycle_result.json")
    dynamic_setup = load_json_file(STORAGE_DIR / "dynamic_setup_result.json")
    research_decision = load_json_file(STORAGE_DIR / "research_decision_result.json")
    existing_paper_report = load_json_file(STORAGE_DIR / "paper_performance_report.json")

    daily_report_path = latest_daily_report_file()
    daily_report = load_json_file(daily_report_path) if daily_report_path else {}

    current_price = get_current_price(
        market_snapshot=market_snapshot,
        market_context=market_context,
        research_cycle_result=research_cycle_result,
        daily_report=daily_report,
        paper_report=existing_paper_report,
    )

    market_bias = get_market_bias(
        market_context=market_context,
        research_cycle_result=research_cycle_result,
        daily_report=daily_report,
    )

    research_score = get_research_score(
        research_cycle_result=research_cycle_result,
        daily_report=daily_report,
    )

    decision_type = get_decision_type(
        research_decision=research_decision,
        dynamic_setup=dynamic_setup,
        daily_report=daily_report,
    )

    signal = build_paper_signal(
        market_bias=market_bias,
        research_score=research_score,
        decision_type=decision_type,
    )

    trading_mode = os.getenv("TRADING_MODE", "paper").strip().lower() or "paper"

    position_opened = False
    execution_reason = "Dry-run/paper-watch mode only."

    paper_report = {
        "name": "PAPER_WATCH_MANAGER",
        "status": "PAPER_PERFORMANCE_UPDATED",
        "mode": "paper",
        "signal": signal,
        "current_price": current_price,
        "market_bias": market_bias,
        "research_score": research_score,
        "decision_type": decision_type,
        "position_opened": position_opened,
        "reason": execution_reason,
        "timestamp_utc": now_utc(),
    }

    write_json_file(STORAGE_DIR / "paper_performance_report.json", paper_report)

    telegram_result = build_telegram_skipped_result()
    write_json_file(STORAGE_DIR / "telegram_alert_result.json", telegram_result)

    trading_cycle_result = {
        "name": "TRADING_CYCLE",
        "status": "CYCLE_COMPLETED",
        "mode": trading_mode,
        "current_price": current_price,
        "market_bias": market_bias,
        "research_score": research_score,
        "decision_type": decision_type,
        "signal": signal,
        "position_opened": position_opened,
        "paper_performance": paper_report.get("status"),
        "telegram_alert": telegram_result.get("status"),
        "started_at_utc": started_at,
        "finished_at_utc": now_utc(),
        "source_daily_report": str(daily_report_path) if daily_report_path else None,
        "files": {
            "trading_cycle_result": str(STORAGE_DIR / "trading_cycle_result.json"),
            "paper_performance_report": str(STORAGE_DIR / "paper_performance_report.json"),
            "telegram_alert_result": str(STORAGE_DIR / "telegram_alert_result.json"),
        },
    }

    write_json_file(STORAGE_DIR / "trading_cycle_result.json", trading_cycle_result)

    return trading_cycle_result


def main() -> None:
    try:
        result = run_trading_cycle()

        safe_print("[TRADING_CYCLE]")
        safe_print(f"Status: {result.get('status')}")
        safe_print(f"Current Price: {result.get('current_price')}")
        safe_print(f"Market Bias: {result.get('market_bias')}")
        safe_print(f"Research Score: {result.get('research_score')}")
        safe_print(f"Decision Type: {result.get('decision_type')}")
        safe_print(f"Signal: {result.get('signal', {}).get('side')}")
        safe_print(f"Trading Bot: {result.get('paper_performance')}")
        safe_print(f"Telegram Alert: {result.get('telegram_alert')}")
        safe_print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as exc:
        error_result = {
            "name": "TRADING_CYCLE",
            "status": "CYCLE_FAILED",
            "error": str(exc),
            "traceback": traceback.format_exc()[-4000:],
            "timestamp_utc": now_utc(),
        }

        write_json_file(STORAGE_DIR / "trading_cycle_result.json", error_result)
        safe_print(json.dumps(error_result, ensure_ascii=False, indent=2))
        raise


if __name__ == "__main__":
    main()
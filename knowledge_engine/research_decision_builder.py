from __future__ import annotations

import json
import os
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STORAGE_DIR = PROJECT_ROOT / "storage"
KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"
WIKI_DIR = KNOWLEDGE_BASE_DIR / "wiki"

MARKET_CONTEXT_PATH = STORAGE_DIR / "market_context.json"
MARKET_SNAPSHOT_PATH = STORAGE_DIR / "market_snapshot.json"
DYNAMIC_SETUP_RESULT_PATH = STORAGE_DIR / "dynamic_setup_result.json"
RESEARCH_DECISION_PATH = STORAGE_DIR / "research_decision.json"
RESEARCH_DECISION_LOG_PATH = STORAGE_DIR / "research_decision_log.json"
KB_LINT_RESULT_PATH = KNOWLEDGE_BASE_DIR / "lint" / "kb_lint_result.json"


def build_research_decision() -> Dict[str, Any]:
    """
    Step 62:
    Dynamic Setup -> Research Decision Builder

    Decision priority:
    1. dynamic_setup_result.json with DYNAMIC_SETUP_CREATED
    2. dynamic_setup_result.json with OBSERVE_ONLY -> OBSERVE_ONLY research decision
    3. latest daily report conditional setup
    4. FALLBACK_ strategy values from .env
    5. OBSERVE_ONLY if no valid setup exists

    Trading Bot should only read:
    - storage/research_decision.json
    """

    load_dotenv(PROJECT_ROOT / ".env")
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    started_at = _now_utc_iso()

    try:
        market_context = _load_json(MARKET_CONTEXT_PATH, default={})
        market_snapshot = _load_json(MARKET_SNAPSHOT_PATH, default={})
        dynamic_setup_result = _load_json(DYNAMIC_SETUP_RESULT_PATH, default={})
        kb_lint_result = _load_json(KB_LINT_RESULT_PATH, default={})
        latest_report_path = _find_latest_daily_report()

        kb_lint_status = kb_lint_result.get("status")
        current_price = _extract_current_price(market_context, market_snapshot)

        if kb_lint_status in {"ERROR", "FAILED"}:
            result = _build_observe_only_decision(
                started_at=started_at,
                decision_source="kb_lint",
                reason=f"KB lint status is {kb_lint_status}. Trading decision blocked.",
                market_context=market_context,
                market_snapshot=market_snapshot,
                dynamic_setup_result=dynamic_setup_result,
                kb_lint_result=kb_lint_result,
                latest_report_path=latest_report_path,
                status="RESEARCH_DECISION_BLOCKED_BY_KB_LINT",
            )
            _save_and_log(result)
            return result

        decision = _build_from_dynamic_setup(
            started_at=started_at,
            dynamic_setup_result=dynamic_setup_result,
            market_context=market_context,
            market_snapshot=market_snapshot,
            kb_lint_result=kb_lint_result,
            latest_report_path=latest_report_path,
            current_price=current_price,
        )

        if decision is not None:
            _save_and_log(decision)
            return decision

        decision = _build_from_latest_report(
            started_at=started_at,
            latest_report_path=latest_report_path,
            market_context=market_context,
            market_snapshot=market_snapshot,
            dynamic_setup_result=dynamic_setup_result,
            kb_lint_result=kb_lint_result,
            current_price=current_price,
        )

        if decision is not None:
            _save_and_log(decision)
            return decision

        decision = _build_from_fallback(
            started_at=started_at,
            market_context=market_context,
            market_snapshot=market_snapshot,
            dynamic_setup_result=dynamic_setup_result,
            kb_lint_result=kb_lint_result,
            latest_report_path=latest_report_path,
            current_price=current_price,
        )

        _save_and_log(decision)
        return decision

    except Exception as error:
        result = {
            "step": "STEP_62_RESEARCH_DECISION_BUILDER",
            "status": "ERROR",
            "decision_type": "NO_DECISION",
            "decision_source": "research_decision_builder_error",
            "timestamp_utc": _now_utc_iso(),
            "started_at_utc": started_at,
            "finished_at_utc": _now_utc_iso(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "conditional_setup": None,
            "safety": {
                "order_execution": False,
                "paper_watch_created": False,
                "live_trading_enabled": False,
            },
            "files": _result_files(latest_report_path=None),
        }

        _save_and_log(result)
        return result


def _build_from_dynamic_setup(
    started_at: str,
    dynamic_setup_result: Dict[str, Any],
    market_context: Dict[str, Any],
    market_snapshot: Dict[str, Any],
    kb_lint_result: Dict[str, Any],
    latest_report_path: Optional[Path],
    current_price: Optional[float],
) -> Optional[Dict[str, Any]]:
    dynamic_enabled = _env_bool("DYNAMIC_SETUP_ENABLED", True)

    if not dynamic_enabled:
        return None

    if not isinstance(dynamic_setup_result, dict) or not dynamic_setup_result:
        return None

    dynamic_status = dynamic_setup_result.get("status")
    dynamic_decision_type = dynamic_setup_result.get("decision_type")

    if dynamic_status == "DYNAMIC_SETUP_CREATED":
        conditional_setup = dynamic_setup_result.get("conditional_setup")

        if not _is_valid_conditional_setup(conditional_setup):
            return _build_observe_only_decision(
                started_at=started_at,
                decision_source="dynamic_setup_generator",
                reason="Dynamic setup result exists but conditional_setup is invalid.",
                market_context=market_context,
                market_snapshot=market_snapshot,
                dynamic_setup_result=dynamic_setup_result,
                kb_lint_result=kb_lint_result,
                latest_report_path=latest_report_path,
                status="RESEARCH_DECISION_CREATED_WITH_WARNINGS",
            )

        normalized_setup = _normalize_conditional_setup(conditional_setup)

        return {
            "step": "STEP_62_RESEARCH_DECISION_BUILDER",
            "status": "RESEARCH_DECISION_CREATED",
            "decision_type": "CONDITIONAL_WATCH",
            "decision_source": "dynamic_setup_generator",
            "timestamp_utc": _now_utc_iso(),
            "started_at_utc": started_at,
            "finished_at_utc": _now_utc_iso(),
            "symbol": normalized_setup.get("symbol") or market_snapshot.get("symbol") or market_context.get("symbol") or "BTCUSDT",
            "current_price": current_price,
            "trading_bias": _trading_bias_from_direction(normalized_setup.get("direction")),
            "confidence": dynamic_setup_result.get("confidence", normalized_setup.get("confidence", "medium")),
            "kb_lint_status": kb_lint_result.get("status"),
            "source_report": str(latest_report_path) if latest_report_path else None,
            "active_scenario": _extract_active_scenario_from_dynamic(dynamic_setup_result),
            "conditional_setup": normalized_setup,
            "risk_notes": _build_risk_notes(
                source="dynamic_setup_generator",
                dynamic_setup_result=dynamic_setup_result,
            ),
            "evidence": {
                "decision_source": "dynamic_setup_generator",
                "entities": ["BTC"],
                "concepts": [
                    "open_interest",
                    "funding_rate",
                    "long_short_ratio",
                    "liquidation",
                    "price_action",
                ],
                "sources": ["coinalyze", "market_snapshot"],
                "scenarios": [_extract_active_scenario_from_dynamic(dynamic_setup_result)],
            },
            "dynamic_setup_summary": _compact_dynamic_setup(dynamic_setup_result),
            "market_snapshot_summary": _compact_market_snapshot(market_snapshot),
            "safety": {
                "order_execution": False,
                "paper_watch_created": False,
                "live_trading_enabled": False,
            },
            "files": _result_files(latest_report_path),
        }

    if dynamic_status == "OBSERVE_ONLY" or dynamic_decision_type == "OBSERVE_ONLY":
        return _build_observe_only_decision(
            started_at=started_at,
            decision_source="dynamic_setup_generator",
            reason=dynamic_setup_result.get("reason") or "Dynamic setup generator returned OBSERVE_ONLY.",
            market_context=market_context,
            market_snapshot=market_snapshot,
            dynamic_setup_result=dynamic_setup_result,
            kb_lint_result=kb_lint_result,
            latest_report_path=latest_report_path,
            status="RESEARCH_DECISION_CREATED",
        )

    if dynamic_status == "ERROR":
        return _build_observe_only_decision(
            started_at=started_at,
            decision_source="dynamic_setup_generator",
            reason=f"Dynamic setup generator returned ERROR: {dynamic_setup_result.get('error_message')}",
            market_context=market_context,
            market_snapshot=market_snapshot,
            dynamic_setup_result=dynamic_setup_result,
            kb_lint_result=kb_lint_result,
            latest_report_path=latest_report_path,
            status="RESEARCH_DECISION_CREATED_WITH_WARNINGS",
        )

    return None


def _build_from_latest_report(
    started_at: str,
    latest_report_path: Optional[Path],
    market_context: Dict[str, Any],
    market_snapshot: Dict[str, Any],
    dynamic_setup_result: Dict[str, Any],
    kb_lint_result: Dict[str, Any],
    current_price: Optional[float],
) -> Optional[Dict[str, Any]]:
    if latest_report_path is None or not latest_report_path.exists():
        return None

    text = latest_report_path.read_text(encoding="utf-8", errors="replace")
    setup = _extract_conditional_setup_from_report(text)

    if not _is_valid_conditional_setup(setup):
        return None

    normalized_setup = _normalize_conditional_setup(setup)

    return {
        "step": "STEP_62_RESEARCH_DECISION_BUILDER",
        "status": "RESEARCH_DECISION_CREATED",
        "decision_type": "CONDITIONAL_WATCH",
        "decision_source": "daily_report",
        "timestamp_utc": _now_utc_iso(),
        "started_at_utc": started_at,
        "finished_at_utc": _now_utc_iso(),
        "symbol": normalized_setup.get("symbol") or market_snapshot.get("symbol") or market_context.get("symbol") or "BTCUSDT",
        "current_price": current_price,
        "trading_bias": _trading_bias_from_direction(normalized_setup.get("direction")),
        "confidence": "medium",
        "kb_lint_status": kb_lint_result.get("status"),
        "source_report": str(latest_report_path),
        "conditional_setup": normalized_setup,
        "risk_notes": [
            "Setup was extracted from the latest daily report.",
            "Confirm market snapshot before trading cycle.",
        ],
        "evidence": {
            "decision_source": "daily_report",
            "entities": ["BTC"],
            "concepts": ["report_conditional_setup"],
            "sources": ["wiki_report"],
            "scenarios": [],
        },
        "dynamic_setup_summary": _compact_dynamic_setup(dynamic_setup_result),
        "market_snapshot_summary": _compact_market_snapshot(market_snapshot),
        "safety": {
            "order_execution": False,
            "paper_watch_created": False,
            "live_trading_enabled": False,
        },
        "files": _result_files(latest_report_path),
    }


def _build_from_fallback(
    started_at: str,
    market_context: Dict[str, Any],
    market_snapshot: Dict[str, Any],
    dynamic_setup_result: Dict[str, Any],
    kb_lint_result: Dict[str, Any],
    latest_report_path: Optional[Path],
    current_price: Optional[float],
) -> Dict[str, Any]:
    fallback_allowed = _env_bool("ALLOW_FALLBACK_RESEARCH_DECISION", True)

    if not fallback_allowed:
        return _build_observe_only_decision(
            started_at=started_at,
            decision_source="fallback_disabled",
            reason="No dynamic setup or report setup found, and fallback research decision is disabled.",
            market_context=market_context,
            market_snapshot=market_snapshot,
            dynamic_setup_result=dynamic_setup_result,
            kb_lint_result=kb_lint_result,
            latest_report_path=latest_report_path,
            status="RESEARCH_DECISION_CREATED",
        )

    setup = {
        "symbol": market_snapshot.get("symbol") or market_context.get("symbol") or "BTCUSDT",
        "setup_type": os.getenv("FALLBACK_SETUP_TYPE", "breakout_reclaim"),
        "direction": os.getenv("FALLBACK_SETUP_DIRECTION", "long"),
        "trigger_price": _env_float("FALLBACK_TRIGGER_PRICE", 107500.0),
        "invalidation_price": _env_float("FALLBACK_INVALIDATION_PRICE", 106200.0),
        "take_profit": _env_float("FALLBACK_TAKE_PROFIT", 110000.0),
        "expires_after_hours": _env_int("FALLBACK_EXPIRES_AFTER_HOURS", 24),
        "confidence": "low",
        "source": "fallback_strategy_values",
        "created_at_utc": _now_utc_iso(),
    }

    if not _is_valid_conditional_setup(setup):
        return _build_observe_only_decision(
            started_at=started_at,
            decision_source="fallback_strategy_values",
            reason="Fallback strategy values are invalid.",
            market_context=market_context,
            market_snapshot=market_snapshot,
            dynamic_setup_result=dynamic_setup_result,
            kb_lint_result=kb_lint_result,
            latest_report_path=latest_report_path,
            status="RESEARCH_DECISION_CREATED_WITH_WARNINGS",
        )

    normalized_setup = _normalize_conditional_setup(setup)

    return {
        "step": "STEP_62_RESEARCH_DECISION_BUILDER",
        "status": "RESEARCH_DECISION_CREATED_WITH_WARNINGS",
        "decision_type": "CONDITIONAL_WATCH",
        "decision_source": "fallback_strategy_values",
        "timestamp_utc": _now_utc_iso(),
        "started_at_utc": started_at,
        "finished_at_utc": _now_utc_iso(),
        "symbol": normalized_setup.get("symbol"),
        "current_price": current_price,
        "trading_bias": _trading_bias_from_direction(normalized_setup.get("direction")),
        "confidence": "low",
        "kb_lint_status": kb_lint_result.get("status"),
        "source_report": str(latest_report_path) if latest_report_path else None,
        "conditional_setup": normalized_setup,
        "risk_notes": [
            "Fallback setup was used because dynamic setup and report setup were unavailable.",
            "This should be treated as low-confidence and mainly for continuity/testing.",
        ],
        "evidence": {
            "decision_source": "fallback_strategy_values",
            "entities": ["BTC"],
            "concepts": ["fallback"],
            "sources": [".env"],
            "scenarios": [],
        },
        "dynamic_setup_summary": _compact_dynamic_setup(dynamic_setup_result),
        "market_snapshot_summary": _compact_market_snapshot(market_snapshot),
        "safety": {
            "order_execution": False,
            "paper_watch_created": False,
            "live_trading_enabled": False,
        },
        "files": _result_files(latest_report_path),
    }


def _build_observe_only_decision(
    started_at: str,
    decision_source: str,
    reason: str,
    market_context: Dict[str, Any],
    market_snapshot: Dict[str, Any],
    dynamic_setup_result: Dict[str, Any],
    kb_lint_result: Dict[str, Any],
    latest_report_path: Optional[Path],
    status: str = "RESEARCH_DECISION_CREATED",
) -> Dict[str, Any]:
    current_price = _extract_current_price(market_context, market_snapshot)

    return {
        "step": "STEP_62_RESEARCH_DECISION_BUILDER",
        "status": status,
        "decision_type": "OBSERVE_ONLY",
        "decision_source": decision_source,
        "timestamp_utc": _now_utc_iso(),
        "started_at_utc": started_at,
        "finished_at_utc": _now_utc_iso(),
        "symbol": market_snapshot.get("symbol") or market_context.get("symbol") or "BTCUSDT",
        "current_price": current_price,
        "trading_bias": "neutral",
        "confidence": "low",
        "kb_lint_status": kb_lint_result.get("status"),
        "source_report": str(latest_report_path) if latest_report_path else None,
        "conditional_setup": None,
        "reason": reason,
        "risk_notes": [
            "No conditional watch should be created.",
            "Market should be observed until signals improve.",
        ],
        "evidence": {
            "decision_source": decision_source,
            "entities": ["BTC"],
            "concepts": ["observe_only"],
            "sources": ["dynamic_setup_result", "market_snapshot"],
            "scenarios": [],
        },
        "dynamic_setup_summary": _compact_dynamic_setup(dynamic_setup_result),
        "market_snapshot_summary": _compact_market_snapshot(market_snapshot),
        "safety": {
            "order_execution": False,
            "paper_watch_created": False,
            "live_trading_enabled": False,
        },
        "files": _result_files(latest_report_path),
    }


def _extract_conditional_setup_from_report(text: str) -> Dict[str, Any]:
    """
    Supports report formats like:
    - Direction: long
    - Trigger: 107500
    - Invalidation: 106200
    - Take Profit: 110000
    - Setup Type: breakout_reclaim
    """

    setup_type = _extract_report_value(text, ["Setup Type", "setup_type"])
    direction = _extract_report_value(text, ["Direction", "direction"])
    trigger = _extract_report_value(text, ["Trigger", "Trigger Price", "trigger_price"])
    invalidation = _extract_report_value(text, ["Invalidation", "Invalidation Price", "invalidation_price"])
    take_profit = _extract_report_value(text, ["Take Profit", "TP", "take_profit"])

    setup: Dict[str, Any] = {}

    if setup_type:
        setup["setup_type"] = setup_type

    if direction:
        setup["direction"] = direction.lower()

    if trigger:
        setup["trigger_price"] = _to_float(trigger)

    if invalidation:
        setup["invalidation_price"] = _to_float(invalidation)

    if take_profit:
        setup["take_profit"] = _to_float(take_profit)

    if setup:
        setup["symbol"] = "BTCUSDT"
        setup["expires_after_hours"] = _env_int("FALLBACK_EXPIRES_AFTER_HOURS", 24)
        setup["source"] = "daily_report"

    return setup


def _extract_report_value(text: str, labels: List[str]) -> Optional[str]:
    for label in labels:
        pattern = rf"[-*]?\s*{re.escape(label)}\s*:\s*([^\n\r]+)"
        match = re.search(pattern, text, flags=re.IGNORECASE)

        if match:
            return match.group(1).strip()

    return None


def _normalize_conditional_setup(setup: Any) -> Dict[str, Any]:
    if not isinstance(setup, dict):
        return {}

    normalized = {
        "symbol": setup.get("symbol") or "BTCUSDT",
        "setup_type": setup.get("setup_type") or os.getenv("FALLBACK_SETUP_TYPE", "breakout_reclaim"),
        "direction": str(setup.get("direction") or os.getenv("FALLBACK_SETUP_DIRECTION", "long")).lower(),
        "trigger_price": _to_float(setup.get("trigger_price")),
        "invalidation_price": _to_float(setup.get("invalidation_price")),
        "take_profit": _to_float(setup.get("take_profit")),
        "expires_after_hours": _to_int(setup.get("expires_after_hours")) or _env_int("FALLBACK_EXPIRES_AFTER_HOURS", 24),
        "confidence": setup.get("confidence"),
        "score": setup.get("score"),
        "source": setup.get("source") or "research_decision_builder",
        "created_at_utc": setup.get("created_at_utc") or _now_utc_iso(),
    }

    extra_keys = [
        "base_price",
        "rules",
        "signals",
        "reasoning",
    ]

    for key in extra_keys:
        if key in setup:
            normalized[key] = setup[key]

    return normalized


def _is_valid_conditional_setup(setup: Any) -> bool:
    if not isinstance(setup, dict):
        return False

    required = [
        "setup_type",
        "direction",
        "trigger_price",
        "invalidation_price",
        "take_profit",
    ]

    for key in required:
        if setup.get(key) is None:
            return False

    trigger = _to_float(setup.get("trigger_price"))
    invalidation = _to_float(setup.get("invalidation_price"))
    take_profit = _to_float(setup.get("take_profit"))
    direction = str(setup.get("direction") or "").lower()

    if trigger is None or invalidation is None or take_profit is None:
        return False

    if trigger <= 0 or invalidation <= 0 or take_profit <= 0:
        return False

    if direction not in {"long", "short"}:
        return False

    if direction == "long":
        return invalidation < trigger < take_profit

    if direction == "short":
        return take_profit < trigger < invalidation

    return False


def _extract_current_price(
    market_context: Dict[str, Any],
    market_snapshot: Dict[str, Any],
) -> Optional[float]:
    candidates = [
        market_context.get("current_price"),
        market_context.get("price"),
        market_snapshot.get("current_price"),
        market_snapshot.get("price"),
    ]

    for value in candidates:
        parsed = _to_float(value)

        if parsed is not None:
            return parsed

    return None


def _find_latest_daily_report() -> Optional[Path]:
    daily_dir = WIKI_DIR / "report" / "daily"

    if not daily_dir.exists():
        return None

    reports = sorted(daily_dir.glob("*.md"))

    if not reports:
        return None

    return reports[-1]


def _trading_bias_from_direction(direction: Any) -> str:
    direction_text = str(direction or "").lower()

    if direction_text == "long":
        return "bullish"

    if direction_text == "short":
        return "bearish"

    return "neutral"


def _extract_active_scenario_from_dynamic(dynamic_setup_result: Dict[str, Any]) -> Optional[str]:
    setup_type = dynamic_setup_result.get("setup_type")

    if setup_type:
        return str(setup_type)

    conditional_setup = dynamic_setup_result.get("conditional_setup")

    if isinstance(conditional_setup, dict):
        return conditional_setup.get("setup_type")

    return None


def _build_risk_notes(
    source: str,
    dynamic_setup_result: Dict[str, Any],
) -> List[str]:
    notes = [
        f"Decision source: {source}.",
        "This is a conditional watch, not a market order.",
        "Order execution remains disabled unless explicitly enabled in a separate manual test mode.",
    ]

    signals = dynamic_setup_result.get("signals")

    if isinstance(signals, dict):
        funding_signal = _nested_signal(signals, "funding_rate")
        long_short_signal = _nested_signal(signals, "long_short_ratio")
        oi_signal = _nested_signal(signals, "open_interest")

        notes.append(f"Funding signal: {funding_signal}.")
        notes.append(f"Long/Short signal: {long_short_signal}.")
        notes.append(f"Open Interest signal: {oi_signal}.")

    return notes


def _nested_signal(signals: Dict[str, Any], key: str) -> str:
    item = signals.get(key)

    if isinstance(item, dict):
        return str(item.get("signal") or "unknown")

    return "unknown"


def _compact_dynamic_setup(dynamic_setup_result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(dynamic_setup_result, dict):
        return {}

    return {
        "status": dynamic_setup_result.get("status"),
        "decision_type": dynamic_setup_result.get("decision_type"),
        "direction": dynamic_setup_result.get("direction"),
        "setup_type": dynamic_setup_result.get("setup_type"),
        "confidence": dynamic_setup_result.get("confidence"),
        "long_score": dynamic_setup_result.get("long_score"),
        "short_score": dynamic_setup_result.get("short_score"),
        "selected_score": dynamic_setup_result.get("selected_score"),
        "reason": dynamic_setup_result.get("reason"),
    }


def _compact_market_snapshot(market_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(market_snapshot, dict):
        return {}

    return {
        "status": market_snapshot.get("status"),
        "symbol": market_snapshot.get("symbol"),
        "provider": market_snapshot.get("provider"),
        "current_price": market_snapshot.get("current_price"),
        "timestamp_utc": market_snapshot.get("timestamp_utc"),
        "data_quality": market_snapshot.get("data_quality"),
    }


def _result_files(latest_report_path: Optional[Path]) -> Dict[str, Optional[str]]:
    return {
        "market_context": str(MARKET_CONTEXT_PATH),
        "market_snapshot": str(MARKET_SNAPSHOT_PATH),
        "dynamic_setup_result": str(DYNAMIC_SETUP_RESULT_PATH),
        "kb_lint_result": str(KB_LINT_RESULT_PATH),
        "latest_daily_report": str(latest_report_path) if latest_report_path else None,
        "research_decision": str(RESEARCH_DECISION_PATH),
        "research_decision_log": str(RESEARCH_DECISION_LOG_PATH),
    }


def _save_and_log(result: Dict[str, Any]) -> None:
    _save_json(RESEARCH_DECISION_PATH, result)
    _append_log(RESEARCH_DECISION_LOG_PATH, result)


def _env_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key)

    if value is None:
        return default

    return value.strip().lower() in {
        "true",
        "1",
        "yes",
        "y",
        "on",
    }


def _env_float(key: str, default: float) -> float:
    value = os.getenv(key)

    if value is None:
        return default

    parsed = _to_float(value)

    return parsed if parsed is not None else default


def _env_int(key: str, default: int) -> int:
    value = os.getenv(key)

    if value is None:
        return default

    parsed = _to_int(value)

    return parsed if parsed is not None else default


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(",", "").replace("$", "")

    if not text:
        return None

    try:
        return float(text)
    except ValueError:
        return None


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def _append_log(path: Path, item: Dict[str, Any], max_items: int = 500) -> None:
    existing = _load_json(path, default=[])

    if not isinstance(existing, list):
        existing = []

    existing.append(item)
    existing = existing[-max_items:]

    _save_json(path, existing)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    result = build_research_decision()

    print("=" * 90)
    print("[RESEARCH DECISION BUILDER]")
    print("=" * 90)
    print(f"Status: {result.get('status')}")
    print(f"Decision Type: {result.get('decision_type')}")
    print(f"Decision Source: {result.get('decision_source')}")
    print(f"Symbol: {result.get('symbol')}")
    print(f"Current Price: {result.get('current_price')}")
    print(f"Trading Bias: {result.get('trading_bias')}")
    print(f"Confidence: {result.get('confidence')}")
    print(f"KB Lint Status: {result.get('kb_lint_status')}")

    print("-" * 90)
    print("[CONDITIONAL SETUP]")
    conditional_setup = result.get("conditional_setup")

    if isinstance(conditional_setup, dict):
        print(f"Setup Type: {conditional_setup.get('setup_type')}")
        print(f"Direction: {conditional_setup.get('direction')}")
        print(f"Trigger Price: {conditional_setup.get('trigger_price')}")
        print(f"Invalidation Price: {conditional_setup.get('invalidation_price')}")
        print(f"Take Profit: {conditional_setup.get('take_profit')}")
        print(f"Source: {conditional_setup.get('source')}")
    else:
        print("None")
        print(f"Reason: {result.get('reason')}")

    print("-" * 90)
    print("[FILES]")
    files = result.get("files", {})

    if isinstance(files, dict):
        for key, value in files.items():
            print(f"{key}: {value}")

    print("=" * 90)


if __name__ == "__main__":
    main()
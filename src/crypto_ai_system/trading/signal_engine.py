from __future__ import annotations

import os

from config.settings import (
    LATEST_DIR,
    MARKET_SNAPSHOT_PATH,
    MAX_STALE_DATA_MINUTES,
    RESEARCH_RESULT_PATH,
    RESEARCH_SIGNAL_PATH,
    USE_RESEARCH_SIGNAL_GATE,
)
from core.json_io import read_json
from crypto_ai_system.trading.permission_gate import signal_payload_from_research_signal
from crypto_ai_system.quality.legacy_signal_fallback_blocker import (
    build_legacy_signal_fallback_block_report,
    legacy_fallback_used,
)


SIGNAL_ENGINE_MODE = "SIGNAL_GENERATION_ONLY"
ORDER_EXECUTION_ENABLED_BY_THIS_MODULE = False
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
LEGACY_SIGNAL_FALLBACK_REVIEW_ONLY_COMPAT = os.getenv("ALLOW_LEGACY_SIGNAL_FALLBACK", "").lower() in {"1", "true", "yes", "review_only"}
SIGNAL_QA_REPORT_PATH = LATEST_DIR / "signal_qa_report.json"


def _blocked_research_signal_payload(reason: str) -> dict:
    return {
        "signal": "NONE",
        "confidence": 0,
        "reasons": [reason],
        "permission_gate_applied": True,
        "source": "research_signal_v2_gate_fail_closed",
        "allow_new_position": False,
        "allow_long": False,
        "allow_short": False,
        "risk_level": "blocked",
        "position_size_multiplier": 0.0,
        "legacy_fallback_used": False,
    }


def _legacy_signal_from_research() -> dict:
    snapshot = read_json(MARKET_SNAPSHOT_PATH, {})
    research = read_json(RESEARCH_RESULT_PATH, {})

    signal = "NONE"
    confidence = 0
    reasons = []

    trend = snapshot.get("trend_bias")
    scenario = research.get("scenario")
    timing = research.get("signal_timing")

    if snapshot.get("is_synthetic") or snapshot.get("is_fallback"):
        return {
            "signal": "NONE",
            "confidence": 0,
            "reasons": ["synthetic_or_fallback_data_no_signal"],
            "permission_gate_applied": False,
            "allow_new_position": False,
            "risk_level": "blocked",
            "position_size_multiplier": 0.0,
            "legacy_fallback_used": True,
        }

    if trend == "bullish" and scenario in {"Bullish", "Constructive"} and timing in {"Early", "Confirmed"}:
        signal = "LONG"
        confidence = 65
        reasons.append("trend_and_research_aligned_long")
    elif trend == "bearish" and scenario == "Bearish":
        signal = "SHORT"
        confidence = 60
        reasons.append("trend_and_research_aligned_short")

    return {
        "signal": signal,
        "confidence": confidence,
        "reasons": reasons,
        "permission_gate_applied": False,
        "allow_new_position": signal in {"LONG", "SHORT"},
        "risk_level": "normal" if signal in {"LONG", "SHORT"} else "blocked",
        "position_size_multiplier": 1.0 if signal in {"LONG", "SHORT"} else 0.0,
        "legacy_fallback_used": True,
    }


def _research_signal_invalid_reason(research_signal: dict) -> str | None:
    if not isinstance(research_signal, dict) or not research_signal:
        return "RESEARCH_SIGNAL_MISSING_FAIL_CLOSED"
    if not (research_signal.get("trade_permission") or research_signal.get("entry_side")):
        return "RESEARCH_SIGNAL_INVALID_FAIL_CLOSED"
    if research_signal.get("valid") is False or research_signal.get("validation_status") == "invalid":
        return "RESEARCH_SIGNAL_INVALID_FAIL_CLOSED"
    if legacy_fallback_used(research_signal):
        return "RESEARCH_SIGNAL_LEGACY_FALLBACK_FAIL_CLOSED"
    if research_signal.get("stale") is True or research_signal.get("data_stale") is True:
        return "RESEARCH_SIGNAL_STALE_FAIL_CLOSED"
    freshness = research_signal.get("data_freshness_sec")
    try:
        if freshness is not None and float(freshness) > float(MAX_STALE_DATA_MINUTES) * 60.0:
            return "RESEARCH_SIGNAL_STALE_FAIL_CLOSED"
    except Exception:
        return "RESEARCH_SIGNAL_INVALID_FRESHNESS_FAIL_CLOSED"
    return None


def generate_trading_signal() -> dict:
    """Generate the final Trading Bot signal.

    Step268: when USE_RESEARCH_SIGNAL_GATE=true, a missing/stale/invalid
    ResearchSignal fails closed and legacy scenario fallback is not allowed unless
    an explicit review-only compatibility flag is set.
    """
    if USE_RESEARCH_SIGNAL_GATE:
        research_signal = read_json(RESEARCH_SIGNAL_PATH, {})
        signal_qa_report = read_json(SIGNAL_QA_REPORT_PATH, {})
        reason = _research_signal_invalid_reason(research_signal)
        blocker_report = build_legacy_signal_fallback_block_report(
            research_signal=research_signal,
            signal_qa_report=signal_qa_report,
            use_research_signal_gate=True,
            consumer="trading_signal_engine",
        )
        blocker_result = str(blocker_report.get("legacy_signal_fallback_blocker_result") or "")
        if reason is None and blocker_result == "PASS_RESEARCH_SIGNAL_QA":
            payload = signal_payload_from_research_signal(research_signal)
            payload.setdefault("source", "research_signal_v2")
            payload["legacy_fallback_used"] = False
            payload["legacy_signal_fallback_blocker_result"] = blocker_result
            payload["legacy_signal_fallback_blocker_id"] = blocker_report.get("legacy_signal_fallback_blocker_id")
            return payload
        block_reason = reason or blocker_result or "RESEARCH_SIGNAL_GATE_FAIL_CLOSED"
        payload = _blocked_research_signal_payload(block_reason)
        payload["legacy_signal_fallback_blocker_result"] = blocker_result
        payload["legacy_signal_fallback_blocker_id"] = blocker_report.get("legacy_signal_fallback_blocker_id")
        payload["legacy_signal_fallback_blocker_block_reasons"] = blocker_report.get("block_reasons") or []
        # Step290: the legacy compatibility flag may exist for source history, but
        # it cannot reopen trading-signal fallback while the ResearchSignal gate is enabled.
        payload["legacy_signal_fallback_compat_requested"] = LEGACY_SIGNAL_FALLBACK_REVIEW_ONLY_COMPAT
        return payload

    return _legacy_signal_from_research()

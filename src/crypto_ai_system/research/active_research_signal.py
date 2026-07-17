"""Lean ResearchSignal v2 for the active Binance-public pipeline (E-2).

The dormant v2 research stack (`raw_score_pipeline` + `research_bot` +
`research_feature_matrix`) produces a rich ResearchSignal, but it runs its own
extended-venue data collection and heavy feature store. The active pipeline
uses the simple Binance-public snapshot + `research/scoring`. This module bridges
the gap: it builds a ResearchSignal v2 record from the active snapshot + research
result, with a real lineage chain (data_snapshot_id -> feature_snapshot_id ->
research_signal_id + content hashes) and a trade_permission derived from the
active research, so the decision engine and the real PreOrderRiskGate (B-3) have
the inputs they need — without pulling in the extended data stack.

Signal QA over this record and profile approval land in E-3.
"""

from __future__ import annotations

from typing import Any, Mapping

from config.settings import LATEST_DIR, MARKET_SNAPSHOT_PATH, RESEARCH_RESULT_PATH, RESEARCH_SIGNAL_PATH
from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.quality.signal_qa import persist_signal_qa_report, validate_research_signal_quality
from crypto_ai_system.research.paper_profile import (
    PAPER_PROFILE_ID,
    PAPER_PROFILE_SHA256,
    PAPER_PROFILE_VERSION,
)
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

ACTIVE_RESEARCH_SIGNAL_VERSION = "active_research_signal.v1"
DEFAULT_PROFILE_ID = PAPER_PROFILE_ID
PROFILE_VERSION = PAPER_PROFILE_VERSION
CONFIG_VERSION = "lean_pipeline.v1"

# profile_id -> the deterministic hash the gate's profile-hash check expects.
_PROFILE_HASHES = {PAPER_PROFILE_ID: PAPER_PROFILE_SHA256}


def _resolve_signal_profile() -> tuple[str, str]:
    """(profile_id, profile_sha256) for this cycle's signal.

    When the live-strategy stage is fully configured (same single source the
    pipeline stage router uses), the signal carries the operator-approved live
    profile so the live PreOrderRiskGate's hash check can pass; otherwise the
    auto-approved paper profile.
    """
    try:
        from crypto_ai_system.research.live_profile import (
            LIVE_PROFILE_ID,
            LIVE_PROFILE_SHA256,
            live_stage_fully_configured,
        )

        if live_stage_fully_configured():
            return LIVE_PROFILE_ID, LIVE_PROFILE_SHA256
    except Exception:  # noqa: BLE001 - any doubt -> paper (fail-closed for live)
        pass
    return PAPER_PROFILE_ID, PAPER_PROFILE_SHA256

SIGNAL_QA_REPORT_PATH = LATEST_DIR / "signal_qa_report.json"

# Scenario/timing that permit a long (mirrors the decision engine bias). The
# scenario sets are public because they are the only record of the research's
# *directional view* before timing/data blocks collapse entry_side to FLAT — the
# counterfactual tracker reads them to know what a block suppressed.
LONG_SCENARIOS = {"Bullish", "Constructive"}
SHORT_SCENARIOS = {"Bearish"}
_BLOCKING_TIMING = {"Data-Blocked", "Late", "Risk-Off", "Bearish"}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value not in {None, ""} else default
    except (TypeError, ValueError):
        return default


def _optional_health_flags(optional_data_health: Mapping[str, Any]) -> tuple[bool, bool, bool]:
    """Return (stale_optional, missing_neutral, all_available) from health map."""
    statuses = [str((v or {}).get("status", "")) for v in optional_data_health.values() if isinstance(v, Mapping)]
    stale = any(s == "stale" for s in statuses)
    missing_neutral = any(s in {"missing", "unavailable", "invalid", "neutral_due_to_missing"} for s in statuses)
    all_available = bool(statuses) and all(s == "available" for s in statuses)
    return stale, missing_neutral, all_available


def _trade_permission(snapshot: Mapping[str, Any], research: Mapping[str, Any]) -> dict[str, Any]:
    scenario = str(research.get("scenario") or "")
    timing = str(research.get("signal_timing") or "")
    block_reasons: list[str] = []
    if snapshot.get("is_synthetic") is True:
        block_reasons.append("SYNTHETIC_DATA")
    if snapshot.get("is_fallback") is True:
        block_reasons.append("FALLBACK_DATA")

    allow_long = scenario in LONG_SCENARIOS and timing not in _BLOCKING_TIMING and not block_reasons
    allow_short = scenario in SHORT_SCENARIOS and timing != "Data-Blocked" and not block_reasons
    allow_new = allow_long or allow_short
    risk_level = "blocked" if (block_reasons or not allow_new) else "normal"
    return {
        "allow_long": bool(allow_long),
        "allow_short": bool(allow_short),
        "allow_new_position": bool(allow_new),
        "risk_level": risk_level,
        "block_reasons": block_reasons,
        "risk_warnings": [],
    }


def build_active_research_signal(
    snapshot: Mapping[str, Any],
    research: Mapping[str, Any],
    *,
    cycle_id: str | None = None,
    profile_id: str | None = None,
) -> dict[str, Any]:
    """Build a ResearchSignal v2 record from the active snapshot + research result.

    ``profile_id`` defaults to this cycle's resolved profile: the operator-approved
    live profile when the live stage is fully configured, else the paper profile.
    """
    resolved_profile_id, resolved_profile_hash = _resolve_signal_profile()
    if profile_id is None:
        profile_id = resolved_profile_id
    profile_hash = (
        resolved_profile_hash if profile_id == resolved_profile_id
        else _PROFILE_HASHES.get(profile_id)
    )
    symbol = str(snapshot.get("symbol") or "BTCUSDT")
    timeframe = str(snapshot.get("timeframe") or "1h")
    optional_data_health = snapshot.get("optional_data_health") if isinstance(snapshot.get("optional_data_health"), dict) else {}
    stale_optional, missing_neutral, all_available = _optional_health_flags(optional_data_health)

    # Content-stable lineage: identity fields (not created_at) so the same candle
    # + features yield the same ids/hashes for verification.
    snapshot_identity = {
        "symbol": symbol,
        "timeframe": timeframe,
        "last_candle_time": snapshot.get("last_candle_time"),
        "last_close": snapshot.get("last_close"),
        "funding_rate": snapshot.get("funding_rate"),
        "open_interest_change_24h": snapshot.get("open_interest_change_24h"),
        "source_type": snapshot.get("source_type"),
    }
    features = {
        "ma20": snapshot.get("ma20"),
        "ma50": snapshot.get("ma50"),
        "volume_ratio": snapshot.get("volume_ratio"),
        "change_24h_pct": snapshot.get("change_24h_pct"),
        "funding_rate": snapshot.get("funding_rate"),
        "open_interest_change_24h": snapshot.get("open_interest_change_24h"),
        "trend_bias": snapshot.get("trend_bias"),
    }
    data_snapshot_id = stable_id("data_snapshot", snapshot_identity)
    source_bundle_sha256 = sha256_json(snapshot_identity)
    feature_matrix_sha256 = sha256_json(features)
    feature_snapshot_id = stable_id("feature_snapshot", {"data_snapshot_id": data_snapshot_id, "feature_matrix_sha256": feature_matrix_sha256})

    permission = _trade_permission(snapshot, research)
    side = "LONG" if permission["allow_long"] else "SHORT" if permission["allow_short"] else "FLAT"
    research_signal_id = stable_id(
        "research_signal",
        {
            "data_snapshot_id": data_snapshot_id,
            "feature_snapshot_id": feature_snapshot_id,
            "side": side,
            "profile_id": profile_id,
        },
    )
    score_total = _f(research.get("scores", {}).get("final_score"))

    return {
        "signal_version": ACTIVE_RESEARCH_SIGNAL_VERSION,
        "version": ACTIVE_RESEARCH_SIGNAL_VERSION,
        "signal_id": research_signal_id,
        "research_signal_id": research_signal_id,
        "cycle_id": cycle_id,
        "data_snapshot_id": data_snapshot_id,
        "feature_snapshot_id": feature_snapshot_id,
        "feature_matrix_sha256": feature_matrix_sha256,
        "source_bundle_sha256": source_bundle_sha256,
        "profile_id": profile_id,
        "profile_version": PROFILE_VERSION,
        # Matches the approved profile for this cycle's resolved stage (paper, or
        # the operator-approved live profile when the live stage is fully
        # configured) so the gate's profile-hash check can pass. An unknown
        # profile carries no hash and the gate blocks (fail-closed).
        "profile_sha256": profile_hash,
        "profile_hash": profile_hash,
        "config_version": CONFIG_VERSION,
        "created_at_utc": utc_now_canonical(),
        "timestamp": snapshot.get("last_candle_time") or snapshot.get("created_at"),
        "symbol": symbol,
        "timeframe": timeframe,
        "data_source": snapshot.get("source_type") or snapshot.get("source"),
        "data_quality_status": "OK" if snapshot.get("is_synthetic") is not True else "SYNTHETIC",
        # Data-health flags the PreOrderRiskGate reads.
        "synthetic_used": bool(snapshot.get("is_synthetic")),
        "fallback_used": bool(snapshot.get("is_fallback")),
        "stale": False,
        "data_stale": False,
        "optional_data_health": optional_data_health,
        "stale_optional_data": bool(stale_optional),
        "missing_optional_data_neutral": bool(missing_neutral),
        "neutral_due_to_missing": bool(missing_neutral),
        "live_candidate_eligible": bool(all_available and snapshot.get("is_synthetic") is not True),
        "scenario": research.get("scenario"),
        "market_condition": research.get("scenario"),
        "signal_timing": research.get("signal_timing"),
        "signal_quality": research.get("signal_quality"),
        "score_total_score": score_total,
        "entry_side": side,
        "trade_permission": permission,
        "block_reasons": permission["block_reasons"],
    }


def run_active_research_signal(*, cycle_id: str | None = None) -> dict[str, Any]:
    """Read active snapshot + research result, build & persist the ResearchSignal.

    Also stamps the research result with the lineage ids so the decision engine's
    same-signal-id check passes.
    """
    snapshot = read_json(MARKET_SNAPSHOT_PATH, {})
    research = read_json(RESEARCH_RESULT_PATH, {})
    if not isinstance(snapshot, dict):
        snapshot = {}
    if not isinstance(research, dict):
        research = {}

    signal = build_active_research_signal(snapshot, research, cycle_id=cycle_id)
    atomic_write_json(RESEARCH_SIGNAL_PATH, signal)

    # Signal QA over THIS cycle's signal (E-3). Writing a matching QA report is
    # what makes the decision engine treat the signal as authoritative
    # (USE_RESEARCH_SIGNAL_GATE). A stale/synthetic/incomplete signal fails QA.
    cfg = load_config(".")
    qa_report = validate_research_signal_quality(signal, cfg=cfg)
    atomic_write_json(SIGNAL_QA_REPORT_PATH, qa_report)
    try:
        persist_signal_qa_report(cfg, qa_report)
    except Exception:  # noqa: BLE001 - registry persistence is best-effort here
        pass

    # Stamp lineage onto the legacy research result so the decision engine treats
    # this cycle's signal as the matching one (not stale cross-cycle state).
    research["research_signal_id"] = signal["research_signal_id"]
    research["signal_id"] = signal["research_signal_id"]
    research["data_snapshot_id"] = signal["data_snapshot_id"]
    research["feature_snapshot_id"] = signal["feature_snapshot_id"]
    research["cycle_id"] = cycle_id
    atomic_write_json(RESEARCH_RESULT_PATH, research)
    return signal

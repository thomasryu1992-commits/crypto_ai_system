from __future__ import annotations

from typing import Any, Mapping

from crypto_ai_system.config import AppConfig
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

MARKET_THESIS_NOTE_VERSION = "step287_market_thesis_note_v1"


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _direction_label(score: float) -> str:
    if score >= 0.35:
        return "bullish"
    if score <= -0.35:
        return "bearish"
    return "neutral"


def _append_if(items: list[str], condition: bool, text: str) -> None:
    if condition and text not in items:
        items.append(text)


def _score_summary(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "total_score": snapshot.get("score_total_score", snapshot.get("total_score")),
        "structure": snapshot.get("score_structure"),
        "momentum": snapshot.get("score_momentum"),
        "derivatives": snapshot.get("score_derivatives"),
        "exchange_flow": snapshot.get("score_exchange_flow", snapshot.get("exchange_flow_score")),
        "etf_flow": snapshot.get("score_etf_flow", snapshot.get("etf_flow_score")),
        "stablecoin_liquidity": snapshot.get("score_stablecoin_liquidity", snapshot.get("stablecoin_liquidity_score")),
        "risk": snapshot.get("score_risk"),
        "binance_derivatives_score": snapshot.get("binance_derivatives_score"),
        "exchange_flow_score": snapshot.get("exchange_flow_score"),
        "etf_flow_score": snapshot.get("etf_flow_score"),
        "stablecoin_liquidity_score": snapshot.get("stablecoin_liquidity_score"),
    }


def _supporting_features(snapshot: Mapping[str, Any], condition: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "price_structure": {
            "close": snapshot.get("close"),
            "market_condition": snapshot.get("market_condition") or condition.get("final_condition"),
            "market_regime": snapshot.get("market_regime"),
            "mtf_bias": snapshot.get("mtf_bias"),
            "mtf_alignment_score": snapshot.get("mtf_alignment_score"),
            "volatility_state": snapshot.get("volatility_state") or condition.get("volatility_state"),
        },
        "derivatives_positioning": {
            "funding_rate": snapshot.get("funding_rate"),
            "oi_change_1h": snapshot.get("oi_change_1h") or snapshot.get("oi_change_pct"),
            "binance_derivatives_score": snapshot.get("binance_derivatives_score"),
            "taker_buy_sell_ratio": snapshot.get("taker_buy_sell_ratio"),
            "top_trader_long_short_ratio": snapshot.get("top_trader_position_long_short_ratio"),
        },
        "exchange_flow": {
            "exchange_flow_score": snapshot.get("exchange_flow_score"),
            "exchange_netflow_zscore_30d": snapshot.get("exchange_netflow_zscore_30d"),
            "btc_exchange_netflow": snapshot.get("btc_exchange_netflow"),
        },
        "etf_flow": {
            "etf_flow_score": snapshot.get("etf_flow_score"),
            "total_flow_usd_m": snapshot.get("total_flow_usd_m"),
            "etf_flow_5d_sum": snapshot.get("etf_flow_5d_sum"),
        },
        "stablecoin_liquidity": {
            "stablecoin_liquidity_score": snapshot.get("stablecoin_liquidity_score"),
            "stablecoin_total_mcap_7d_change": snapshot.get("stablecoin_total_mcap_7d_change"),
        },
        "score_components": _score_summary(snapshot),
    }


def _build_arguments(snapshot: Mapping[str, Any], condition: Mapping[str, Any]) -> tuple[list[str], list[str], list[str], list[str]]:
    long_arguments: list[str] = []
    short_arguments: list[str] = []
    neutral_arguments: list[str] = []
    counterarguments: list[str] = []

    total_score = _float(snapshot.get("score_total_score", snapshot.get("total_score")))
    structure = _float(snapshot.get("score_structure"))
    momentum = _float(snapshot.get("score_momentum"))
    derivatives = _float(snapshot.get("score_derivatives"))
    exchange = _float(snapshot.get("exchange_flow_score", snapshot.get("score_exchange_flow")))
    etf = _float(snapshot.get("etf_flow_score", snapshot.get("score_etf_flow")))
    stable = _float(snapshot.get("stablecoin_liquidity_score", snapshot.get("score_stablecoin_liquidity")))
    binance_derivatives = _float(snapshot.get("binance_derivatives_score"))
    mtf_alignment = _float(snapshot.get("mtf_alignment_score"))
    condition_text = str(snapshot.get("market_condition") or condition.get("final_condition") or "").upper()
    mtf_bias = str(snapshot.get("mtf_bias") or "").upper()

    _append_if(long_arguments, total_score >= 0.35, "Positive total score supports a long-biased thesis.")
    _append_if(short_arguments, total_score <= -0.35, "Negative total score supports a short-biased thesis.")
    _append_if(neutral_arguments, abs(total_score) < 0.35, "Total score is not strong enough to create directional conviction.")

    _append_if(long_arguments, "BULLISH" in condition_text, "Market condition is classified as bullish.")
    _append_if(short_arguments, "BEARISH" in condition_text, "Market condition is classified as bearish.")
    _append_if(neutral_arguments, "NEUTRAL" in condition_text or "RANGE" in condition_text, "Market condition is neutral/range-like and requires confirmation.")

    _append_if(long_arguments, structure > 0.20, "Price structure score is supportive for upside continuation.")
    _append_if(short_arguments, structure < -0.20, "Price structure score is supportive for downside continuation.")
    _append_if(long_arguments, momentum > 0.20, "Momentum score supports upside follow-through.")
    _append_if(short_arguments, momentum < -0.20, "Momentum score supports downside follow-through.")
    _append_if(long_arguments, mtf_alignment > 0.20 or mtf_bias in {"BULLISH", "UP", "LONG"}, "Multi-timeframe context leans constructive.")
    _append_if(short_arguments, mtf_alignment < -0.20 or mtf_bias in {"BEARISH", "DOWN", "SHORT"}, "Multi-timeframe context leans defensive.")

    _append_if(long_arguments, derivatives > 0.20 or binance_derivatives > 0.20, "Derivatives positioning is supportive rather than obstructive.")
    _append_if(short_arguments, derivatives < -0.20 or binance_derivatives < -0.20, "Derivatives positioning is bearish or risk-off.")
    _append_if(counterarguments, binance_derivatives >= 0.80, "Derivatives positioning may be crowded on the long side.")
    _append_if(counterarguments, binance_derivatives <= -0.80, "Derivatives positioning may be crowded on the short side.")

    _append_if(long_arguments, exchange >= 0.25, "Exchange flow score supports accumulation or reduced sell pressure.")
    _append_if(short_arguments, exchange <= -0.25, "Exchange flow score indicates sell pressure or distribution risk.")
    _append_if(long_arguments, etf >= 0.25, "ETF flow score supports institutional demand.")
    _append_if(short_arguments, etf <= -0.25, "ETF flow score indicates institutional outflow weakness.")
    _append_if(long_arguments, stable >= 0.25, "Stablecoin liquidity score supports risk-on liquidity.")
    _append_if(short_arguments, stable <= -0.25, "Stablecoin liquidity score indicates liquidity contraction risk.")

    if long_arguments and short_arguments:
        counterarguments.append("Long and short evidence both exist; directional conclusion requires risk-gate confirmation.")
    if snapshot.get("missing_optional_data_neutral") or _float(snapshot.get("missing_optional_source_count")) > 0:
        neutral_arguments.append("One or more optional data groups are missing and scored neutral_due_to_missing.")
        counterarguments.append("Missing optional data weakens live/testnet eligibility even when price data is valid.")
    if snapshot.get("stale_optional_data") or _float(snapshot.get("stale_optional_source_count")) > 0:
        neutral_arguments.append("One or more optional data groups are stale.")
        counterarguments.append("Stale optional data must remain visible in review and block live eligibility where required.")
    if not _bool(snapshot.get("live_candidate_eligible")):
        counterarguments.append("Current data lineage is not live-candidate eligible.")

    if not long_arguments:
        long_arguments.append("No strong bullish thesis is supported by the current feature snapshot.")
    if not short_arguments:
        short_arguments.append("No strong bearish thesis is supported by the current feature snapshot.")
    if not neutral_arguments:
        neutral_arguments.append("Neutral view remains secondary but must be reviewed if signal and price structure diverge.")
    if not counterarguments:
        counterarguments.append("No major contradictory feature was detected, but this note remains review-only evidence.")

    return long_arguments, short_arguments, neutral_arguments, counterarguments


def _build_invalidation_conditions(snapshot: Mapping[str, Any]) -> list[str]:
    total_score = _float(snapshot.get("score_total_score", snapshot.get("total_score")))
    close = snapshot.get("close")
    conditions = [
        "ResearchSignal lineage becomes missing, stale, or hash-mismatched.",
        "Price data becomes missing, stale, fallback, synthetic, or sample-based.",
        "PreOrderRiskGate blocks due to position, loss, spread/slippage, API, reconciliation, or manual kill-switch constraints.",
    ]
    if close is not None:
        conditions.append(f"BTC price structure invalidates around the current close reference ({close}).")
    if total_score >= 0.35:
        conditions.append("Bullish thesis invalidates if total score flips below neutral and price structure loses support.")
    elif total_score <= -0.35:
        conditions.append("Bearish thesis invalidates if total score flips above neutral and price structure reclaims resistance.")
    else:
        conditions.append("Neutral thesis invalidates only after price structure and ResearchSignal align directionally.")
    return conditions


def build_market_thesis_note(
    snapshot: Mapping[str, Any],
    condition: Mapping[str, Any],
    cfg: AppConfig,
    *,
    feature_snapshot_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a review-only market thesis note from feature evidence.

    The note is intentionally interpretive and cannot create order intents,
    approve trades, mutate settings, or promote a profile.
    """
    manifest = dict(feature_snapshot_manifest or snapshot.get("feature_snapshot_manifest") or {})
    total_score = _float(snapshot.get("score_total_score", snapshot.get("total_score")))
    direction = _direction_label(total_score)
    long_args, short_args, neutral_args, counterarguments = _build_arguments(snapshot, condition)
    data_snapshot_id = snapshot.get("data_snapshot_id") or manifest.get("data_snapshot_id")
    feature_snapshot_id = snapshot.get("feature_snapshot_id") or manifest.get("feature_snapshot_id")
    feature_matrix_sha256 = snapshot.get("feature_matrix_sha256") or manifest.get("feature_matrix_sha256")
    source_bundle_sha256 = snapshot.get("source_bundle_sha256") or manifest.get("source_bundle_sha256")
    data_snapshot_manifest_sha256 = snapshot.get("data_snapshot_manifest_sha256") or manifest.get("data_snapshot_manifest_sha256")
    optional_data_health = snapshot.get("optional_data_health") if isinstance(snapshot.get("optional_data_health"), Mapping) else manifest.get("optional_data_health", {})
    profile_id = str(snapshot.get("profile_id") or snapshot.get("research_profile_id") or cfg.get("research.active_profile_id", "default_review_profile"))
    profile_version = str(snapshot.get("profile_version") or cfg.get("research.profile_version", "unknown"))
    config_version = str(snapshot.get("config_version") or cfg.get("project.version", "unknown"))
    created_at = utc_now_canonical()
    note_core = {
        "signal_version": MARKET_THESIS_NOTE_VERSION,
        "profile_id": profile_id,
        "profile_version": profile_version,
        "config_version": config_version,
        "data_snapshot_id": data_snapshot_id,
        "data_snapshot_manifest_sha256": data_snapshot_manifest_sha256,
        "feature_snapshot_id": feature_snapshot_id,
        "feature_matrix_sha256": feature_matrix_sha256,
        "source_bundle_sha256": source_bundle_sha256,
        "directional_bias": direction,
        "score_total": total_score,
        "market_condition": snapshot.get("market_condition") or condition.get("final_condition"),
        "created_at_utc": created_at,
    }
    note_id = stable_id("market_thesis_note", note_core, 24)
    note = {
        "market_thesis_note_id": note_id,
        "thesis_version": MARKET_THESIS_NOTE_VERSION,
        **note_core,
        "optional_data_health": dict(optional_data_health or {}),
        "missing_optional_source_count": snapshot.get("missing_optional_source_count") or manifest.get("missing_optional_source_count"),
        "stale_optional_source_count": snapshot.get("stale_optional_source_count") or manifest.get("stale_optional_source_count"),
        "live_candidate_eligible": bool(snapshot.get("live_candidate_eligible", manifest.get("live_candidate_eligible", False))),
        "main_market_question": "Does current BTC feature evidence support long, short, or neutral review-only positioning?",
        "core_thesis": f"Current feature evidence is {direction}; this note is review-only and does not authorize execution.",
        "long_arguments": long_args,
        "short_arguments": short_args,
        "neutral_arguments": neutral_args,
        "counterarguments": counterarguments,
        "invalidation_conditions": _build_invalidation_conditions(snapshot),
        "supporting_features": _supporting_features(snapshot, condition),
        "conflicting_features": counterarguments,
        "open_risks": [
            "Optional data may be missing, stale, or neutral_due_to_missing.",
            "Market thesis interpretation must be validated by ResearchSignal QA and PreOrderRiskGate.",
            "This note must not create order intent, mutate runtime settings, or promote any profile.",
        ],
        "order_intent_created": False,
        "trade_approved": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
    }
    note["market_thesis_note_sha256"] = sha256_json(note)
    return note

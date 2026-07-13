from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from crypto_ai_system.trading.order_id_chain import risk_gate_id_from_payload
from crypto_ai_system.utils.audit import sha256_json, utc_now_canonical

PRE_ORDER_RISK_GATE_VERSION = "step293_pre_order_risk_gate_full_policy_expansion_v1"

PASS_REVIEW_ONLY = "PASS_REVIEW_ONLY"
PASS_PAPER = "PASS_PAPER"
PASS_SIGNED_TESTNET = "PASS_SIGNED_TESTNET"

BLOCK_INVALID_CANONICAL_ID_CHAIN = "BLOCK_INVALID_CANONICAL_ID_CHAIN"
BLOCK_PROFILE_UNAPPROVED = "BLOCK_PROFILE_UNAPPROVED"
BLOCK_PROFILE_HASH_MISMATCH = "BLOCK_PROFILE_HASH_MISMATCH"
BLOCK_PROFILE_HASH_MISSING = "BLOCK_PROFILE_HASH_MISSING"
BLOCK_STALE_DATA = "BLOCK_STALE_DATA"
BLOCK_FALLBACK_OR_SYNTHETIC = "BLOCK_FALLBACK_OR_SYNTHETIC"
BLOCK_SAMPLE_DATA = "BLOCK_SAMPLE_DATA"
BLOCK_OPTIONAL_DATA_HEALTH = "BLOCK_OPTIONAL_DATA_HEALTH"
BLOCK_POSITION_LIMIT = "BLOCK_POSITION_LIMIT"
BLOCK_DAILY_LOSS_LIMIT = "BLOCK_DAILY_LOSS_LIMIT"
BLOCK_CONSECUTIVE_LOSS = "BLOCK_CONSECUTIVE_LOSS"
BLOCK_SPREAD_SLIPPAGE = "BLOCK_SPREAD_SLIPPAGE"
BLOCK_API_ERROR_RATE = "BLOCK_API_ERROR_RATE"
BLOCK_RECONCILIATION_MISMATCH = "BLOCK_RECONCILIATION_MISMATCH"
BLOCK_MANUAL_KILL_SWITCH = "BLOCK_MANUAL_KILL_SWITCH"
BLOCK_MIN_ORDER_SIZE = "BLOCK_MIN_ORDER_SIZE"
BLOCK_MAX_ORDER_NOTIONAL = "BLOCK_MAX_ORDER_NOTIONAL"
BLOCK_DAILY_ORDER_COUNT = "BLOCK_DAILY_ORDER_COUNT"
BLOCK_FEE_MODEL = "BLOCK_FEE_MODEL"
BLOCK_BALANCE_MARGIN = "BLOCK_BALANCE_MARGIN"
BLOCK_LEVERAGE_LIMIT = "BLOCK_LEVERAGE_LIMIT"
BLOCK_VENUE_READINESS = "BLOCK_VENUE_READINESS"
BLOCK_STAGE_EXECUTION_DISABLED = "BLOCK_STAGE_EXECUTION_DISABLED"
BLOCK_RESEARCH_PERMISSION = "BLOCK_RESEARCH_PERMISSION"


@dataclass
class PreOrderRiskGateResult:
    risk_gate_id: str
    decision_id: str
    research_signal_id: str
    profile_id: str
    status: str
    stage: str
    approved: bool
    risk_level: str
    allow_new_position: bool
    allow_long: bool
    allow_short: bool
    block_reasons: list[str] = field(default_factory=list)
    reduce_reasons: list[str] = field(default_factory=list)
    policy_checks: dict[str, Any] = field(default_factory=dict)
    order_notional_usdt: float | None = None
    max_order_notional_usdt: float | None = None
    min_order_notional_usdt: float | None = None
    gate_version: str = PRE_ORDER_RISK_GATE_VERSION
    created_at_utc: str = field(default_factory=utc_now_canonical)
    risk_gate_report_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if not payload.get("risk_gate_report_sha256"):
            payload["risk_gate_report_sha256"] = sha256_json({k: v for k, v in payload.items() if k != "risk_gate_report_sha256"})
        return payload


def _as_bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in {None, ""}:
            return default
        return float(value)
    except Exception:
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        if value in {None, ""}:
            return default
        return int(value)
    except Exception:
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _order_notional_usdt(decision: Mapping[str, Any], market: Mapping[str, Any], runtime: Mapping[str, Any]) -> float | None:
    for source in (decision, market, runtime):
        for key in ("order_notional_usdt", "notional_usdt", "notional", "max_order_notional_usdt"):
            if source.get(key) not in {None, ""}:
                value = _float(source.get(key), -1.0)
                return value if value >= 0 else None
    qty = _float(decision.get("quantity") or decision.get("qty") or decision.get("size"), 0.0)
    price = _float(decision.get("entry") or decision.get("entry_price") or market.get("price") or market.get("mark_price") or market.get("last_price"), 0.0)
    if qty > 0 and price > 0:
        return qty * price
    return None


def _profile_hash_block(profile: Mapping[str, Any], research_signal: Mapping[str, Any], config: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    blocks: list[str] = []
    checks: dict[str, Any] = {}
    expected_hash = profile.get("profile_sha256") or profile.get("profile_hash")
    actual_hash = research_signal.get("profile_sha256") or research_signal.get("profile_hash") or profile.get("actual_profile_sha256")
    checks["profile_hash_expected_present"] = bool(expected_hash)
    checks["profile_hash_actual_present"] = bool(actual_hash)
    checks["profile_hash_match"] = bool(expected_hash and actual_hash and expected_hash == actual_hash)
    if expected_hash and actual_hash and expected_hash != actual_hash:
        blocks.append("PROFILE_HASH_GATE_BLOCKED")
    if expected_hash and not actual_hash and config.get("require_profile_hash", True) is True:
        blocks.append("PROFILE_HASH_MISSING_BLOCKED")
    return blocks, checks


def _status_for_blocks(blocks: list[str], stage: str) -> str:
    block_set = set(blocks)
    if {"CHAIN_DECISION_ID_MISSING_BLOCKED", "CHAIN_RESEARCH_SIGNAL_ID_MISSING_BLOCKED", "CHAIN_PROFILE_ID_MISSING_BLOCKED"} & block_set:
        return BLOCK_INVALID_CANONICAL_ID_CHAIN
    if "APPROVED_PROFILE_GATE_BLOCKED" in block_set:
        return BLOCK_PROFILE_UNAPPROVED
    if "PROFILE_HASH_GATE_BLOCKED" in block_set:
        return BLOCK_PROFILE_HASH_MISMATCH
    if "PROFILE_HASH_MISSING_BLOCKED" in block_set:
        return BLOCK_PROFILE_HASH_MISSING
    if {"DATA_FRESHNESS_GATE_BLOCKED", "OPTIONAL_DATA_STALE_GATE_BLOCKED"} & block_set:
        return BLOCK_STALE_DATA
    if {"FALLBACK_DATA_GATE_BLOCKED", "SYNTHETIC_DATA_GATE_BLOCKED"} & block_set:
        return BLOCK_FALLBACK_OR_SYNTHETIC
    if "SAMPLE_DATA_GATE_BLOCKED" in block_set:
        return BLOCK_SAMPLE_DATA
    if {"OPTIONAL_DATA_MISSING_LIVE_CANDIDATE_BLOCKED", "OPTIONAL_DATA_HEALTH_LIVE_CANDIDATE_BLOCKED"} & block_set:
        return BLOCK_OPTIONAL_DATA_HEALTH
    if "POSITION_LIMIT_GATE_BLOCKED" in block_set:
        return BLOCK_POSITION_LIMIT
    if "DAILY_LOSS_LIMIT_GATE_BLOCKED" in block_set:
        return BLOCK_DAILY_LOSS_LIMIT
    if "MAX_CONSECUTIVE_LOSS_GATE_BLOCKED" in block_set:
        return BLOCK_CONSECUTIVE_LOSS
    if {"SPREAD_SLIPPAGE_GATE_BLOCKED", "SLIPPAGE_EVIDENCE_MISSING_BLOCKED"} & block_set:
        return BLOCK_SPREAD_SLIPPAGE
    if "API_ERROR_RATE_GATE_BLOCKED" in block_set:
        return BLOCK_API_ERROR_RATE
    if "RECONCILIATION_MISMATCH_GATE_BLOCKED" in block_set:
        return BLOCK_RECONCILIATION_MISMATCH
    if "MANUAL_KILL_SWITCH_GATE_BLOCKED" in block_set:
        return BLOCK_MANUAL_KILL_SWITCH
    if "MIN_ORDER_SIZE_GATE_BLOCKED" in block_set:
        return BLOCK_MIN_ORDER_SIZE
    if "MAX_ORDER_NOTIONAL_GATE_BLOCKED" in block_set:
        return BLOCK_MAX_ORDER_NOTIONAL
    if "DAILY_ORDER_COUNT_GATE_BLOCKED" in block_set:
        return BLOCK_DAILY_ORDER_COUNT
    if "FEE_MODEL_GATE_BLOCKED" in block_set:
        return BLOCK_FEE_MODEL
    if {"BALANCE_MARGIN_GATE_BLOCKED", "MARGIN_CHECK_MISSING_BLOCKED"} & block_set:
        return BLOCK_BALANCE_MARGIN
    if "LEVERAGE_LIMIT_GATE_BLOCKED" in block_set:
        return BLOCK_LEVERAGE_LIMIT
    if "VENUE_READINESS_GATE_BLOCKED" in block_set:
        return BLOCK_VENUE_READINESS
    if "STAGE_EXECUTION_DISABLED_BLOCKED" in block_set:
        return BLOCK_STAGE_EXECUTION_DISABLED
    if "RESEARCH_SIGNAL_TRADE_PERMISSION_BLOCKED" in block_set:
        return BLOCK_RESEARCH_PERMISSION
    normalized_stage = stage.strip().lower()
    if normalized_stage in {"signed_testnet", "testnet"}:
        return PASS_SIGNED_TESTNET
    if normalized_stage == "paper":
        return PASS_PAPER
    return PASS_REVIEW_ONLY


def evaluate_pre_order_risk_gate(
    *,
    decision: Mapping[str, Any],
    research_signal: Mapping[str, Any],
    profile: Mapping[str, Any],
    runtime_state: Mapping[str, Any] | None = None,
    market_state: Mapping[str, Any] | None = None,
    gate_config: Mapping[str, Any] | None = None,
) -> PreOrderRiskGateResult:
    """Evaluate the canonical Step293 pre-order risk gate.

    This gate is a permission artifact only. It never submits orders, never reads
    secret values, never mutates runtime settings, and never promotes a strategy.
    """
    runtime = dict(runtime_state or {})
    market = dict(market_state or {})
    config = dict(gate_config or {})
    blocks: list[str] = []
    reduces: list[str] = []
    policy_checks: dict[str, Any] = {}

    decision_id = _text(decision.get("decision_id") or decision.get("id"))
    research_signal_id = _text(research_signal.get("research_signal_id") or research_signal.get("signal_id"))
    profile_id = _text(profile.get("profile_id") or research_signal.get("profile_id"))

    if not decision_id:
        blocks.append("CHAIN_DECISION_ID_MISSING_BLOCKED")
    if not research_signal_id:
        blocks.append("CHAIN_RESEARCH_SIGNAL_ID_MISSING_BLOCKED")
    if not profile_id:
        blocks.append("CHAIN_PROFILE_ID_MISSING_BLOCKED")
    policy_checks["canonical_id_chain_complete"] = bool(decision_id and research_signal_id and profile_id)

    profile_approved = _as_bool(profile.get("approved") or profile.get("approval_status") == "approved")
    policy_checks["approved_profile"] = profile_approved
    if not profile_approved:
        blocks.append("APPROVED_PROFILE_GATE_BLOCKED")
    hash_blocks, hash_checks = _profile_hash_block(profile, research_signal, config)
    blocks.extend(hash_blocks)
    policy_checks.update(hash_checks)

    price_stale = research_signal.get("stale") is True or research_signal.get("data_stale") is True or market.get("stale") is True or market.get("price_stale") is True
    policy_checks["data_fresh"] = not price_stale
    if price_stale:
        blocks.append("DATA_FRESHNESS_GATE_BLOCKED")
    if research_signal.get("sample_used") is True or market.get("sample_used") is True or research_signal.get("sample_flag") is True or market.get("sample_flag") is True:
        blocks.append("SAMPLE_DATA_GATE_BLOCKED")
    if research_signal.get("synthetic_used") is True or market.get("synthetic_used") is True or research_signal.get("synthetic_flag") is True or market.get("synthetic_flag") is True:
        blocks.append("SYNTHETIC_DATA_GATE_BLOCKED")
    if research_signal.get("fallback_used") is True or market.get("fallback_used") is True or research_signal.get("fallback_flag") is True or market.get("fallback_flag") is True:
        blocks.append("FALLBACK_DATA_GATE_BLOCKED")
    policy_checks["fallback_synthetic_sample_clear"] = not any(reason in blocks for reason in ("SAMPLE_DATA_GATE_BLOCKED", "SYNTHETIC_DATA_GATE_BLOCKED", "FALLBACK_DATA_GATE_BLOCKED"))

    stage = _text(config.get("stage") or runtime.get("stage") or "paper").lower()
    candidate_mode = stage in {"signed_testnet", "testnet", "live_canary", "live", "live_scaled"} or _as_bool(config.get("promotion_candidate"))
    if research_signal.get("stale_optional_data") is True or _int(research_signal.get("stale_optional_source_count"), 0) > 0:
        blocks.append("OPTIONAL_DATA_STALE_GATE_BLOCKED")
    if candidate_mode and (research_signal.get("missing_optional_data_neutral") is True or _as_bool(research_signal.get("neutral_due_to_missing"))):
        blocks.append("OPTIONAL_DATA_MISSING_LIVE_CANDIDATE_BLOCKED")
    if candidate_mode and research_signal.get("live_candidate_eligible") is False:
        blocks.append("OPTIONAL_DATA_HEALTH_LIVE_CANDIDATE_BLOCKED")
    policy_checks["optional_data_live_candidate_eligible"] = bool(research_signal.get("live_candidate_eligible", False))

    max_positions = _int(config.get("max_open_positions"), 1)
    open_positions = _int(runtime.get("open_positions"), 0)
    policy_checks["position_limit_ok"] = open_positions < max_positions
    if open_positions >= max_positions:
        blocks.append("POSITION_LIMIT_GATE_BLOCKED")
    daily_loss_limit_r = _float(config.get("daily_loss_limit_r"), -2.0)
    daily_pnl_r = _float(runtime.get("daily_pnl_r"), 0.0)
    policy_checks["daily_loss_limit_ok"] = daily_pnl_r > daily_loss_limit_r
    if daily_pnl_r <= daily_loss_limit_r:
        blocks.append("DAILY_LOSS_LIMIT_GATE_BLOCKED")
    daily_loss_limit_usdt = config.get("daily_loss_limit_usdt")
    if daily_loss_limit_usdt is not None and _float(runtime.get("daily_pnl_usdt"), 0.0) <= -abs(_float(daily_loss_limit_usdt)):
        blocks.append("DAILY_LOSS_LIMIT_GATE_BLOCKED")
    max_consecutive_losses = _int(config.get("max_consecutive_losses"), 3)
    consecutive_losses = _int(runtime.get("consecutive_losses"), 0)
    policy_checks["consecutive_loss_limit_ok"] = consecutive_losses < max_consecutive_losses
    if consecutive_losses >= max_consecutive_losses:
        blocks.append("MAX_CONSECUTIVE_LOSS_GATE_BLOCKED")

    max_daily_order_count = config.get("max_daily_order_count")
    if max_daily_order_count is not None and _int(runtime.get("daily_order_count"), 0) >= _int(max_daily_order_count):
        blocks.append("DAILY_ORDER_COUNT_GATE_BLOCKED")

    max_spread_bps = _float(config.get("max_spread_bps"), 10.0)
    max_slippage_bps = _float(config.get("max_slippage_bps"), 15.0)
    spread_bps = _float(market.get("spread_bps"), 0.0)
    slippage_bps = _float(market.get("slippage_bps") or market.get("estimated_slippage_bps"), 0.0)
    policy_checks["spread_slippage_ok"] = spread_bps <= max_spread_bps and slippage_bps <= max_slippage_bps
    if spread_bps > max_spread_bps or slippage_bps > max_slippage_bps:
        blocks.append("SPREAD_SLIPPAGE_GATE_BLOCKED")
    if config.get("require_slippage_estimate") is True and not ("slippage_bps" in market or "estimated_slippage_bps" in market):
        blocks.append("SLIPPAGE_EVIDENCE_MISSING_BLOCKED")

    max_api_error_rate = _float(config.get("max_api_error_rate"), 0.05)
    api_error_rate = _float(runtime.get("api_error_rate"), 0.0)
    policy_checks["api_error_rate_ok"] = api_error_rate <= max_api_error_rate
    if api_error_rate > max_api_error_rate:
        blocks.append("API_ERROR_RATE_GATE_BLOCKED")
    reconciliation_mismatch = runtime.get("reconciliation_mismatch") is True or _float(runtime.get("reconciliation_mismatch_rate"), 0.0) > _float(config.get("max_reconciliation_mismatch_rate"), 0.0)
    policy_checks["reconciliation_mismatch_clear"] = not reconciliation_mismatch
    if reconciliation_mismatch:
        blocks.append("RECONCILIATION_MISMATCH_GATE_BLOCKED")
    manual_kill_switch = runtime.get("manual_kill_switch") is True or runtime.get("manual_kill_switch_active") is True
    policy_checks["manual_kill_switch_clear"] = not manual_kill_switch
    if manual_kill_switch:
        blocks.append("MANUAL_KILL_SWITCH_GATE_BLOCKED")

    order_notional = _order_notional_usdt(decision, market, runtime)
    min_order_notional = config.get("min_order_notional_usdt")
    max_order_notional = config.get("max_order_notional_usdt")
    if min_order_notional is not None and order_notional is not None and order_notional < _float(min_order_notional):
        blocks.append("MIN_ORDER_SIZE_GATE_BLOCKED")
    if max_order_notional is not None and order_notional is not None and order_notional > _float(max_order_notional):
        blocks.append("MAX_ORDER_NOTIONAL_GATE_BLOCKED")
    if config.get("require_min_order_size_check") is True and min_order_notional is None and not market.get("min_order_size_check_passed"):
        blocks.append("MIN_ORDER_SIZE_GATE_BLOCKED")
    policy_checks["order_notional_usdt"] = order_notional

    if config.get("require_fee_model") is True and not (market.get("fee_model") or market.get("fee_bps") is not None or market.get("estimated_fee_usdt") is not None):
        blocks.append("FEE_MODEL_GATE_BLOCKED")
    if config.get("require_margin_check") is True:
        available_margin = _float(runtime.get("available_margin_usdt") or runtime.get("available_balance_usdt"), -1.0)
        required_margin = _float(runtime.get("required_margin_usdt") or ((order_notional or 0.0) / max(_float(runtime.get("leverage"), 1.0), 1e-9)), 0.0)
        if available_margin < 0 or available_margin < required_margin:
            blocks.append("BALANCE_MARGIN_GATE_BLOCKED")
    if config.get("require_balance_check") is True and order_notional is not None:
        available_balance = _float(runtime.get("available_balance_usdt"), -1.0)
        if available_balance < 0 or available_balance < order_notional:
            blocks.append("BALANCE_MARGIN_GATE_BLOCKED")
    max_leverage = config.get("max_leverage")
    if max_leverage is not None and _float(runtime.get("leverage"), 1.0) > _float(max_leverage):
        blocks.append("LEVERAGE_LIMIT_GATE_BLOCKED")
    if config.get("require_venue_readiness") is True and market.get("venue_readiness_valid") is not True:
        blocks.append("VENUE_READINESS_GATE_BLOCKED")

    if stage in {"signed_testnet", "testnet"} and config.get("testnet_order_submission_allowed") is False:
        blocks.append("STAGE_EXECUTION_DISABLED_BLOCKED")
    if stage in {"live_canary", "live", "live_scaled"} and (config.get("live_trading_enabled") is not True or config.get("external_order_submission_allowed") is not True):
        blocks.append("STAGE_EXECUTION_DISABLED_BLOCKED")

    tp = research_signal.get("trade_permission") if isinstance(research_signal.get("trade_permission"), Mapping) else {}
    allow_long = bool(tp.get("allow_long", decision.get("side") == "LONG" or decision.get("direction") == "LONG"))
    allow_short = bool(tp.get("allow_short", decision.get("side") == "SHORT" or decision.get("direction") == "SHORT"))
    allow_new = bool(tp.get("allow_new_position", decision.get("side") in {"LONG", "SHORT"} or decision.get("direction") in {"LONG", "SHORT"}))
    if tp.get("risk_level") == "reduced":
        reduces.append("RESEARCH_SIGNAL_REDUCED_RISK_LEVEL")
    if tp.get("risk_level") == "blocked":
        blocks.append("RESEARCH_SIGNAL_TRADE_PERMISSION_BLOCKED")

    status = _status_for_blocks(blocks, stage)
    approved = status in {PASS_REVIEW_ONLY, PASS_PAPER, PASS_SIGNED_TESTNET} and allow_new and (allow_long or allow_short)
    risk_level = "blocked" if status.startswith("BLOCK_") else "reduced" if reduces else "normal"
    unique_blocks = sorted(set(blocks))
    unique_reduces = sorted(set(reduces))
    policy_checks.update(
        {
            "stage": stage,
            "status": status,
            "approved": approved,
            "allow_new_from_research_permission": allow_new,
            "allow_long_from_research_permission": allow_long,
            "allow_short_from_research_permission": allow_short,
            "order_notional_within_min_max": not ({"MIN_ORDER_SIZE_GATE_BLOCKED", "MAX_ORDER_NOTIONAL_GATE_BLOCKED"} & set(unique_blocks)),
            "fee_model_ok": "FEE_MODEL_GATE_BLOCKED" not in unique_blocks,
            "balance_margin_ok": "BALANCE_MARGIN_GATE_BLOCKED" not in unique_blocks,
            "leverage_ok": "LEVERAGE_LIMIT_GATE_BLOCKED" not in unique_blocks,
            "venue_readiness_ok": "VENUE_READINESS_GATE_BLOCKED" not in unique_blocks,
            "stage_execution_enabled_for_requested_stage": "STAGE_EXECUTION_DISABLED_BLOCKED" not in unique_blocks,
        }
    )
    payload = {
        "decision_id": decision_id,
        "research_signal_id": research_signal_id,
        "profile_id": profile_id,
        "status": status,
        "stage": stage,
        "block_reasons": unique_blocks,
        "reduce_reasons": unique_reduces,
        "risk_level": risk_level,
        "gate_version": PRE_ORDER_RISK_GATE_VERSION,
    }
    result = PreOrderRiskGateResult(
        risk_gate_id=risk_gate_id_from_payload(decision, research_signal, profile, payload),
        decision_id=decision_id,
        research_signal_id=research_signal_id,
        profile_id=profile_id,
        status=status,
        stage=stage,
        approved=approved,
        risk_level=risk_level,
        allow_new_position=approved,
        allow_long=approved and allow_long,
        allow_short=approved and allow_short,
        block_reasons=unique_blocks,
        reduce_reasons=unique_reduces,
        policy_checks=policy_checks,
        order_notional_usdt=order_notional,
        max_order_notional_usdt=_float(max_order_notional) if max_order_notional is not None else None,
        min_order_notional_usdt=_float(min_order_notional) if min_order_notional is not None else None,
    )
    result.risk_gate_report_sha256 = sha256_json({k: v for k, v in asdict(result).items() if k != "risk_gate_report_sha256"})
    return result

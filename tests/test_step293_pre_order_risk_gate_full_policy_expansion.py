from __future__ import annotations

from crypto_ai_system.trading.pre_order_risk_gate import (
    BLOCK_API_ERROR_RATE,
    BLOCK_BALANCE_MARGIN,
    BLOCK_CONSECUTIVE_LOSS,
    BLOCK_DAILY_LOSS_LIMIT,
    BLOCK_DAILY_ORDER_COUNT,
    BLOCK_FEE_MODEL,
    BLOCK_FALLBACK_OR_SYNTHETIC,
    BLOCK_LEVERAGE_LIMIT,
    BLOCK_MANUAL_KILL_SWITCH,
    BLOCK_MAX_ORDER_NOTIONAL,
    BLOCK_MIN_ORDER_SIZE,
    BLOCK_POSITION_LIMIT,
    BLOCK_PROFILE_HASH_MISMATCH,
    BLOCK_PROFILE_UNAPPROVED,
    BLOCK_RECONCILIATION_MISMATCH,
    BLOCK_SPREAD_SLIPPAGE,
    BLOCK_STAGE_EXECUTION_DISABLED,
    BLOCK_STALE_DATA,
    BLOCK_VENUE_READINESS,
    PASS_PAPER,
    PASS_REVIEW_ONLY,
    PASS_SIGNED_TESTNET,
    PRE_ORDER_RISK_GATE_VERSION,
    evaluate_pre_order_risk_gate,
)


def _decision(**overrides):
    payload = {
        "decision_id": "decision_step293_1",
        "side": "LONG",
        "entry": 100.0,
        "quantity": 0.1,
        "order_notional_usdt": 10.0,
    }
    payload.update(overrides)
    return payload


def _research_signal(**overrides):
    payload = {
        "research_signal_id": "research_signal_step293_1",
        "profile_id": "profile_step293_1",
        "profile_sha256": "profile_hash_ok",
        "live_candidate_eligible": True,
        "trade_permission": {
            "allow_long": True,
            "allow_short": False,
            "allow_new_position": True,
            "risk_level": "normal",
        },
    }
    payload.update(overrides)
    return payload


def _profile(**overrides):
    payload = {
        "profile_id": "profile_step293_1",
        "approved": True,
        "profile_sha256": "profile_hash_ok",
    }
    payload.update(overrides)
    return payload


def _runtime(**overrides):
    payload = {
        "stage": "paper",
        "open_positions": 0,
        "daily_pnl_r": 0.0,
        "daily_pnl_usdt": 0.0,
        "consecutive_losses": 0,
        "daily_order_count": 0,
        "api_error_rate": 0.0,
        "reconciliation_mismatch": False,
        "manual_kill_switch": False,
        "available_balance_usdt": 1000.0,
        "available_margin_usdt": 1000.0,
        "leverage": 1.0,
    }
    payload.update(overrides)
    return payload


def _market(**overrides):
    payload = {
        "spread_bps": 1.0,
        "slippage_bps": 1.0,
        "fee_bps": 2.0,
        "min_order_size_check_passed": True,
        "venue_readiness_valid": True,
    }
    payload.update(overrides)
    return payload


def _config(**overrides):
    payload = {
        "stage": "paper",
        "max_open_positions": 1,
        "daily_loss_limit_r": -2.0,
        "daily_loss_limit_usdt": 100.0,
        "max_consecutive_losses": 3,
        "max_daily_order_count": 3,
        "max_spread_bps": 10.0,
        "max_slippage_bps": 15.0,
        "max_api_error_rate": 0.05,
        "min_order_notional_usdt": 5.0,
        "max_order_notional_usdt": 100.0,
        "require_fee_model": True,
        "require_margin_check": True,
        "require_balance_check": False,
        "max_leverage": 3.0,
        "require_venue_readiness": True,
    }
    payload.update(overrides)
    return payload


def _evaluate(**overrides):
    return evaluate_pre_order_risk_gate(
        decision=overrides.get("decision", _decision()),
        research_signal=overrides.get("research_signal", _research_signal()),
        profile=overrides.get("profile", _profile()),
        runtime_state=overrides.get("runtime_state", _runtime()),
        market_state=overrides.get("market_state", _market()),
        gate_config=overrides.get("gate_config", _config()),
    )


def test_step293_pre_order_risk_gate_passes_paper_with_full_policy_context() -> None:
    result = _evaluate()

    assert result.status == PASS_PAPER
    assert result.approved is True
    assert result.allow_new_position is True
    assert result.gate_version == PRE_ORDER_RISK_GATE_VERSION
    assert result.risk_gate_id.startswith("risk_gate_")
    assert result.risk_gate_report_sha256
    assert result.policy_checks["canonical_id_chain_complete"] is True
    assert result.policy_checks["fee_model_ok"] is True
    assert result.policy_checks["balance_margin_ok"] is True
    assert result.policy_checks["leverage_ok"] is True


def test_step293_review_only_stage_is_not_testnet_or_live_permission() -> None:
    result = _evaluate(runtime_state=_runtime(stage="review_only"), gate_config=_config(stage="review_only"))

    assert result.status == PASS_REVIEW_ONLY
    assert result.approved is True
    assert result.stage == "review_only"
    assert result.policy_checks["stage_execution_enabled_for_requested_stage"] is True


def test_step293_signed_testnet_requires_explicit_submission_allowed() -> None:
    blocked = _evaluate(runtime_state=_runtime(stage="signed_testnet"), gate_config=_config(stage="signed_testnet", testnet_order_submission_allowed=False))
    allowed = _evaluate(runtime_state=_runtime(stage="signed_testnet"), gate_config=_config(stage="signed_testnet", testnet_order_submission_allowed=True))

    assert blocked.status == BLOCK_STAGE_EXECUTION_DISABLED
    assert "STAGE_EXECUTION_DISABLED_BLOCKED" in blocked.block_reasons
    assert allowed.status == PASS_SIGNED_TESTNET
    assert allowed.approved is True


def test_step293_profile_and_data_blocks_are_mapped_to_status_codes() -> None:
    unapproved = _evaluate(profile=_profile(approved=False))
    hash_mismatch = _evaluate(profile=_profile(profile_sha256="expected"), research_signal=_research_signal(profile_sha256="actual"))
    stale = _evaluate(research_signal=_research_signal(stale=True))
    fallback = _evaluate(research_signal=_research_signal(fallback_used=True))

    assert unapproved.status == BLOCK_PROFILE_UNAPPROVED
    assert hash_mismatch.status == BLOCK_PROFILE_HASH_MISMATCH
    assert stale.status == BLOCK_STALE_DATA
    assert fallback.status == BLOCK_FALLBACK_OR_SYNTHETIC


def test_step293_position_loss_api_reconciliation_and_kill_switch_blocks() -> None:
    assert _evaluate(runtime_state=_runtime(open_positions=1)).status == BLOCK_POSITION_LIMIT
    assert _evaluate(runtime_state=_runtime(daily_pnl_r=-2.0)).status == BLOCK_DAILY_LOSS_LIMIT
    assert _evaluate(runtime_state=_runtime(consecutive_losses=3)).status == BLOCK_CONSECUTIVE_LOSS
    assert _evaluate(runtime_state=_runtime(api_error_rate=0.10)).status == BLOCK_API_ERROR_RATE
    assert _evaluate(runtime_state=_runtime(reconciliation_mismatch=True)).status == BLOCK_RECONCILIATION_MISMATCH
    assert _evaluate(runtime_state=_runtime(manual_kill_switch=True)).status == BLOCK_MANUAL_KILL_SWITCH
    assert _evaluate(runtime_state=_runtime(daily_order_count=3)).status == BLOCK_DAILY_ORDER_COUNT


def test_step293_market_cost_order_size_margin_leverage_and_venue_blocks() -> None:
    assert _evaluate(market_state=_market(spread_bps=20.0)).status == BLOCK_SPREAD_SLIPPAGE
    assert _evaluate(decision=_decision(order_notional_usdt=1.0)).status == BLOCK_MIN_ORDER_SIZE
    assert _evaluate(decision=_decision(order_notional_usdt=200.0)).status == BLOCK_MAX_ORDER_NOTIONAL
    assert _evaluate(market_state={"spread_bps": 1.0, "slippage_bps": 1.0, "min_order_size_check_passed": True, "venue_readiness_valid": True}).status == BLOCK_FEE_MODEL
    assert _evaluate(runtime_state=_runtime(available_margin_usdt=1.0)).status == BLOCK_BALANCE_MARGIN
    assert _evaluate(runtime_state=_runtime(leverage=10.0)).status == BLOCK_LEVERAGE_LIMIT
    assert _evaluate(market_state=_market(venue_readiness_valid=False)).status == BLOCK_VENUE_READINESS

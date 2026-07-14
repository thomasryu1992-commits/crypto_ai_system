from __future__ import annotations

from pathlib import Path

import yaml

from crypto_ai_system.execution.exchange_adapter_contract import (
    DisabledExchangeAdapter,
    EXCHANGE_ADAPTER_CONTRACT_VERSION,
    validate_adapter_capabilities,
)
from crypto_ai_system.execution.signed_testnet_readiness import (
    SIGNED_TESTNET_READINESS_VERSION,
    evaluate_signed_testnet_preflight,
    validate_signed_testnet_approval,
    validate_testnet_secret_policy,
)
from crypto_ai_system.utils.audit import utc_now_canonical


def _valid_approval() -> dict:
    return {
        "approval_packet_id": "approval_packet_step273_test",
        "approval_intake_id": "approval_intake_step273_test",
        "approver_id": "operator_thomas_review_only",
        "approver_role": "operator",
        "approval_ticket_id": "TICKET-STEP273-TESTNET-CONTRACT",
        "approval_signature": "signed-testnet-contract-review-only-signature",
        "timestamp_utc": utc_now_canonical(),
    }


def _valid_secret_status() -> dict:
    return {
        "has_api_key": True,
        "has_api_secret": True,
        "key_scope": "testnet",
        "base_url": "https://testnet.binancefuture.com",
        "secret_file_loaded": False,
        "secret_file_created": False,
        "secret_bytes_read": False,
        "live_key_detected": False,
    }


def _valid_venue_state() -> dict:
    return {
        "balance_read_contract_available": True,
        "position_read_contract_available": True,
        "open_orders_read_contract_available": True,
        "orderbook_read_contract_available": True,
        "fee_model_available": True,
        "slippage_estimate_available": True,
        "min_order_size_valid": True,
    }


def _valid_runtime_flags() -> dict:
    return {
        "trading_mode": "paper",
        "testnet_signed_order_enabled": False,
        "enable_real_orders": False,
        "live_trading_enabled": False,
        "allow_live_trading": False,
    }


def test_step273_disabled_exchange_adapter_blocks_place_order() -> None:
    adapter = DisabledExchangeAdapter(venue="binance_futures", environment="testnet")
    capabilities = adapter.get_capabilities()
    validation = validate_adapter_capabilities(capabilities)
    assert validation["valid"] is True
    assert validation["contract_ready"] is True
    assert validation["contract_version"] == EXCHANGE_ADAPTER_CONTRACT_VERSION

    result = adapter.place_order({"symbol": "BTCUSDT", "side": "BUY", "notional_usdt": 5})
    assert result["status"] == "PLACE_ORDER_DISABLED_STEP273"
    assert result["submitted"] is False
    assert result["exchange_order_id"] is None
    assert result["external_order_submission_performed"] is False
    assert result["order_submission_enabled_by_contract"] is False


def test_step273_adapter_capability_validation_requires_read_and_pretrade_contracts() -> None:
    invalid_capabilities = {
        "venue": "binance_futures",
        "environment": "testnet",
        "testnet_only": True,
        "supports_balance_read": True,
        "supports_positions_read": False,
        "supports_open_orders_read": True,
        "supports_orderbook_read": True,
        "supports_fee_estimate": False,
        "supports_slippage_estimate": True,
        "supports_min_order_validation": True,
        "supports_fetch_order": True,
        "supports_place_order": False,
    }
    validation = validate_adapter_capabilities(invalid_capabilities)
    assert validation["valid"] is False
    assert "supports_positions_read" in validation["missing_capabilities"]
    assert "supports_fee_estimate" in validation["missing_capabilities"]


def test_step273_secret_policy_blocks_live_key_and_actual_secret_values() -> None:
    result = validate_testnet_secret_policy(
        {
            "api_key": "real-looking-key-value",
            "api_secret": "real-looking-secret-value",
            "has_api_key": True,
            "has_api_secret": True,
            "key_scope": "live",
            "base_url": "https://fapi.binance.com",
            "live_key_detected": True,
        }
    )
    assert result["valid"] is False
    assert "SECRET_VALUE_PROVIDED_BLOCKED" in result["block_reasons"]
    assert "LIVE_KEY_DETECTED_BLOCKED" in result["block_reasons"]
    assert "TESTNET_BASE_URL_NOT_TESTNET_BLOCKED" in result["block_reasons"]


def test_step273_missing_manual_signed_approval_fails_closed() -> None:
    validation = validate_signed_testnet_approval({"approval_packet_id": "packet_only"})
    assert validation["valid"] is False
    assert "SIGNED_TESTNET_APPROVAL_APPROVAL_SIGNATURE_MISSING" in validation["block_reasons"]
    assert "SIGNED_TESTNET_APPROVAL_TIMESTAMP_UTC_MISSING" in validation["block_reasons"]


def test_step273_preflight_contract_ready_but_execution_remains_disabled() -> None:
    adapter = DisabledExchangeAdapter()
    result = evaluate_signed_testnet_preflight(
        adapter_capabilities=adapter.get_capabilities(),
        secret_status=_valid_secret_status(),
        manual_approval=_valid_approval(),
        venue_state=_valid_venue_state(),
        risk_limits={
            "max_order_notional_usdt": 5,
            "max_daily_order_count": 3,
            "manual_kill_switch_required": True,
        },
        runtime_flags=_valid_runtime_flags(),
    )
    assert result["readiness_version"] == SIGNED_TESTNET_READINESS_VERSION
    assert result["contract_review_ready"] is True
    assert result["ready_for_signed_testnet_execution"] is False
    assert result["testnet_order_submission_allowed"] is False
    assert result["external_order_submission_performed"] is False
    assert result["block_reasons"] == []


def test_step273_preflight_blocks_if_testnet_order_flag_enabled() -> None:
    adapter = DisabledExchangeAdapter()
    runtime_flags = _valid_runtime_flags()
    runtime_flags["testnet_signed_order_enabled"] = True
    result = evaluate_signed_testnet_preflight(
        adapter_capabilities=adapter.get_capabilities(),
        secret_status=_valid_secret_status(),
        manual_approval=_valid_approval(),
        venue_state=_valid_venue_state(),
        risk_limits={
            "max_order_notional_usdt": 5,
            "max_daily_order_count": 3,
            "manual_kill_switch_required": True,
        },
        runtime_flags=runtime_flags,
    )
    assert result["contract_review_ready"] is False
    assert "TESTNET_SIGNED_ORDER_ENABLED_MUST_REMAIN_FALSE_STEP273" in result["block_reasons"]
    assert result["ready_for_signed_testnet_execution"] is False


def test_step273_version_and_config_safety_flags() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.286.2"' in pyproject

    settings = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    assert settings["project"]["version"] == "p70_venue_neutral_execution_contract"
    contract = settings["execution"]["signed_testnet_adapter_contract"]
    assert contract["contract_review_only"] is True
    assert contract["place_order_enabled"] is False
    assert contract["api_key_access_allowed"] is False
    assert contract["secret_file_creation_allowed"] is False
    assert settings["safety"]["live_trading_enabled"] is False
    assert settings["safety"]["testnet_signed_order_enabled"] is False

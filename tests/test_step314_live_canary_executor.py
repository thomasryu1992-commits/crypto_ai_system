from __future__ import annotations

from pathlib import Path

import yaml

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.live_canary_approval_packet import (
    OperatorLiveCanaryApprovalRequest,
    build_live_canary_approval_packet,
)
from crypto_ai_system.execution.live_canary_order_executor import (
    BLOCK_APPROVAL_PACKET_NOT_VALID,
    BLOCK_LIVE_CANARY_EXECUTION_DISABLED,
    BLOCK_LIVE_ORDER_SUBMISSION_DISABLED,
    BLOCK_MISSING_APPROVAL_PACKET,
    BLOCK_PLACE_ORDER_DISABLED,
    BLOCK_SECRET_VALUE_ACCESS,
    BLOCK_UNSAFE_RUNTIME_FLAG,
    STATUS_BLOCKED,
    STEP314_LIVE_CANARY_ORDER_EXECUTOR_VERSION,
    LiveCanaryOrderExecutorPolicy,
    build_live_canary_order_execution_record,
    persist_live_canary_order_execution_record,
    run_live_canary_order_executor_latest,
)
from crypto_ai_system.execution.live_key_scope_validator import build_live_key_scope_validation
from crypto_ai_system.execution.live_read_only_adapter_probe import build_live_read_only_adapter_probe
from crypto_ai_system.utils.audit import sha256_text


def _canonical_ids() -> dict:
    return {
        "data_snapshot_id": "data_snapshot_step314",
        "feature_snapshot_id": "feature_snapshot_step314",
        "research_signal_id": "research_signal_step314",
        "profile_id": "profile_step314",
        "approval_packet_id": "approval_packet_step314",
        "approval_intake_id": "approval_intake_step314",
        "decision_id": "decision_step314",
        "risk_gate_id": "risk_gate_step314",
        "order_intent_id": "order_intent_step314",
        "execution_id": "execution_step314_signed_testnet",
        "reconciliation_id": "reconciliation_step314_signed_testnet",
    }


def _session_close() -> dict:
    return {
        **_canonical_ids(),
        "signed_testnet_session_close_report_id": "signed_testnet_session_step314",
        "signed_testnet_session_close_report_sha256": sha256_text("signed_testnet_session_step314"),
        "status": "SIGNED_TESTNET_SESSION_CLOSE_REPORT_RECORDED_REVIEW_ONLY",
        "orders_submitted_count": 1,
        "orders_filled_count": 1,
        "orders_rejected_count": 0,
        "orders_not_submitted_count": 0,
        "reconciliation_mismatch_count": 0,
        "api_error_count": 0,
        "latency_summary": {"count": 1, "avg": 120.0},
        "slippage_summary": {"count": 1, "avg": 1.2},
        "manual_override_count": 0,
        "promotion_recommendation": "expand_signed_testnet_validation",
        "external_order_submission_performed": False,
        "live_trading_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
    }


def _live_probe() -> dict:
    probe = build_live_read_only_adapter_probe(
        live_metadata={
            "venue": "binance_futures_live",
            "environment": "live",
            "base_url": "https://fapi.binance.com",
            "scope": ["read_only"],
            "operator_id": "operator_thomas_review_only",
            "metadata_only": True,
            "secret_reference_id": "metadata_ref:live/binance_futures/read_only_reference",
            "api_key_value_access_allowed": False,
            "api_secret_value_access_allowed": False,
            "secret_file_access_allowed": False,
            "secret_file_creation_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "withdrawal_enabled": False,
            "transfer_enabled": False,
            "leverage_mutation_enabled": False,
            "live_trading_enabled": False,
        }
    )
    probe.update(_canonical_ids())
    return probe


def _key_scope() -> dict:
    validation = build_live_key_scope_validation(
        {
            "secret_reference_id": "metadata_ref:live/binance_futures/read_only_reference",
            "key_fingerprint_sha256": sha256_text("step314-live-read-only-metadata-reference"),
            "environment": "live",
            "venue": "binance_futures_live",
            "base_url": "https://fapi.binance.com",
            "scope": ["read_only"],
            "operator_id": "operator_thomas_review_only",
            "metadata_only": True,
            "withdrawal_enabled": False,
            "transfer_enabled": False,
            "admin_enabled": False,
            "write_enabled": False,
            "trade_enabled": False,
            "ip_whitelist_enabled": True,
            "ip_whitelist_metadata_only": True,
        },
        live_read_only_probe=_live_probe(),
    )
    validation.update(_canonical_ids())
    return validation


def _approval_packet() -> dict:
    return build_live_canary_approval_packet(
        signed_testnet_session_close_report=_session_close(),
        live_read_only_probe=_live_probe(),
        live_key_scope_validation=_key_scope(),
        operator_live_canary_approval_request=OperatorLiveCanaryApprovalRequest().to_dict(),
    )


def _payload() -> dict:
    return {
        **_canonical_ids(),
        "venue": "binance_futures_live",
        "environment": "live_canary",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "MARKET",
        "quantity": 0.0001,
        "notional_usdt": 5.0,
        "idempotency_key": "live-canary-idempotency-step314",
        "review_only": True,
        "would_submit_only": True,
        "actual_submission_performed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "live_order_submission_allowed": False,
    }


def test_step314_builds_disabled_live_canary_executor_record() -> None:
    record = build_live_canary_order_execution_record(approval_packet=_approval_packet(), live_canary_order_payload=_payload())

    assert record["version"] == STEP314_LIVE_CANARY_ORDER_EXECUTOR_VERSION
    assert record["status"] == STATUS_BLOCKED
    assert record["submitted_to_exchange"] is False
    assert record["actual_submission_performed"] is False
    assert record["external_order_submission_performed"] is False
    assert record["adapter_called_for_write"] is False
    assert record["exchange_order_id"] is None
    assert BLOCK_LIVE_CANARY_EXECUTION_DISABLED in record["block_reasons"]
    assert BLOCK_LIVE_ORDER_SUBMISSION_DISABLED in record["block_reasons"]
    assert BLOCK_PLACE_ORDER_DISABLED in record["block_reasons"]
    assert record["live_canary_execution_enabled"] is False
    assert record["live_order_submission_allowed"] is False
    assert record["lifecycle_events"]
    assert record["reconciliation_required"] is False


def test_step314_blocks_missing_or_invalid_approval_packet() -> None:
    missing = build_live_canary_order_execution_record(approval_packet=None, live_canary_order_payload=_payload())
    assert missing["status"] == STATUS_BLOCKED
    assert BLOCK_MISSING_APPROVAL_PACKET in missing["block_reasons"]
    invalid_packet = _approval_packet()
    invalid_packet["valid"] = False
    invalid = build_live_canary_order_execution_record(approval_packet=invalid_packet, live_canary_order_payload=_payload())
    assert BLOCK_APPROVAL_PACKET_NOT_VALID in invalid["block_reasons"]
    assert invalid["submitted_to_exchange"] is False


def test_step314_blocks_secret_and_unsafe_runtime_flags() -> None:
    packet = _approval_packet()
    payload = _payload()
    payload["api_key_value_access_allowed"] = True
    payload["runtime_settings_mutated"] = True
    record = build_live_canary_order_execution_record(approval_packet=packet, live_canary_order_payload=payload)
    assert BLOCK_SECRET_VALUE_ACCESS in record["block_reasons"]
    assert BLOCK_UNSAFE_RUNTIME_FLAG in record["block_reasons"]
    assert record["api_key_value_access_allowed"] is False
    assert record["runtime_settings_mutated"] is False


def test_step314_ignores_exchange_response_without_live_submission() -> None:
    record = build_live_canary_order_execution_record(
        approval_packet=_approval_packet(),
        live_canary_order_payload=_payload(),
        policy=LiveCanaryOrderExecutorPolicy(live_canary_execution_enabled=True, live_order_submission_allowed=True, external_order_submission_allowed=True, place_order_enabled=True, signed_order_executor_enabled=True, write_enabled=True, trade_enabled=True),
        exchange_response={"exchange_order_id": "live_order_should_not_be_used", "status": "FILLED"},
    )
    assert record["submitted_to_exchange"] is False
    assert record["exchange_order_id"] is None
    assert "STEP314_EXCHANGE_RESPONSE_IGNORED_BECAUSE_LIVE_SUBMISSION_IS_DISABLED_BY_DESIGN" in record["warnings"]


def test_step314_persists_executor_and_lifecycle_registry(tmp_path: Path) -> None:
    cfg = load_config(Path.cwd())
    object.__setattr__(cfg, "root", tmp_path)
    record = build_live_canary_order_execution_record(approval_packet=_approval_packet(), live_canary_order_payload=_payload())
    persisted = persist_live_canary_order_execution_record(cfg, record)
    assert persisted["live_canary_order_executor_registry_record_id"]
    assert persisted["live_canary_order_lifecycle_registry_record_id"]
    assert (tmp_path / "storage/latest/live_canary_order_execution_record.json").exists()
    assert (tmp_path / "storage/latest/live_canary_order_lifecycle_events.json").exists()
    assert (tmp_path / "storage/registries/live_canary_order_executor_registry.jsonl").exists()
    assert (tmp_path / "storage/registries/live_canary_order_lifecycle_registry.jsonl").exists()


def test_step314_latest_runner_blocks_by_default(tmp_path: Path) -> None:
    root = tmp_path
    (root / "config").mkdir(parents=True)
    (root / "config/settings.yaml").write_text(Path("config/settings.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    result = run_live_canary_order_executor_latest(project_root=root, approval_packet=_approval_packet(), live_canary_order_payload=_payload())
    assert result["status"] == STATUS_BLOCKED
    assert result["submitted_to_exchange"] is False
    assert (root / "storage/latest/live_canary_order_execution_record.json").exists()


def test_step314_config_flags_remain_disabled() -> None:
    settings = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    cfg = settings["execution"]["live_canary_order_executor"]
    assert cfg["enabled"] is False
    assert cfg["review_only"] is True
    assert cfg["live_canary_execution_enabled"] is False
    assert cfg["live_order_submission_allowed"] is False
    assert cfg["external_order_submission_performed"] is False
    assert cfg["place_order_enabled"] is False
    assert cfg["cancel_order_enabled"] is False
    assert cfg["withdrawal_enabled"] is False
    assert cfg["transfer_enabled"] is False
    assert cfg["admin_enabled"] is False
    assert cfg["write_enabled"] is False
    assert cfg["trade_enabled"] is False
    assert cfg["api_key_value_access_allowed"] is False
    assert cfg["api_secret_value_access_allowed"] is False
    assert cfg["secret_file_access_allowed"] is False
    assert cfg["secret_file_creation_allowed"] is False
    assert settings["safety"]["live_trading_enabled"] is False

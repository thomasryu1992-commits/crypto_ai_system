from __future__ import annotations

from pathlib import Path

import yaml

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.live_canary_approval_packet import (
    BLOCK_CANONICAL_ID_CHAIN_MISSING,
    BLOCK_LIVE_KEY_SCOPE_INVALID,
    BLOCK_MISSING_OPERATOR_REQUEST,
    BLOCK_OPERATOR_REQUESTS_LIVE_ORDER_SUBMISSION,
    BLOCK_SESSION_NO_SUBMITTED_ORDER,
    BLOCK_UNSAFE_RUNTIME_FLAG,
    OperatorLiveCanaryApprovalRequest,
    STATUS_BLOCKED,
    STATUS_READY_REVIEW_ONLY,
    build_live_canary_approval_packet,
    persist_live_canary_approval_packet,
    run_live_canary_approval_packet_latest,
)
from crypto_ai_system.execution.live_key_scope_validator import build_live_key_scope_validation
from crypto_ai_system.execution.live_read_only_adapter_probe import build_live_read_only_adapter_probe
from crypto_ai_system.utils.audit import sha256_text, utc_now_canonical


def _canonical_ids() -> dict:
    return {
        "data_snapshot_id": "data_snapshot_demo",
        "feature_snapshot_id": "feature_snapshot_demo",
        "research_signal_id": "research_signal_demo",
        "profile_id": "profile_demo",
        "approval_packet_id": "approval_packet_demo",
        "approval_intake_id": "approval_intake_demo",
        "decision_id": "decision_demo",
        "risk_gate_id": "risk_gate_demo",
        "order_intent_id": "order_intent_demo",
        "execution_id": "execution_demo",
        "reconciliation_id": "reconciliation_demo",
    }


def _session_close() -> dict:
    return {
        **_canonical_ids(),
        "signed_testnet_session_close_report_id": "signed_testnet_session_demo",
        "signed_testnet_session_close_report_sha256": sha256_text("signed_testnet_session_demo"),
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
            "margin_mode_mutation_enabled": False,
            "live_trading_enabled": False,
        }
    )
    probe.update(_canonical_ids())
    return probe


def _key_scope() -> dict:
    validation = build_live_key_scope_validation(
        {
            "secret_reference_id": "metadata_ref:live/binance_futures/read_only_reference",
            "key_fingerprint_sha256": sha256_text("step312-live-read-only-metadata-reference"),
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


def _operator_request() -> dict:
    return OperatorLiveCanaryApprovalRequest().to_dict()


def test_step313_builds_review_only_live_canary_approval_packet_when_all_evidence_is_valid() -> None:
    packet = build_live_canary_approval_packet(
        signed_testnet_session_close_report=_session_close(),
        live_read_only_probe=_live_probe(),
        live_key_scope_validation=_key_scope(),
        operator_live_canary_approval_request=_operator_request(),
    )

    assert packet["status"] == STATUS_READY_REVIEW_ONLY
    assert packet["valid"] is True
    assert packet["live_canary_approval_review_ready"] is True
    assert packet["live_canary_execution_enabled"] is False
    assert packet["live_canary_ready"] is False
    assert packet["live_order_submission_allowed"] is False
    assert packet["place_order_enabled"] is False
    assert packet["cancel_order_enabled"] is False
    assert packet["api_key_value_access_allowed"] is False
    assert packet["api_secret_value_access_allowed"] is False
    assert packet["block_reasons"] == []


def test_step313_blocks_missing_operator_request_and_missing_canonical_chain() -> None:
    session = _session_close()
    for key in _canonical_ids():
        session.pop(key, None)
    live_probe = _live_probe()
    key_scope = _key_scope()
    for key in _canonical_ids():
        live_probe.pop(key, None)
        key_scope.pop(key, None)
    packet = build_live_canary_approval_packet(
        signed_testnet_session_close_report=session,
        live_read_only_probe=live_probe,
        live_key_scope_validation=key_scope,
        operator_live_canary_approval_request=None,
    )

    assert packet["status"] == STATUS_BLOCKED
    assert packet["valid"] is False
    assert BLOCK_MISSING_OPERATOR_REQUEST in packet["block_reasons"]
    assert BLOCK_CANONICAL_ID_CHAIN_MISSING in packet["block_reasons"]
    assert packet["live_order_submission_allowed"] is False


def test_step313_blocks_session_without_submitted_signed_testnet_order() -> None:
    session = _session_close()
    session["orders_submitted_count"] = 0
    packet = build_live_canary_approval_packet(
        signed_testnet_session_close_report=session,
        live_read_only_probe=_live_probe(),
        live_key_scope_validation=_key_scope(),
        operator_live_canary_approval_request=_operator_request(),
    )

    assert packet["valid"] is False
    assert BLOCK_SESSION_NO_SUBMITTED_ORDER in packet["block_reasons"]
    assert packet["live_canary_execution_enabled"] is False


def test_step313_blocks_operator_request_attempting_to_enable_live_order_submission() -> None:
    request = _operator_request()
    request["request_live_order_submission_enabled"] = True
    packet = build_live_canary_approval_packet(
        signed_testnet_session_close_report=_session_close(),
        live_read_only_probe=_live_probe(),
        live_key_scope_validation=_key_scope(),
        operator_live_canary_approval_request=request,
    )

    assert packet["valid"] is False
    assert BLOCK_OPERATOR_REQUESTS_LIVE_ORDER_SUBMISSION in packet["block_reasons"]
    assert packet["live_order_submission_allowed"] is False


def test_step313_blocks_invalid_live_key_scope_and_unsafe_runtime_flags() -> None:
    key_scope = _key_scope()
    key_scope["valid"] = False
    key_scope["status"] = "LIVE_KEY_SCOPE_VALIDATION_BLOCKED"
    key_scope["place_order_enabled"] = True
    packet = build_live_canary_approval_packet(
        signed_testnet_session_close_report=_session_close(),
        live_read_only_probe=_live_probe(),
        live_key_scope_validation=key_scope,
        operator_live_canary_approval_request=_operator_request(),
    )

    assert packet["valid"] is False
    assert BLOCK_LIVE_KEY_SCOPE_INVALID in packet["block_reasons"]
    assert BLOCK_UNSAFE_RUNTIME_FLAG in packet["block_reasons"]
    assert packet["place_order_enabled"] is False


def test_step313_persists_packet_registry_and_latest(tmp_path: Path) -> None:
    cfg = load_config(Path.cwd())
    object.__setattr__(cfg, "root", tmp_path)
    packet = build_live_canary_approval_packet(
        signed_testnet_session_close_report=_session_close(),
        live_read_only_probe=_live_probe(),
        live_key_scope_validation=_key_scope(),
        operator_live_canary_approval_request=_operator_request(),
    )
    persisted = persist_live_canary_approval_packet(cfg, packet)

    assert persisted["live_canary_approval_registry_record_id"]
    assert (tmp_path / "storage/latest/live_canary_approval_packet.json").exists()
    assert (tmp_path / "storage/latest/live_canary_approval_registry_record.json").exists()
    assert (tmp_path / "storage/registries/live_canary_approval_packet_registry.jsonl").exists()


def test_step313_latest_runner_blocks_without_operator_request(tmp_path: Path) -> None:
    root = tmp_path
    (root / "config").mkdir(parents=True)
    (root / "config/settings.yaml").write_text(Path("config/settings.yaml").read_text(encoding="utf-8"), encoding="utf-8")

    result = run_live_canary_approval_packet_latest(
        project_root=root,
        signed_testnet_session_close_report=_session_close(),
        live_read_only_probe=_live_probe(),
        live_key_scope_validation=_key_scope(),
    )

    assert result["valid"] is False
    assert BLOCK_MISSING_OPERATOR_REQUEST in result["block_reasons"]
    assert result["live_canary_execution_enabled"] is False
    assert (root / "storage/latest/live_canary_approval_packet.json").exists()


def test_step313_config_flags_remain_disabled() -> None:
    settings = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    cfg = settings["execution"]["live_canary_approval_packet"]
    assert cfg["enabled"] is False
    assert cfg["review_only"] is True
    assert cfg["default_operator_request_enabled"] is False
    assert cfg["live_canary_ready"] is False
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

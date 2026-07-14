from __future__ import annotations

from pathlib import Path

import yaml

from crypto_ai_system.execution.exchange_adapter_contract import DisabledExchangeAdapter
from crypto_ai_system.execution.signed_testnet_preflight_artifact import (
    SIGNED_TESTNET_PREFLIGHT_ARTIFACT_VERSION,
    build_signed_testnet_preflight_artifact,
    validate_signed_testnet_preflight_artifact,
)
from crypto_ai_system.execution.testnet_secret_intake import (
    SECRET_MANAGER_CONTRACT_VERSION,
    MetadataOnlySecretManagerContract,
    build_testnet_key_metadata_intake,
    validate_testnet_key_metadata_intake,
)
from crypto_ai_system.execution.venue_capability_evidence import (
    VENUE_CAPABILITY_EVIDENCE_VERSION,
    build_venue_capability_evidence,
    validate_venue_capability_evidence,
)
from crypto_ai_system.utils.audit import sha256_text, utc_now_canonical


def _valid_approval() -> dict:
    return {
        "approval_packet_id": "approval_packet_step274_test",
        "approval_intake_id": "approval_intake_step274_test",
        "approver_id": "operator_thomas_review_only",
        "approver_role": "operator",
        "approval_ticket_id": "TICKET-STEP274-PREFLIGHT",
        "approval_signature": "signed-testnet-preflight-artifact-review-only-signature",
        "timestamp_utc": utc_now_canonical(),
    }


def _runtime_flags() -> dict:
    return {
        "trading_mode": "paper",
        "testnet_signed_order_enabled": False,
        "enable_real_orders": False,
        "live_trading_enabled": False,
        "allow_live_trading": False,
    }


def _risk_limits() -> dict:
    return {
        "max_order_notional_usdt": 5,
        "max_daily_order_count": 3,
        "manual_kill_switch_required": True,
    }


def _valid_key_metadata() -> dict:
    return {
        "has_api_key": True,
        "has_api_secret": True,
        "key_scope": "testnet",
        "base_url": "https://testnet.binancefuture.com",
        "api_key_fingerprint_sha256": sha256_text("step274-testnet-key-metadata-only"),
        "secret_reference_id": "secret_ref:testnet/binance_futures/step274_metadata_only",
        "secret_file_loaded": False,
        "secret_file_created": False,
        "secret_bytes_read": False,
        "live_key_detected": False,
    }


def test_step274_secret_manager_contract_never_reads_secret_values() -> None:
    contract = MetadataOnlySecretManagerContract()
    payload = contract.to_dict()
    assert payload["contract_version"] == SECRET_MANAGER_CONTRACT_VERSION
    assert payload["metadata_only"] is True
    assert payload["secret_value_access_allowed"] is False
    assert payload["secret_file_creation_allowed"] is False

    result = contract.read_secret("ignored")
    assert result["status"] == "SECRET_VALUE_READ_DISABLED_STEP274"
    assert result["secret_value"] is None
    assert result["secret_value_access_allowed"] is False


def test_step274_testnet_key_metadata_intake_accepts_metadata_only_reference() -> None:
    intake = build_testnet_key_metadata_intake(_valid_key_metadata())
    assert intake["valid"] is True
    assert intake["metadata_only"] is True
    assert intake["secret_value_access_allowed"] is False
    assert intake["secret_file_creation_allowed"] is False
    assert intake["api_key_fingerprint_sha256"] == _valid_key_metadata()["api_key_fingerprint_sha256"]
    assert "api_key" not in intake["public_metadata"]
    assert validate_testnet_key_metadata_intake(intake)["valid"] is True


def test_step274_key_intake_blocks_live_fingerprint_and_actual_secret_values() -> None:
    live_fingerprint = sha256_text("known-live-key")
    metadata = _valid_key_metadata()
    metadata.update(
        {
            "api_key": "actual-testnet-key-value-not-allowed",
            "api_secret": "actual-secret-not-allowed",
            "api_key_fingerprint_sha256": live_fingerprint,
        }
    )
    intake = build_testnet_key_metadata_intake(
        metadata,
        known_live_key_fingerprints_sha256=[live_fingerprint],
    )
    assert intake["valid"] is False
    assert "API_KEY_VALUE_PROVIDED_BLOCKED" in intake["block_reasons"]
    assert "API_SECRET_VALUE_PROVIDED_BLOCKED" in intake["block_reasons"]
    assert "LIVE_KEY_FINGERPRINT_MATCH_BLOCKED" in intake["block_reasons"]


def test_step274_venue_capability_evidence_records_read_contracts_without_submission(tmp_path: Path) -> None:
    adapter = DisabledExchangeAdapter()
    evidence = build_venue_capability_evidence(
        adapter=adapter,
        order_intent={
            "order_intent_id": "order_intent_step274_test",
            "notional_usdt": 5,
            "min_notional_usdt": 1,
        },
        symbol="BTCUSDT",
        evidence_path=tmp_path / "venue_evidence.json",
    )
    assert evidence["version"] == VENUE_CAPABILITY_EVIDENCE_VERSION
    assert evidence["valid"] is True
    assert evidence["external_order_submission_performed"] is False
    assert evidence["order_submission_enabled_by_contract"] is False
    assert evidence["place_order_probe_submitted"] is False
    assert evidence["blocked_submission_probe"]["submitted"] is False
    assert evidence["min_order_size_evidence"]["min_order_size_valid"] is True
    assert Path(evidence["evidence_path"]).exists()
    assert validate_venue_capability_evidence(evidence)["valid"] is True


def test_step274_preflight_artifact_links_key_intake_venue_evidence_and_approval_hash(tmp_path: Path) -> None:
    adapter = DisabledExchangeAdapter()
    intake = build_testnet_key_metadata_intake(_valid_key_metadata())
    evidence = build_venue_capability_evidence(
        adapter=adapter,
        order_intent={"order_intent_id": "order_intent_step274_preflight", "notional_usdt": 5, "min_notional_usdt": 1},
        symbol="BTCUSDT",
    )
    artifact = build_signed_testnet_preflight_artifact(
        adapter_capabilities=adapter.get_capabilities(),
        testnet_key_intake=intake,
        venue_capability_evidence=evidence,
        manual_approval=_valid_approval(),
        risk_limits=_risk_limits(),
        runtime_flags=_runtime_flags(),
        output_path=tmp_path / "step274_preflight_artifact.json",
    )
    assert artifact["version"] == SIGNED_TESTNET_PREFLIGHT_ARTIFACT_VERSION
    assert artifact["contract_review_ready"] is True
    assert artifact["ready_for_signed_testnet_execution"] is False
    assert artifact["testnet_order_submission_allowed"] is False
    assert artifact["external_order_submission_performed"] is False
    assert artifact["testnet_key_intake_id"] == intake["testnet_key_intake_id"]
    assert artifact["venue_capability_evidence_id"] == evidence["venue_capability_evidence_id"]
    assert artifact["approval_sha256"]
    assert Path(artifact["preflight_artifact_path"]).exists()
    assert validate_signed_testnet_preflight_artifact(artifact)["valid"] is True


def test_step274_preflight_artifact_hash_validation_fails_when_tampered() -> None:
    adapter = DisabledExchangeAdapter()
    intake = build_testnet_key_metadata_intake(_valid_key_metadata())
    evidence = build_venue_capability_evidence(
        adapter=adapter,
        order_intent={"order_intent_id": "order_intent_step274_tamper", "notional_usdt": 5, "min_notional_usdt": 1},
    )
    artifact = build_signed_testnet_preflight_artifact(
        adapter_capabilities=adapter.get_capabilities(),
        testnet_key_intake=intake,
        venue_capability_evidence=evidence,
        manual_approval=_valid_approval(),
        risk_limits=_risk_limits(),
        runtime_flags=_runtime_flags(),
    )
    artifact["venue_capability_evidence_hash"] = "0" * 64
    validation = validate_signed_testnet_preflight_artifact(artifact)
    assert validation["valid"] is False
    assert "SIGNED_TESTNET_PREFLIGHT_ARTIFACT_HASH_INVALID" in validation["block_reasons"]


def test_step274_version_and_safety_config_flags() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.286.2"' in pyproject

    settings = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    assert settings["project"]["version"] == "p70_venue_neutral_execution_contract"
    step274 = settings["execution"]["testnet_secret_intake"]
    assert step274["enabled"] is False
    assert step274["metadata_only"] is True
    assert step274["api_key_value_allowed"] is False
    assert step274["secret_file_access_allowed"] is False
    evidence = settings["execution"]["venue_capability_evidence"]
    assert evidence["enabled"] is False
    assert evidence["place_order_probe_must_be_blocked"] is True
    assert settings["safety"]["live_trading_enabled"] is False
    assert settings["safety"]["testnet_signed_order_enabled"] is False

from __future__ import annotations

from pathlib import Path

import yaml

from crypto_ai_system.execution.testnet_secret_metadata_intake_v2 import (
    STEP304_TESTNET_SECRET_METADATA_INTAKE_VERSION,
    TestnetSecretMetadataContractV2,
    build_testnet_secret_metadata_intake_v2,
    persist_testnet_secret_metadata_intake_v2,
    run_testnet_secret_metadata_intake_latest,
    validate_testnet_secret_metadata_intake_v2,
)
from crypto_ai_system.config import load_config
from crypto_ai_system.utils.audit import sha256_text


def _valid_metadata() -> dict:
    return {
        "secret_reference_id": "metadata_ref:testnet/binance_futures/step304_unit",
        "key_fingerprint_sha256": sha256_text("step304-unit-testnet-key-reference"),
        "environment": "testnet",
        "venue": "binance_futures_testnet",
        "scope": ["read_only", "signed_testnet_preparation"],
        "operator_id": "operator_thomas_review_only",
        "base_url": "https://testnet.binancefuture.com",
        "secret_file_loaded": False,
        "secret_file_created": False,
        "secret_bytes_read": False,
        "secret_value_read": False,
        "live_key_detected": False,
    }


def test_step304_contract_never_reads_secret_values() -> None:
    contract = TestnetSecretMetadataContractV2()
    payload = contract.to_dict()
    assert payload["contract_version"] == STEP304_TESTNET_SECRET_METADATA_INTAKE_VERSION
    assert payload["metadata_only"] is True
    assert payload["api_key_value_access_allowed"] is False
    assert payload["api_secret_value_access_allowed"] is False
    assert payload["secret_file_access_allowed"] is False
    assert payload["secret_file_creation_allowed"] is False

    read = contract.read_secret("ignored")
    assert read["status"] == "SECRET_VALUE_READ_DISABLED_STEP304_METADATA_ONLY"
    assert read["secret_value"] is None
    assert read["api_key_value"] is None
    assert read["api_secret_value"] is None
    assert read["testnet_order_submission_allowed"] is False
    assert read["external_order_submission_performed"] is False


def test_step304_accepts_metadata_only_testnet_reference() -> None:
    intake = build_testnet_secret_metadata_intake_v2(_valid_metadata())
    assert intake["version"] == STEP304_TESTNET_SECRET_METADATA_INTAKE_VERSION
    assert intake["valid"] is True
    assert intake["metadata_only"] is True
    assert intake["environment"] == "testnet"
    assert intake["venue"] == "binance_futures_testnet"
    assert intake["key_fingerprint_sha256"] == _valid_metadata()["key_fingerprint_sha256"]
    assert "api_key" not in intake["public_metadata"]
    assert "api_secret" not in intake["public_metadata"]
    assert validate_testnet_secret_metadata_intake_v2(intake)["valid"] is True



def test_step304_blocks_actual_secret_values_live_fingerprint_and_mainnet_metadata() -> None:
    live_fp = sha256_text("known-live-key")
    metadata = _valid_metadata()
    metadata.update(
        {
            "api_key": "actual-key-value-not-allowed",
            "api_secret": "actual-secret-value-not-allowed",
            "key_fingerprint_sha256": live_fp,
            "environment": "mainnet",
            "base_url": "https://fapi.binance.com",
            "scope": ["read_only", "withdrawal"],
            "live_key_detected": True,
        }
    )
    intake = build_testnet_secret_metadata_intake_v2(
        metadata,
        known_live_key_fingerprints_sha256=[live_fp],
    )
    assert intake["valid"] is False
    assert "API_KEY_VALUE_PROVIDED_BLOCKED" in intake["block_reasons"]
    assert "API_SECRET_VALUE_PROVIDED_BLOCKED" in intake["block_reasons"]
    assert "LIVE_KEY_FINGERPRINT_MATCH_BLOCKED" in intake["block_reasons"]
    assert "TESTNET_SECRET_ENVIRONMENT_NOT_TESTNET_BLOCKED" in intake["block_reasons"]
    assert "TESTNET_SECRET_BASE_URL_NOT_TESTNET_BLOCKED" in intake["block_reasons"]
    assert "TESTNET_SECRET_SCOPE_CONTAINS_LIVE_OR_HIGH_RISK_PERMISSION" in intake["block_reasons"]


def test_step304_blocks_secret_file_access_and_non_metadata_reference() -> None:
    metadata = _valid_metadata()
    metadata.update(
        {
            "secret_reference_id": "plain-text-secret-location",
            "secret_file_loaded": True,
            "secret_file_created": True,
            "secret_bytes_read": True,
        }
    )
    intake = build_testnet_secret_metadata_intake_v2(metadata)
    assert intake["valid"] is False
    assert "SECRET_REFERENCE_ID_NOT_METADATA_ONLY_BLOCKED" in intake["block_reasons"]
    assert "SECRET_BYTES_OR_FILE_ACCESS_BLOCKED" in intake["block_reasons"]
    assert "SECRET_FILE_CREATION_BLOCKED" in intake["block_reasons"]


def test_step304_persists_append_only_registry_without_secret_values(tmp_path: Path) -> None:
    root = tmp_path
    (root / "config").mkdir(parents=True)
    (root / "config/settings.yaml").write_text(Path("config/settings.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    cfg = load_config(root)
    intake = build_testnet_secret_metadata_intake_v2(_valid_metadata())
    persisted = persist_testnet_secret_metadata_intake_v2(cfg, intake)
    assert persisted["valid"] is True
    latest = root / "storage/latest/testnet_secret_metadata_intake_v2.json"
    validation = root / "storage/latest/testnet_secret_metadata_validation_v2.json"
    registry_latest = root / "storage/latest/testnet_secret_metadata_registry_record.json"
    registry = root / "storage/registries/testnet_secret_metadata_registry.jsonl"
    assert latest.exists()
    assert validation.exists()
    assert registry_latest.exists()
    assert registry.exists()
    text = latest.read_text(encoding="utf-8")
    assert "actual-key-value" not in text
    assert len(registry.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_step304_latest_runner_creates_metadata_intake_evidence(tmp_path: Path) -> None:
    root = tmp_path
    (root / "config").mkdir(parents=True)
    (root / "config/settings.yaml").write_text(Path("config/settings.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    result = run_testnet_secret_metadata_intake_latest(project_root=root)
    assert result["valid"] is True
    assert result["metadata_only"] is True
    assert result["api_key_value_access_allowed"] is False
    assert result["api_secret_value_access_allowed"] is False
    assert result["testnet_order_submission_allowed"] is False
    assert (root / "storage/latest/testnet_secret_metadata_intake_v2.json").exists()


def test_step304_config_flags_remain_disabled() -> None:
    settings = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    cfg = settings["execution"]["testnet_secret_metadata_intake_v2"]
    assert cfg["enabled"] is False
    assert cfg["review_only"] is True
    assert cfg["metadata_only"] is True
    assert cfg["api_key_value_access_allowed"] is False
    assert cfg["api_secret_value_access_allowed"] is False
    assert cfg["secret_file_access_allowed"] is False
    assert cfg["secret_file_creation_allowed"] is False
    assert cfg["ready_for_signed_testnet_execution"] is False
    assert cfg["testnet_order_submission_allowed"] is False
    assert cfg["external_order_submission_performed"] is False
    assert cfg["place_order_enabled"] is False
    assert cfg["cancel_order_enabled"] is False
    assert cfg["signed_order_executor_enabled"] is False
    assert settings["safety"]["live_trading_enabled"] is False
    assert settings["safety"]["testnet_signed_order_enabled"] is False

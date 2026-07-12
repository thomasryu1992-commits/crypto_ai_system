from __future__ import annotations

from pathlib import Path

import yaml

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.live_key_scope_validator import (
    STEP312_LIVE_KEY_SCOPE_VALIDATOR_VERSION,
    build_live_key_scope_validation,
    persist_live_key_scope_validation,
    run_live_key_scope_validator_latest,
)
from crypto_ai_system.execution.live_read_only_adapter_probe import build_live_read_only_adapter_probe
from crypto_ai_system.utils.audit import sha256_text


def _live_probe() -> dict:
    return build_live_read_only_adapter_probe(
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


def _metadata() -> dict:
    return {
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
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "live_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "signed_order_executor_enabled": False,
        "live_trading_enabled": False,
    }


def test_step312_validates_live_key_scope_metadata_only_without_unlocking_live_canary() -> None:
    result = build_live_key_scope_validation(_metadata(), live_read_only_probe=_live_probe())

    assert result["version"] == STEP312_LIVE_KEY_SCOPE_VALIDATOR_VERSION
    assert result["status"] == "LIVE_KEY_SCOPE_VALIDATED_METADATA_ONLY"
    assert result["valid"] is True
    assert result["metadata_only"] is True
    assert result["live_read_only_probe_valid_and_fresh"] is True
    assert result["live_canary_ready"] is False
    assert result["live_order_submission_allowed"] is False
    assert result["place_order_enabled"] is False
    assert result["cancel_order_enabled"] is False
    assert result["withdrawal_enabled"] is False
    assert result["transfer_enabled"] is False
    assert result["trade_enabled"] is False
    assert result["api_key_value_access_allowed"] is False
    assert result["api_secret_value_access_allowed"] is False


def test_step312_blocks_trade_withdrawal_or_admin_scope() -> None:
    metadata = _metadata()
    metadata["scope"] = ["read_only", "trade", "withdrawal", "admin"]
    metadata["trade_enabled"] = True
    result = build_live_key_scope_validation(metadata, live_read_only_probe=_live_probe())

    assert result["valid"] is False
    assert "STEP312_BLOCK_FORBIDDEN_SCOPE_TRADE" in result["block_reasons"]
    assert "STEP312_BLOCK_FORBIDDEN_SCOPE_WITHDRAW" in result["block_reasons"] or "STEP312_BLOCK_FORBIDDEN_SCOPE_WITHDRAWAL" in result["block_reasons"]
    assert "STEP312_BLOCK_FORBIDDEN_SCOPE_ADMIN" in result["block_reasons"]
    assert "STEP312_BLOCK_TRADE_ENABLED_NOT_DISABLED" in result["block_reasons"]
    assert result["live_order_submission_allowed"] is False


def test_step312_blocks_actual_secret_value_or_secret_file_access() -> None:
    metadata = _metadata()
    metadata["api_key"] = "actual-live-key-value"
    metadata["secret_file_loaded"] = True
    metadata["secret_file_created"] = True
    result = build_live_key_scope_validation(metadata, live_read_only_probe=_live_probe())

    assert result["valid"] is False
    assert "STEP312_BLOCK_API_KEY_VALUE_PROVIDED" in result["block_reasons"]
    assert "STEP312_BLOCK_SECRET_BYTES_OR_FILE_ACCESS" in result["block_reasons"]
    assert "STEP312_BLOCK_SECRET_FILE_CREATION" in result["block_reasons"]
    assert result["api_key_value_access_allowed"] is False
    assert result["secret_file_access_allowed"] is False


def test_step312_requires_fresh_live_read_only_probe() -> None:
    result = build_live_key_scope_validation(_metadata(), live_read_only_probe=None)

    assert result["valid"] is False
    assert "STEP312_BLOCK_MISSING_LIVE_READ_ONLY_PROBE" in result["block_reasons"]
    assert result["live_read_only_probe_valid_and_fresh"] is False


def test_step312_blocks_testnet_or_non_live_metadata() -> None:
    metadata = _metadata()
    metadata["environment"] = "testnet"
    metadata["venue"] = "binance_futures_testnet"
    metadata["base_url"] = "https://testnet.binancefuture.com"
    result = build_live_key_scope_validation(metadata, live_read_only_probe=_live_probe())

    assert result["valid"] is False
    assert "STEP312_BLOCK_ENVIRONMENT_NOT_LIVE" in result["block_reasons"]
    assert "STEP312_BLOCK_VENUE_NOT_APPROVED_FOR_LIVE_SCOPE_VALIDATION" in result["block_reasons"]
    assert "STEP312_BLOCK_BASE_URL_NOT_LIVE" in result["block_reasons"]


def test_step312_persists_registry_and_latest(tmp_path: Path) -> None:
    cfg = load_config(Path.cwd())
    object.__setattr__(cfg, "root", tmp_path)
    validation = build_live_key_scope_validation(_metadata(), live_read_only_probe=_live_probe())
    persisted = persist_live_key_scope_validation(cfg, validation)

    assert persisted["live_key_scope_validator_registry_record_id"]
    assert (tmp_path / "storage/latest/live_key_scope_validation.json").exists()
    assert (tmp_path / "storage/latest/live_key_scope_validator_registry_record.json").exists()
    registry = tmp_path / "storage/registries/live_key_scope_validator_registry.jsonl"
    assert registry.exists()
    assert len(registry.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_step312_latest_runner_links_to_step311_probe(tmp_path: Path) -> None:
    root = tmp_path
    (root / "config").mkdir(parents=True)
    (root / "config/settings.yaml").write_text(Path("config/settings.yaml").read_text(encoding="utf-8"), encoding="utf-8")

    result = run_live_key_scope_validator_latest(project_root=root, live_read_only_probe=_live_probe())

    assert result["status"] == "LIVE_KEY_SCOPE_VALIDATED_METADATA_ONLY"
    assert result["valid"] is True
    assert result["live_read_only_probe_valid_and_fresh"] is True
    assert result["live_canary_ready"] is False
    assert (root / "storage/latest/live_key_scope_validation.json").exists()
    assert (root / "storage/registries/live_key_scope_validator_registry.jsonl").exists()


def test_step312_config_flags_remain_disabled() -> None:
    settings = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    cfg = settings["execution"]["live_key_scope_validator"]
    assert cfg["enabled"] is False
    assert cfg["review_only"] is True
    assert cfg["metadata_only"] is True
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

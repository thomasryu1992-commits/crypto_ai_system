from __future__ import annotations

from pathlib import Path

import yaml

from crypto_ai_system.execution.live_read_only_adapter_probe import (
    STEP311_LIVE_READ_ONLY_ADAPTER_PROBE_VERSION,
    build_live_read_only_adapter_probe,
    persist_live_read_only_adapter_probe,
    run_live_read_only_adapter_probe_latest,
)
from crypto_ai_system.config import load_config


def _metadata() -> dict:
    return {
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
        "secret_value_read": False,
        "secret_bytes_read": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "withdrawal_enabled": False,
        "transfer_enabled": False,
        "leverage_mutation_enabled": False,
        "margin_mode_mutation_enabled": False,
        "live_trading_enabled": False,
    }


def test_step311_builds_valid_live_read_only_probe_without_unlocking_live_execution() -> None:
    probe = build_live_read_only_adapter_probe(live_metadata=_metadata())

    assert probe["version"] == STEP311_LIVE_READ_ONLY_ADAPTER_PROBE_VERSION
    assert probe["status"] == "LIVE_READ_ONLY_ADAPTER_PROBE_VALID"
    assert probe["valid"] is True
    assert probe["review_ready"] is True
    assert probe["live_canary_ready"] is False
    assert probe["live_key_scope_validation_required"] is True
    assert probe["live_key_scope_validated"] is False
    assert probe["environment"] == "live"
    assert probe["all_live_read_probes_valid_and_fresh"] is True
    assert probe["place_order_enabled"] is False
    assert probe["cancel_order_enabled"] is False
    assert probe["withdrawal_enabled"] is False
    assert probe["transfer_enabled"] is False
    assert probe["leverage_mutation_enabled"] is False
    assert probe["margin_mode_mutation_enabled"] is False
    assert probe["live_trading_enabled"] is False
    assert probe["api_key_value_access_allowed"] is False
    assert probe["api_secret_value_access_allowed"] is False
    assert set(probe["read_probe_results"]) == {
        "balance_read_probe",
        "positions_read_probe",
        "open_orders_read_probe",
        "orderbook_read_probe",
        "fee_estimate_probe",
        "min_order_size_probe",
    }


def test_step311_blocks_testnet_environment_for_live_probe() -> None:
    metadata = _metadata()
    metadata["environment"] = "testnet"
    metadata["base_url"] = "https://testnet.binancefuture.com"
    probe = build_live_read_only_adapter_probe(live_metadata=metadata)
    assert probe["valid"] is False
    assert "STEP311_BLOCK_ENVIRONMENT_NOT_LIVE" in probe["block_reasons"]
    assert "STEP311_BLOCK_BASE_URL_NOT_LIVE_READ_ONLY" in probe["block_reasons"]


def test_step311_blocks_write_or_withdrawal_scope() -> None:
    metadata = _metadata()
    metadata["scope"] = ["read_only", "trade", "withdrawal"]
    probe = build_live_read_only_adapter_probe(live_metadata=metadata)
    assert probe["valid"] is False
    assert "STEP311_BLOCK_FORBIDDEN_SCOPE_TRADE" in probe["block_reasons"]
    assert "STEP311_BLOCK_FORBIDDEN_SCOPE_WITHDRAWAL" in probe["block_reasons"]


def test_step311_blocks_secret_value_access_and_mutation_flags() -> None:
    metadata = _metadata()
    metadata["api_key_value_access_allowed"] = True
    metadata["place_order_enabled"] = True
    metadata["leverage_mutation_enabled"] = True
    probe = build_live_read_only_adapter_probe(live_metadata=metadata)
    assert probe["valid"] is False
    assert "STEP311_BLOCK_API_KEY_VALUE_ACCESS_ALLOWED" in probe["block_reasons"]
    assert "STEP311_BLOCK_PLACE_ORDER_ENABLED" in probe["block_reasons"]
    assert "STEP311_BLOCK_LEVERAGE_MUTATION_ENABLED" in probe["block_reasons"]


def test_step311_persists_registry_and_latest(tmp_path: Path) -> None:
    cfg = load_config(Path.cwd())
    object.__setattr__(cfg, "root", tmp_path)
    probe = build_live_read_only_adapter_probe(live_metadata=_metadata())
    persisted = persist_live_read_only_adapter_probe(cfg, probe)
    assert persisted["live_read_only_adapter_probe_registry_record_id"]
    assert (tmp_path / "storage/latest/live_read_only_adapter_probe.json").exists()
    assert (tmp_path / "storage/latest/live_read_only_adapter_probe_registry_record.json").exists()
    registry = tmp_path / "storage/registries/live_read_only_adapter_probe_registry.jsonl"
    assert registry.exists()
    assert len(registry.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_step311_latest_runner_creates_live_read_only_probe_evidence(tmp_path: Path) -> None:
    root = tmp_path
    (root / "config").mkdir(parents=True)
    (root / "config/settings.yaml").write_text(Path("config/settings.yaml").read_text(encoding="utf-8"), encoding="utf-8")

    result = run_live_read_only_adapter_probe_latest(project_root=root)

    assert result["status"] == "LIVE_READ_ONLY_ADAPTER_PROBE_VALID"
    assert result["valid"] is True
    assert result["live_canary_ready"] is False
    assert result["live_trading_enabled"] is False
    assert (root / "storage/latest/live_read_only_adapter_probe.json").exists()
    assert (root / "storage/registries/live_read_only_adapter_probe_registry.jsonl").exists()


def test_step311_config_flags_remain_disabled() -> None:
    settings = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    cfg = settings["execution"]["live_read_only_adapter_probe"]
    assert cfg["enabled"] is False
    assert cfg["review_only"] is True
    assert cfg["read_only"] is True
    assert cfg["network_enabled"] is False
    assert cfg["live_key_scope_validated"] is False
    assert cfg["live_canary_ready"] is False
    assert cfg["live_order_submission_allowed"] is False
    assert cfg["external_order_submission_performed"] is False
    assert cfg["place_order_enabled"] is False
    assert cfg["cancel_order_enabled"] is False
    assert cfg["withdrawal_enabled"] is False
    assert cfg["transfer_enabled"] is False
    assert cfg["leverage_mutation_enabled"] is False
    assert cfg["margin_mode_mutation_enabled"] is False
    assert cfg["api_key_value_access_allowed"] is False
    assert cfg["api_secret_value_access_allowed"] is False
    assert cfg["secret_file_access_allowed"] is False
    assert cfg["secret_file_creation_allowed"] is False
    assert settings["safety"]["live_trading_enabled"] is False

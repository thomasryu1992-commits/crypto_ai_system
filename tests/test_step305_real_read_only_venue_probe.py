from __future__ import annotations

from pathlib import Path

import yaml

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.real_read_only_venue_probe import (
    STEP305_REAL_READ_ONLY_VENUE_PROBE_VERSION,
    build_real_read_only_venue_probe,
    persist_real_read_only_venue_probe,
    run_real_read_only_venue_probe_latest,
)
from crypto_ai_system.execution.real_testnet_read_only_adapter import (
    BinanceFuturesTestnetReadOnlyAdapter,
    build_real_testnet_read_only_adapter_evidence,
    persist_real_testnet_read_only_adapter_evidence,
)
from crypto_ai_system.execution.testnet_secret_metadata_intake_v2 import (
    build_testnet_secret_metadata_intake_v2,
    persist_testnet_secret_metadata_intake_v2,
)
from crypto_ai_system.utils.audit import sha256_text


def _order_intent() -> dict:
    return {
        "order_intent_id": "order_intent_step305_unit",
        "symbol": "BTCUSDT",
        "notional_usdt": 5,
        "min_notional_usdt": 1,
        "fee_bps": 2.5,
        "slippage_bps": 3.0,
    }


def _valid_secret_metadata() -> dict:
    return {
        "secret_reference_id": "metadata_ref:testnet/binance_futures/step305_unit",
        "key_fingerprint_sha256": sha256_text("step305-unit-testnet-key-reference"),
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


def _valid_adapter_evidence() -> dict:
    return build_real_testnet_read_only_adapter_evidence(
        adapter=BinanceFuturesTestnetReadOnlyAdapter(),
        order_intent=_order_intent(),
        symbol="BTCUSDT",
    )


def _valid_secret_intake() -> dict:
    return build_testnet_secret_metadata_intake_v2(_valid_secret_metadata())


def test_step305_builds_valid_probe_from_adapter_and_metadata_only_secret() -> None:
    probe = build_real_read_only_venue_probe(
        adapter_evidence=_valid_adapter_evidence(),
        secret_metadata_intake=_valid_secret_intake(),
    )

    assert probe["version"] == STEP305_REAL_READ_ONLY_VENUE_PROBE_VERSION
    assert probe["status"] == "REAL_READ_ONLY_VENUE_PROBE_VALID"
    assert probe["valid"] is True
    assert probe["review_ready"] is True
    assert probe["venue"] == "binance_futures_testnet"
    assert probe["environment"] == "testnet"
    assert probe["metadata_only"] is True
    assert probe["all_read_probes_valid_and_fresh"] is True
    assert probe["place_cancel_disabled_evidence_valid"] is True
    assert probe["ready_for_signed_testnet_execution"] is False
    assert probe["testnet_order_submission_allowed"] is False
    assert probe["external_order_submission_performed"] is False
    assert probe["place_order_enabled"] is False
    assert probe["cancel_order_enabled"] is False
    assert probe["signed_order_executor_enabled"] is False
    assert probe["api_key_value_access_allowed"] is False
    assert set(probe["read_probe_results"]) == {
        "balance_read_probe",
        "positions_read_probe",
        "open_orders_read_probe",
        "orderbook_read_probe",
        "fee_estimate_probe",
        "slippage_estimate_probe",
        "min_order_size_probe",
        "fetch_order_probe",
    }


def test_step305_blocks_missing_secret_metadata_intake() -> None:
    probe = build_real_read_only_venue_probe(
        adapter_evidence=_valid_adapter_evidence(),
        secret_metadata_intake=None,
    )
    assert probe["valid"] is False
    assert "STEP305_SECRET_METADATA_INTAKE_MISSING" in probe["block_reasons"]
    assert "STEP305_SECRET_METADATA_VALIDATION_INVALID" in probe["block_reasons"]


def test_step305_blocks_venue_mismatch() -> None:
    secret = _valid_secret_intake()
    secret["venue"] = "extended_testnet"
    # Re-hash is intentionally not repaired; validator should also reject hash mismatch.
    probe = build_real_read_only_venue_probe(
        adapter_evidence=_valid_adapter_evidence(),
        secret_metadata_intake=secret,
    )
    assert probe["valid"] is False
    assert "STEP305_VENUE_MISMATCH" in probe["block_reasons"]


def test_step305_blocks_stale_adapter_probe() -> None:
    evidence = _valid_adapter_evidence()
    evidence["created_at_utc"] = "2020-01-01T00:00:00Z"
    probe = build_real_read_only_venue_probe(
        adapter_evidence=evidence,
        secret_metadata_intake=_valid_secret_intake(),
        max_probe_age_sec=1,
    )
    assert probe["valid"] is False
    assert "STEP305_ADAPTER_EVIDENCE_STALE_BLOCKED" in probe["block_reasons"]


def test_step305_persists_probe_registry_and_latest(tmp_path: Path) -> None:
    cfg = load_config(Path.cwd())
    object.__setattr__(cfg, "root", tmp_path)
    probe = build_real_read_only_venue_probe(
        adapter_evidence=_valid_adapter_evidence(),
        secret_metadata_intake=_valid_secret_intake(),
    )
    persisted = persist_real_read_only_venue_probe(cfg, probe)
    assert persisted["real_read_only_venue_probe_registry_record_id"]
    assert (tmp_path / "storage/latest/real_read_only_venue_probe.json").exists()
    assert (tmp_path / "storage/latest/real_read_only_venue_probe_registry_record.json").exists()
    registry = tmp_path / "storage/registries/real_read_only_venue_probe_registry.jsonl"
    assert registry.exists()
    assert len(registry.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_step305_latest_runner_creates_adapter_secret_and_probe_evidence(tmp_path: Path) -> None:
    root = tmp_path
    (root / "config").mkdir(parents=True)
    (root / "config/settings.yaml").write_text(Path("config/settings.yaml").read_text(encoding="utf-8"), encoding="utf-8")

    result = run_real_read_only_venue_probe_latest(project_root=root)

    assert result["status"] == "REAL_READ_ONLY_VENUE_PROBE_VALID"
    assert result["valid"] is True
    assert result["testnet_order_submission_allowed"] is False
    assert result["external_order_submission_performed"] is False
    assert (root / "storage/latest/real_testnet_read_only_adapter_evidence.json").exists()
    assert (root / "storage/latest/testnet_secret_metadata_intake_v2.json").exists()
    assert (root / "storage/latest/real_read_only_venue_probe.json").exists()


def test_step305_config_flags_remain_disabled() -> None:
    settings = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    cfg = settings["execution"]["real_read_only_venue_probe"]
    assert cfg["enabled"] is False
    assert cfg["review_only"] is True
    assert cfg["require_adapter_evidence"] is True
    assert cfg["require_secret_metadata_validation"] is True
    assert cfg["require_probe_freshness"] is True
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

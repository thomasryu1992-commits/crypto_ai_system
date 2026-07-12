from __future__ import annotations

from pathlib import Path

import yaml

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.real_read_only_venue_probe import build_real_read_only_venue_probe
from crypto_ai_system.execution.real_testnet_read_only_adapter import BinanceFuturesTestnetReadOnlyAdapter, build_real_testnet_read_only_adapter_evidence
from crypto_ai_system.execution.signed_testnet_pre_submit_validator import (
    BLOCK_MISSING_ORDER_INTENT,
    BLOCK_MISSING_RISK_GATE,
    BLOCK_ORDER_INTENT_STAGE_NOT_SIGNED_TESTNET,
    BLOCK_RISK_GATE_NOT_SIGNED_TESTNET,
    BLOCK_UNSAFE_SUBMISSION_FLAG,
    BLOCK_VENUE_PROBE_INVALID,
    PRE_SUBMIT_BLOCKED,
    PRE_SUBMIT_VALIDATED_REVIEW_ONLY,
    STEP306_SIGNED_TESTNET_PRE_SUBMIT_VALIDATOR_VERSION,
    build_signed_testnet_pre_submit_validation_report,
    persist_signed_testnet_pre_submit_validation_report,
    run_signed_testnet_pre_submit_validator_latest,
)
from crypto_ai_system.execution.testnet_secret_metadata_intake_v2 import build_testnet_secret_metadata_intake_v2
from crypto_ai_system.utils.audit import sha256_text


def _order_intent() -> dict:
    return {
        "status": "ORDER_INTENT_CREATED",
        "state": "CREATED",
        "order_intent_created": True,
        "order_intent_id": "order_intent_step306_unit",
        "decision_id": "decision_step306_unit",
        "risk_gate_id": "risk_gate_step306_unit",
        "research_signal_id": "research_signal_step306_unit",
        "profile_id": "profile_step306_unit",
        "execution_stage": "signed_testnet",
        "decision_stage": "signed_testnet",
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": 0.001,
        "entry_price": 100000.0,
        "notional_usdt": 100.0,
        "pre_order_risk_gate_approved": True,
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
    }


def _risk_gate() -> dict:
    return {
        "risk_gate_id": "risk_gate_step306_unit",
        "decision_id": "decision_step306_unit",
        "research_signal_id": "research_signal_step306_unit",
        "profile_id": "profile_step306_unit",
        "status": "PASS_SIGNED_TESTNET",
        "stage": "signed_testnet",
        "approved": True,
        "block_reasons": [],
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
    }


def _secret_metadata() -> dict:
    return {
        "secret_reference_id": "metadata_ref:testnet/binance_futures/step306_unit",
        "key_fingerprint_sha256": sha256_text("step306-unit-testnet-key-reference"),
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


def _venue_probe() -> dict:
    adapter_evidence = build_real_testnet_read_only_adapter_evidence(
        adapter=BinanceFuturesTestnetReadOnlyAdapter(),
        order_intent={"order_intent_id": "step306_probe", "symbol": "BTCUSDT", "notional_usdt": 5, "min_notional_usdt": 1},
        symbol="BTCUSDT",
    )
    secret_intake = build_testnet_secret_metadata_intake_v2(_secret_metadata())
    return build_real_read_only_venue_probe(adapter_evidence=adapter_evidence, secret_metadata_intake=secret_intake)


def test_step306_builds_review_only_would_submit_payload_without_submission() -> None:
    report = build_signed_testnet_pre_submit_validation_report(
        order_intent=_order_intent(),
        risk_gate_report=_risk_gate(),
        venue_probe=_venue_probe(),
    )

    assert report["version"] == STEP306_SIGNED_TESTNET_PRE_SUBMIT_VALIDATOR_VERSION
    assert report["status"] == PRE_SUBMIT_VALIDATED_REVIEW_ONLY
    assert report["valid"] is True
    assert report["review_only"] is True
    assert report["ready_for_execution_enablement_packet"] is True
    assert report["would_submit_order_payload_created"] is True
    assert report["idempotency_key"]
    payload = report["would_submit_order_payload"]
    assert payload["would_submit_only"] is True
    assert payload["actual_submission_performed"] is False
    assert payload["external_order_submission_performed"] is False
    assert payload["place_order_enabled"] is False
    assert payload["signed_order_executor_enabled"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["external_order_submission_performed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
    assert report["api_key_value_access_allowed"] is False
    assert report["secret_file_access_allowed"] is False


def test_step306_blocks_missing_order_intent_and_risk_gate() -> None:
    report = build_signed_testnet_pre_submit_validation_report(
        order_intent=None,
        risk_gate_report=None,
        venue_probe=_venue_probe(),
    )
    assert report["status"] == PRE_SUBMIT_BLOCKED
    assert BLOCK_MISSING_ORDER_INTENT in report["block_reasons"]
    assert BLOCK_MISSING_RISK_GATE in report["block_reasons"]
    assert report["would_submit_order_payload_created"] is False


def test_step306_blocks_non_signed_testnet_stage_and_non_signed_risk_gate() -> None:
    intent = _order_intent()
    intent["execution_stage"] = "paper"
    risk = _risk_gate()
    risk["status"] = "PASS_PAPER"
    report = build_signed_testnet_pre_submit_validation_report(
        order_intent=intent,
        risk_gate_report=risk,
        venue_probe=_venue_probe(),
    )
    assert report["status"] == PRE_SUBMIT_BLOCKED
    assert BLOCK_ORDER_INTENT_STAGE_NOT_SIGNED_TESTNET in report["block_reasons"]
    assert BLOCK_RISK_GATE_NOT_SIGNED_TESTNET in report["block_reasons"]


def test_step306_blocks_invalid_venue_probe_and_unsafe_flags() -> None:
    probe = _venue_probe()
    probe["valid"] = False
    intent = _order_intent()
    intent["testnet_order_submission_allowed"] = True
    report = build_signed_testnet_pre_submit_validation_report(
        order_intent=intent,
        risk_gate_report=_risk_gate(),
        venue_probe=probe,
    )
    assert report["status"] == PRE_SUBMIT_BLOCKED
    assert BLOCK_VENUE_PROBE_INVALID in report["block_reasons"]
    assert BLOCK_UNSAFE_SUBMISSION_FLAG in report["block_reasons"]


def test_step306_persists_report_payload_registry_and_latest(tmp_path: Path) -> None:
    cfg = load_config(Path.cwd())
    object.__setattr__(cfg, "root", tmp_path)
    report = build_signed_testnet_pre_submit_validation_report(
        order_intent=_order_intent(),
        risk_gate_report=_risk_gate(),
        venue_probe=_venue_probe(),
    )
    persisted = persist_signed_testnet_pre_submit_validation_report(cfg, report)
    assert persisted["signed_testnet_pre_submit_registry_record_id"]
    assert (tmp_path / "storage/latest/signed_testnet_pre_submit_validation_report.json").exists()
    assert (tmp_path / "storage/latest/would_submit_order_payload.json").exists()
    assert (tmp_path / "storage/latest/signed_testnet_pre_submit_registry_record.json").exists()
    assert (tmp_path / "storage/signed_testnet_pre_submit/pre_submit_validation_report.json").exists()
    assert (tmp_path / "storage/registries/signed_testnet_pre_submit_validator_registry.jsonl").exists()


def test_step306_latest_runner_creates_blocked_review_only_evidence(tmp_path: Path) -> None:
    root = tmp_path
    (root / "config").mkdir(parents=True)
    (root / "config/settings.yaml").write_text(Path("config/settings.yaml").read_text(encoding="utf-8"), encoding="utf-8")

    result = run_signed_testnet_pre_submit_validator_latest(project_root=root)

    assert result["status"] == PRE_SUBMIT_BLOCKED
    assert result["review_only"] is True
    assert result["testnet_order_submission_allowed"] is False
    assert result["external_order_submission_performed"] is False
    assert result["place_order_enabled"] is False
    assert result["cancel_order_enabled"] is False
    assert result["signed_order_executor_enabled"] is False
    assert (root / "storage/latest/signed_testnet_pre_submit_validation_report.json").exists()
    assert (root / "storage/latest/real_read_only_venue_probe.json").exists()


def test_step306_config_flags_remain_disabled() -> None:
    settings = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    cfg = settings["execution"]["signed_testnet_pre_submit_validator"]
    assert cfg["enabled"] is False
    assert cfg["review_only"] is True
    assert cfg["create_would_submit_payload"] is True
    assert cfg["require_order_intent"] is True
    assert cfg["require_risk_gate_pass_signed_testnet"] is True
    assert cfg["require_real_read_only_venue_probe_valid"] is True
    assert cfg["require_probe_freshness"] is True
    assert cfg["ready_for_signed_testnet_execution"] is False
    assert cfg["testnet_order_submission_allowed"] is False
    assert cfg["external_order_submission_allowed"] is False
    assert cfg["external_order_submission_performed"] is False
    assert cfg["place_order_enabled"] is False
    assert cfg["cancel_order_enabled"] is False
    assert cfg["signed_order_executor_enabled"] is False
    assert cfg["api_key_value_access_allowed"] is False
    assert cfg["api_secret_value_access_allowed"] is False
    assert cfg["secret_file_access_allowed"] is False
    assert cfg["secret_file_creation_allowed"] is False
    assert settings["safety"]["live_trading_enabled"] is False
    assert settings["safety"]["testnet_signed_order_enabled"] is False

from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.live_scaled_approval_intake_validation import (
    LIVE_SCALED_APPROVAL_PHRASE,
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALID_REVIEW_ONLY_NO_EXECUTION,
    STATUS_WAITING_REVIEW_ONLY,
    LiveScaledApprovalIntake,
    LiveScaledApprovalPacket,
    build_live_scaled_approval_intake_validation_report,
    build_p14_negative_fixture_results,
    build_review_only_live_scaled_approval_packet,
    build_valid_live_scaled_approval_intake,
    persist_live_scaled_approval_intake_validation,
)


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  name: tmp-crypto-ai-system\n  version: test\n"
        "storage:\n  latest_dir: storage/latest\n  registry_dir: storage/registries\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text("[project]\nname='tmp-crypto-ai-system'\nversion='0.286.0'\n", encoding="utf-8")


def _p13_waiting() -> dict:
    return {
        "status": "P13_LIVE_SCALED_READINESS_REVIEW_WAITING_REVIEW_ONLY",
        "p13_live_scaled_readiness_review_sha256": "d" * 64,
        "ready_for_separate_live_scaled_approval_review_only": False,
        "live_scaled_approval_packet_may_be_drafted": False,
        "separate_live_scaled_approval_required": True,
        "separate_live_scaled_approval_present": False,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
    }


def _p13_ready() -> dict:
    return {
        "status": "P13_LIVE_SCALED_READINESS_REVIEW_READY_FOR_SEPARATE_APPROVAL_REVIEW_ONLY",
        "p13_live_scaled_readiness_review_sha256": "d" * 64,
        "ready_for_separate_live_scaled_approval_review_only": True,
        "live_scaled_approval_packet_may_be_drafted": True,
        "separate_live_scaled_approval_required": True,
        "separate_live_scaled_approval_present": False,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_readiness_allowed": False,
        "live_scaled_promotion_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "api_key_value_logged": False,
        "api_secret_value_logged": False,
        "withdrawal_permission_allowed": False,
        "transfer_permission_allowed": False,
        "admin_permission_allowed": False,
    }


def _valid_chain() -> tuple[dict, dict, dict]:
    p13 = _p13_ready()
    packet = build_review_only_live_scaled_approval_packet(p13)
    intake = build_valid_live_scaled_approval_intake(packet)
    return p13, packet, intake


def test_p14_waits_review_only_without_p13_readiness(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)
    atomic_write_json(tmp_path / "storage" / "latest" / "p13_live_scaled_readiness_review_report.json", _p13_waiting())

    report = build_live_scaled_approval_intake_validation_report(cfg=cfg)

    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["waiting"] is True
    assert report["blocked"] is False
    assert "P14_SOURCE_P13_NOT_READY_FOR_SEPARATE_APPROVAL" in report["waiting_reasons"]
    assert report["live_scaled_approval_valid_review_only"] is False
    assert report["limited_live_scaled_auto_trading_allowed"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["secret_value_accessed"] is False
    assert report["unsafe_truthy_execution_flags"] == []


def test_p14_validates_approval_packet_and_intake_review_only_no_execution() -> None:
    p13, packet, intake = _valid_chain()

    report = build_live_scaled_approval_intake_validation_report(
        p13_report=p13,
        approval_packet=packet,
        approval_intake=intake,
    )

    assert report["status"] == STATUS_VALID_REVIEW_ONLY_NO_EXECUTION
    assert report["blocked"] is False
    assert report["waiting"] is False
    assert report["live_scaled_approval_valid_review_only"] is True
    assert report["live_scaled_approval_packet_valid"] is True
    assert report["live_scaled_approval_intake_valid"] is True
    assert report["separate_runtime_enablement_step_required"] is True
    assert report["limited_live_scaled_auto_trading_allowed"] is False
    assert report["live_scaled_runtime_enablement_allowed"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["secret_value_accessed"] is False
    assert intake["approval_phrase"] == LIVE_SCALED_APPROVAL_PHRASE


def test_p14_packet_validation_blocks_hash_caps_symbol_and_unsafe_flags() -> None:
    p13, packet, intake = _valid_chain()
    bad_packet = {
        **packet,
        "source_p13_live_scaled_readiness_review_sha256": "x" * 64,
        "symbol_scope": ["BTCUSDT", "ETHUSDT"],
        "fixed_max_notional_usdt": 1_000,
        "daily_loss_cap_usdt": 100,
        "max_daily_order_count": 99,
        "max_leverage": 10,
        "auto_apply_allowed": True,
        "live_scaled_execution_enabled": True,
        "withdrawal_permission_allowed": True,
    }

    report = build_live_scaled_approval_intake_validation_report(
        p13_report=p13,
        approval_packet=bad_packet,
        approval_intake=intake,
    )

    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P14_PACKET_P13_HASH_MISMATCH" in report["block_reasons"]
    assert "P14_PACKET_SYMBOL_SCOPE_NOT_BTCUSDT_ONLY" in report["block_reasons"]
    assert "P14_PACKET_FIXED_MAX_NOTIONAL_OUT_OF_RANGE" in report["block_reasons"]
    assert "P14_PACKET_DAILY_LOSS_CAP_OUT_OF_RANGE" in report["block_reasons"]
    assert "P14_PACKET_MAX_DAILY_ORDER_COUNT_OUT_OF_RANGE" in report["block_reasons"]
    assert "P14_PACKET_MAX_LEVERAGE_OUT_OF_RANGE" in report["block_reasons"]
    assert "P14_PACKET_UNSAFE_FLAG_TRUE:auto_apply_allowed" in report["block_reasons"]
    assert "P14_PACKET_UNSAFE_FLAG_TRUE:live_scaled_execution_enabled" in report["block_reasons"]
    assert "P14_PACKET_UNSAFE_FLAG_TRUE:withdrawal_permission_allowed" in report["block_reasons"]
    assert report["live_scaled_execution_enabled"] is False


def test_p14_intake_validation_blocks_missing_identity_acknowledgement_secret_and_enablement_request() -> None:
    p13, packet, intake = _valid_chain()
    bad_intake = {
        **intake,
        "operator_id": "",
        "ticket_or_signature": "",
        "approval_phrase": "APPROVED",
        "auto_generated_approval_file": True,
        "acknowledged_kill_switches": False,
        "acknowledged_fixed_max_notional_cap": False,
        "requests_live_scaled_execution_enabled": True,
        "requests_live_order_submission_allowed": True,
        "requests_runtime_settings_mutation": True,
        "secret_value_logged": True,
        "withdrawal_permission_requested": True,
    }

    report = build_live_scaled_approval_intake_validation_report(
        p13_report=p13,
        approval_packet=packet,
        approval_intake=bad_intake,
    )

    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P14_INTAKE_OPERATOR_ID_MISSING" in report["block_reasons"]
    assert "P14_INTAKE_TICKET_OR_SIGNATURE_MISSING" in report["block_reasons"]
    assert "P14_INTAKE_EXACT_APPROVAL_PHRASE_MISSING" in report["block_reasons"]
    assert "P14_INTAKE_AUTO_GENERATED_APPROVAL_FILE_BLOCKED" in report["block_reasons"]
    assert "P14_INTAKE_REQUIRED_ACK_MISSING:acknowledged_kill_switches" in report["block_reasons"]
    assert "P14_INTAKE_REQUIRED_ACK_MISSING:acknowledged_fixed_max_notional_cap" in report["block_reasons"]
    assert "P14_INTAKE_UNSAFE_REQUEST_TRUE:requests_live_scaled_execution_enabled" in report["block_reasons"]
    assert "P14_INTAKE_UNSAFE_REQUEST_TRUE:requests_live_order_submission_allowed" in report["block_reasons"]
    assert "P14_INTAKE_UNSAFE_REQUEST_TRUE:requests_runtime_settings_mutation" in report["block_reasons"]
    assert "P14_INTAKE_UNSAFE_REQUEST_TRUE:secret_value_logged" in report["block_reasons"]
    assert "P14_INTAKE_UNSAFE_REQUEST_TRUE:withdrawal_permission_requested" in report["block_reasons"]
    assert report["limited_live_scaled_auto_trading_allowed"] is False
    assert report["secret_value_accessed"] is False


def test_p14_source_blocks_existing_unsafe_runtime_flags() -> None:
    p13, packet, intake = _valid_chain()
    p13 = {**p13, "live_scaled_execution_enabled": True, "secret_value_logged": True, "runtime_settings_mutated": True}

    report = build_live_scaled_approval_intake_validation_report(
        p13_report=p13,
        approval_packet=packet,
        approval_intake=intake,
    )

    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P14_SOURCE_P13_LIVE_SCALED_ALREADY_ENABLED" in report["block_reasons"]
    assert "P14_SOURCE_P13_UNSAFE_FLAG_TRUE:live_scaled_execution_enabled" in report["block_reasons"]
    assert "P14_SOURCE_P13_UNSAFE_FLAG_TRUE:secret_value_logged" in report["block_reasons"]
    assert "P14_SOURCE_P13_UNSAFE_FLAG_TRUE:runtime_settings_mutated" in report["block_reasons"]
    assert report["live_scaled_execution_enabled"] is False
    assert report["live_order_submission_allowed"] is False


def test_p14_negative_fixtures_all_block_fail_closed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)

    results = build_p14_negative_fixture_results(cfg=cfg)

    assert results["all_negative_fixtures_blocked_fail_closed"] is True
    assert results["limited_live_scaled_auto_trading_allowed"] is False
    assert results["live_scaled_runtime_enablement_allowed"] is False
    assert results["live_scaled_execution_enabled"] is False
    assert results["live_order_submission_allowed"] is False
    assert results["secret_value_accessed"] is False
    for item in results["fixture_results"].values():
        assert item["blocked_fail_closed"] is True
        assert item["live_scaled_approval_valid_review_only"] is False
        assert item["live_scaled_execution_enabled"] is False
        assert item["live_order_submission_allowed"] is False


def test_p14_persist_writes_waiting_report_summary_registry_and_negative_fixtures(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)
    atomic_write_json(tmp_path / "storage" / "latest" / "p13_live_scaled_readiness_review_report.json", _p13_waiting())

    report = persist_live_scaled_approval_intake_validation(cfg=cfg)

    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert (tmp_path / "storage" / "latest" / "p14_live_scaled_approval_intake_validation_report.json").exists()
    assert (tmp_path / "storage" / "latest" / "p14_live_scaled_approval_intake_validation_summary.json").exists()
    assert (tmp_path / "storage" / "latest" / "p14_live_scaled_approval_intake_validation_negative_fixture_results.json").exists()
    assert (tmp_path / "storage" / "latest" / "p14_live_scaled_approval_intake_validation_registry_record.json").exists()
    assert (tmp_path / "storage" / "p14_live_scaled_approval_intake_validation" / "p14_live_scaled_approval_intake_validation_report.json").exists()
    summary = read_json(tmp_path / "storage" / "latest" / "p14_live_scaled_approval_intake_validation_summary.json")
    assert summary["live_scaled_approval_valid_review_only"] is False
    assert summary["separate_runtime_enablement_step_required"] is True
    assert summary["limited_live_scaled_auto_trading_allowed"] is False
    assert summary["live_scaled_runtime_enablement_allowed"] is False
    assert summary["live_scaled_execution_enabled"] is False
    assert summary["live_order_submission_allowed"] is False
    assert summary["secret_value_accessed"] is False


def test_p14_persist_creates_packet_draft_when_p13_is_ready_but_waits_for_intake(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)
    atomic_write_json(tmp_path / "storage" / "latest" / "p13_live_scaled_readiness_review_report.json", _p13_ready())

    report = persist_live_scaled_approval_intake_validation(cfg=cfg)

    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert "P14_APPROVAL_INTAKE_MISSING" in report["waiting_reasons"]
    assert (tmp_path / "storage" / "latest" / "p14_live_scaled_approval_packet.json").exists()
    packet = read_json(tmp_path / "storage" / "latest" / "p14_live_scaled_approval_packet.json")
    assert packet["stage"] == "limited_live_scaled"
    assert packet["requires_manual_operator_intake"] is True
    assert packet["requires_separate_runtime_enablement_step"] is True
    assert packet["live_scaled_execution_enabled"] is False
    assert packet["live_order_submission_allowed"] is False


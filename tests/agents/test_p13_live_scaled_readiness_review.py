from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.live_scaled_readiness_review import (
    LiveScaledControlPolicyEvidence,
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_READY_FOR_SEPARATE_APPROVAL_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_default_live_scaled_control_policy_evidence,
    build_live_scaled_readiness_review_report,
    build_p13_negative_fixture_results,
    persist_live_scaled_readiness_review,
    validate_live_scaled_control_policy_evidence,
)


def _write_min_project(root: Path) -> None:
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  name: tmp-crypto-ai-system\n  version: test\n"
        "storage:\n  latest_dir: storage/latest\n  registry_dir: storage/registries\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text("[project]\nname='tmp-crypto-ai-system'\nversion='0.286.0'\n", encoding="utf-8")


def _p12_waiting() -> dict:
    return {
        "status": "P12_REPEATED_CLEAN_LIVE_CANARY_SESSIONS_WAITING_REVIEW_ONLY",
        "p12_repeated_clean_live_canary_sessions_sha256": "c" * 64,
        "repeated_live_canary_session_evidence_present": False,
        "repeated_clean_live_canary_sessions_validated": False,
        "live_scaled_readiness_candidate_evidence_created": False,
        "live_scaled_readiness_allowed": False,
        "live_scaled_promotion_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
    }


def _p12_valid() -> dict:
    return {
        "status": "P12_REPEATED_CLEAN_LIVE_CANARY_SESSIONS_VALIDATED_REVIEW_ONLY",
        "p12_repeated_clean_live_canary_sessions_sha256": "c" * 64,
        "repeated_live_canary_session_evidence_present": True,
        "repeated_clean_live_canary_sessions_validated": True,
        "live_scaled_readiness_candidate_evidence_created": True,
        "clean_submitted_live_canary_session_count": 8,
        "reconciliation_mismatch_count": 0,
        "manual_override_count": 0,
        "incident_count": 0,
        "critical_alert_count": 0,
        "average_abs_slippage_bps": 1.0,
        "api_error_rate": 0.0,
        "rejection_rate": 0.0,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "api_key_value_logged": False,
        "api_secret_value_logged": False,
        "live_scaled_readiness_allowed": False,
        "live_scaled_promotion_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "withdrawal_permission_allowed": False,
        "transfer_permission_allowed": False,
        "admin_permission_allowed": False,
    }


def test_p13_waits_review_only_without_p12_repeated_live_canary_evidence(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)
    atomic_write_json(tmp_path / "storage" / "latest" / "p12_repeated_clean_live_canary_sessions_report.json", _p12_waiting())

    report = build_live_scaled_readiness_review_report(cfg=cfg)

    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["waiting"] is True
    assert report["ready_for_separate_live_scaled_approval_review_only"] is False
    assert "P13_SOURCE_P12_REPEATED_CLEAN_LIVE_CANARY_SESSIONS_NOT_VALIDATED" in report["waiting_reasons"]
    assert report["live_scaled_approval_packet_may_be_drafted"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["secret_value_accessed"] is False
    assert report["unsafe_truthy_execution_flags"] == []


def test_p13_validates_readiness_for_separate_approval_review_only() -> None:
    report = build_live_scaled_readiness_review_report(
        p12_report=_p12_valid(),
        control_policy_evidence=build_default_live_scaled_control_policy_evidence(),
    )

    assert report["status"] == STATUS_READY_FOR_SEPARATE_APPROVAL_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["waiting"] is False
    assert report["ready_for_separate_live_scaled_approval_review_only"] is True
    assert report["live_scaled_approval_packet_may_be_drafted"] is True
    assert report["separate_live_scaled_approval_required"] is True
    assert report["separate_live_scaled_approval_present"] is False
    assert report["separate_live_scaled_approval_valid"] is False
    assert report["limited_live_scaled_auto_trading_allowed"] is False
    assert report["live_scaled_readiness_allowed"] is False
    assert report["live_scaled_promotion_allowed"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["secret_value_accessed"] is False
    assert report["readiness_controls"]["symbol_scope"] == ["BTCUSDT"]


def test_p13_policy_validation_blocks_caps_missing_controls_and_unsafe_flags() -> None:
    policy = {
        **LiveScaledControlPolicyEvidence().to_dict(),
        "symbol_scope": ["BTCUSDT", "ETHUSDT"],
        "fixed_max_notional_usdt": 1000,
        "daily_loss_cap_usdt": 50,
        "max_daily_order_count": 99,
        "max_consecutive_loss_count": 99,
        "max_open_position_count": 5,
        "max_leverage": 5,
        "max_slippage_bps": 50,
        "max_api_error_rate": 1.0,
        "operator_manual_kill_switch_enforced": False,
        "rollback_ready": False,
        "daily_report_ready": False,
        "incident_report_ready": False,
        "live_scaled_execution_enabled": True,
        "secret_value_logged": True,
        "withdrawal_permission_allowed": True,
    }

    validation = validate_live_scaled_control_policy_evidence(policy)

    assert validation["live_scaled_control_policy_valid"] is False
    assert "P13_POLICY_SYMBOL_SCOPE_NOT_BTCUSDT_ONLY" in validation["block_reasons"]
    assert "P13_POLICY_FIXED_MAX_NOTIONAL_OUT_OF_RANGE" in validation["block_reasons"]
    assert "P13_POLICY_DAILY_LOSS_CAP_OUT_OF_RANGE" in validation["block_reasons"]
    assert "P13_POLICY_MAX_DAILY_ORDER_COUNT_OUT_OF_RANGE" in validation["block_reasons"]
    assert "P13_POLICY_MAX_LEVERAGE_OUT_OF_RANGE" in validation["block_reasons"]
    assert "P13_POLICY_REQUIRED_KILL_SWITCH_MISSING:operator_manual_kill_switch_enforced" in validation["block_reasons"]
    assert "P13_POLICY_REQUIRED_OPERATIONAL_CONTROL_MISSING:rollback_ready" in validation["block_reasons"]
    assert "P13_POLICY_UNSAFE_FLAG_TRUE:live_scaled_execution_enabled" in validation["block_reasons"]
    assert "P13_POLICY_UNSAFE_FLAG_TRUE:secret_value_logged" in validation["block_reasons"]
    assert "P13_POLICY_UNSAFE_FLAG_TRUE:withdrawal_permission_allowed" in validation["block_reasons"]


def test_p13_blocks_p12_source_mismatch_secret_scaled_and_runtime_mutation() -> None:
    p12 = {
        **_p12_valid(),
        "reconciliation_mismatch_count": 1,
        "secret_value_logged": True,
        "live_scaled_execution_enabled": True,
        "runtime_settings_mutated": True,
    }

    report = build_live_scaled_readiness_review_report(
        p12_report=p12,
        control_policy_evidence=build_default_live_scaled_control_policy_evidence(),
    )

    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert report["blocked"] is True
    assert "P13_SOURCE_P12_RECONCILIATION_MISMATCH_NONZERO" in report["block_reasons"]
    assert "P13_SOURCE_P12_UNSAFE_FLAG_TRUE:secret_value_logged" in report["block_reasons"]
    assert "P13_SOURCE_P12_UNSAFE_FLAG_TRUE:live_scaled_execution_enabled" in report["block_reasons"]
    assert "P13_SOURCE_P12_UNSAFE_FLAG_TRUE:runtime_settings_mutated" in report["block_reasons"]
    assert report["live_scaled_execution_enabled"] is False


def test_p13_negative_fixtures_all_block_fail_closed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)

    results = build_p13_negative_fixture_results(cfg=cfg)

    assert results["all_negative_fixtures_blocked_fail_closed"] is True
    assert results["live_scaled_readiness_allowed"] is False
    assert results["live_scaled_promotion_allowed"] is False
    assert results["live_scaled_execution_enabled"] is False
    assert results["live_order_submission_allowed"] is False
    assert results["secret_value_accessed"] is False
    for item in results["fixture_results"].values():
        assert item["blocked_fail_closed"] is True
        assert item["ready_for_separate_live_scaled_approval_review_only"] is False
        assert item["live_scaled_execution_enabled"] is False
        assert item["live_order_submission_allowed"] is False


def test_p13_persist_writes_waiting_report_summary_registry_and_negative_fixtures(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)
    atomic_write_json(tmp_path / "storage" / "latest" / "p12_repeated_clean_live_canary_sessions_report.json", _p12_waiting())

    report = persist_live_scaled_readiness_review(cfg=cfg)

    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert (tmp_path / "storage" / "latest" / "p13_live_scaled_readiness_review_report.json").exists()
    assert (tmp_path / "storage" / "latest" / "p13_live_scaled_readiness_review_summary.json").exists()
    assert (tmp_path / "storage" / "latest" / "p13_live_scaled_readiness_review_negative_fixture_results.json").exists()
    assert (tmp_path / "storage" / "latest" / "p13_live_scaled_readiness_review_registry_record.json").exists()
    assert (tmp_path / "storage" / "p13_live_scaled_readiness_review" / "p13_live_scaled_readiness_review_report.json").exists()
    summary = read_json(tmp_path / "storage" / "latest" / "p13_live_scaled_readiness_review_summary.json")
    assert summary["ready_for_separate_live_scaled_approval_review_only"] is False
    assert summary["live_scaled_approval_packet_may_be_drafted"] is False
    assert summary["separate_live_scaled_approval_required"] is True
    assert summary["separate_live_scaled_approval_present"] is False
    assert summary["limited_live_scaled_auto_trading_allowed"] is False
    assert summary["live_scaled_execution_enabled"] is False
    assert summary["live_order_submission_allowed"] is False
    assert summary["secret_value_accessed"] is False

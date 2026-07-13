from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.limited_live_scaled_runtime_enablement_boundary import (
    LIMITED_LIVE_SCALED_RUNTIME_ENABLEMENT_PHRASE,
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALID_REVIEW_ONLY_NO_EXECUTION,
    STATUS_WAITING_REVIEW_ONLY,
    build_limited_live_scaled_runtime_enablement_boundary_report,
    build_p15_negative_fixture_results,
    build_review_only_runtime_loop_controls,
    build_review_only_runtime_stage_policy,
    build_valid_runtime_enablement_request,
    persist_limited_live_scaled_runtime_enablement_boundary,
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


def _p14_waiting() -> dict:
    return {
        "status": "P14_LIVE_SCALED_APPROVAL_INTAKE_WAITING_REVIEW_ONLY",
        "p14_live_scaled_approval_intake_validation_sha256": "f" * 64,
        "live_scaled_approval_valid_review_only": False,
        "live_scaled_approval_packet_valid": False,
        "live_scaled_approval_intake_valid": False,
        "separate_runtime_enablement_step_required": True,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
    }


def _p14_valid() -> dict:
    return {
        "status": "P14_LIVE_SCALED_APPROVAL_INTAKE_VALID_REVIEW_ONLY_NO_EXECUTION",
        "p14_live_scaled_approval_intake_validation_sha256": "f" * 64,
        "live_scaled_approval_valid_review_only": True,
        "live_scaled_approval_packet_valid": True,
        "live_scaled_approval_intake_valid": True,
        "separate_runtime_enablement_step_required": True,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
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


def _valid_chain() -> tuple[dict, dict, dict, dict]:
    p14 = _p14_valid()
    request = build_valid_runtime_enablement_request(p14)
    policy = build_review_only_runtime_stage_policy(p14)
    loop = build_review_only_runtime_loop_controls()
    return p14, request, policy, loop


def test_p15_waits_review_only_without_p14_valid_approval(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)
    atomic_write_json(tmp_path / "storage" / "latest" / "p14_live_scaled_approval_intake_validation_report.json", _p14_waiting())

    report = persist_limited_live_scaled_runtime_enablement_boundary(cfg=cfg)

    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["waiting"] is True
    assert report["blocked"] is False
    assert "P15_SOURCE_P14_LIVE_SCALED_APPROVAL_NOT_VALID" in report["waiting_reasons"]
    assert report["p15_limited_live_scaled_runtime_boundary_valid_review_only"] is False
    assert report["limited_live_scaled_auto_trading_allowed"] is False
    assert report["live_scaled_runtime_enablement_allowed"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["runtime_loop_started"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["secret_value_accessed"] is False
    assert report["unsafe_truthy_execution_flags"] == []

    summary = read_json(tmp_path / "storage" / "latest" / "p15_limited_live_scaled_runtime_enablement_boundary_summary.json")
    assert summary["status"] == STATUS_WAITING_REVIEW_ONLY
    assert summary["limited_live_scaled_auto_trading_allowed"] is False


def test_p15_validates_runtime_boundary_review_only_no_execution() -> None:
    p14, request, policy, loop = _valid_chain()

    report = build_limited_live_scaled_runtime_enablement_boundary_report(
        p14_report=p14,
        runtime_enablement_request=request,
        runtime_stage_policy=policy,
        runtime_loop_controls=loop,
    )

    assert report["status"] == STATUS_VALID_REVIEW_ONLY_NO_EXECUTION
    assert report["blocked"] is False
    assert report["waiting"] is False
    assert report["p15_limited_live_scaled_runtime_boundary_valid_review_only"] is True
    assert report["runtime_stage_policy_valid_review_only"] is True
    assert report["runtime_loop_controls_valid_review_only"] is True
    assert report["operator_runtime_enablement_request_valid_review_only"] is True
    assert report["limited_live_scaled_runtime_boundary_ready_review_only"] is True
    assert report["separate_operator_runtime_process_required"] is True
    assert request["enablement_phrase"] == LIMITED_LIVE_SCALED_RUNTIME_ENABLEMENT_PHRASE
    assert report["limited_live_scaled_auto_trading_allowed"] is False
    assert report["live_scaled_runtime_enablement_allowed"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["runtime_loop_started"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["secret_value_accessed"] is False
    assert report["unsafe_truthy_execution_flags"] == []


def test_p15_request_validation_blocks_missing_phrase_scheduler_secret_and_runtime_mutation() -> None:
    p14, request, policy, loop = _valid_chain()
    bad_request = {
        **request,
        "operator_id": "",
        "ticket_or_signature": "",
        "enablement_phrase": "APPROVED",
        "auto_generated_enablement_file": True,
        "acknowledged_kill_switches": False,
        "requests_runtime_scheduler_enabled": True,
        "requests_live_scaled_execution_enabled": True,
        "requests_live_order_submission_allowed": True,
        "requests_runtime_settings_mutation": True,
        "secret_value_logged": True,
        "withdrawal_permission_requested": True,
    }

    report = build_limited_live_scaled_runtime_enablement_boundary_report(
        p14_report=p14,
        runtime_enablement_request=bad_request,
        runtime_stage_policy=policy,
        runtime_loop_controls=loop,
    )

    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P15_REQUEST_OPERATOR_ID_MISSING" in report["block_reasons"]
    assert "P15_REQUEST_TICKET_OR_SIGNATURE_MISSING" in report["block_reasons"]
    assert "P15_REQUEST_EXACT_PHRASE_MISSING" in report["block_reasons"]
    assert "P15_REQUEST_AUTO_GENERATED_FILE" in report["block_reasons"]
    assert "P15_REQUEST_ACKNOWLEDGEMENT_MISSING:acknowledged_kill_switches" in report["block_reasons"]
    assert "P15_REQUEST_UNSAFE_FLAG_TRUE:requests_runtime_scheduler_enabled" in report["block_reasons"]
    assert "P15_REQUEST_UNSAFE_FLAG_TRUE:requests_live_scaled_execution_enabled" in report["block_reasons"]
    assert "P15_REQUEST_UNSAFE_FLAG_TRUE:requests_live_order_submission_allowed" in report["block_reasons"]
    assert "P15_REQUEST_UNSAFE_FLAG_TRUE:requests_runtime_settings_mutation" in report["block_reasons"]
    assert "P15_REQUEST_UNSAFE_FLAG_TRUE:secret_value_logged" in report["block_reasons"]
    assert "P15_REQUEST_UNSAFE_FLAG_TRUE:withdrawal_permission_requested" in report["block_reasons"]
    assert report["limited_live_scaled_auto_trading_allowed"] is False
    assert report["runtime_scheduler_enabled"] is False


def test_p15_policy_validation_blocks_caps_scope_missing_requirements_and_unsafe_flags() -> None:
    p14, request, policy, loop = _valid_chain()
    bad_policy = {
        **policy,
        "symbol_scope": ["BTCUSDT", "ETHUSDT"],
        "fixed_max_notional_usdt": 999.0,
        "daily_loss_cap_usdt": 999.0,
        "max_daily_order_count": 99,
        "max_leverage": 25.0,
        "requires_hot_path_preorder_risk_gate": False,
        "requires_reconciliation": False,
        "runtime_scheduler_enabled": True,
        "live_order_submission_allowed": True,
        "place_order_enabled": True,
        "secret_value_accessed": True,
        "withdrawal_permission_allowed": True,
    }

    report = build_limited_live_scaled_runtime_enablement_boundary_report(
        p14_report=p14,
        runtime_enablement_request=request,
        runtime_stage_policy=bad_policy,
        runtime_loop_controls=loop,
    )

    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P15_POLICY_SYMBOL_SCOPE_NOT_BTCUSDT_ONLY" in report["block_reasons"]
    assert "P15_POLICY_FIXED_MAX_NOTIONAL_OUT_OF_RANGE" in report["block_reasons"]
    assert "P15_POLICY_DAILY_LOSS_CAP_OUT_OF_RANGE" in report["block_reasons"]
    assert "P15_POLICY_MAX_DAILY_ORDER_COUNT_OUT_OF_RANGE" in report["block_reasons"]
    assert "P15_POLICY_MAX_LEVERAGE_OUT_OF_RANGE" in report["block_reasons"]
    assert "P15_POLICY_REQUIRED_FIELD_FALSE:requires_hot_path_preorder_risk_gate" in report["block_reasons"]
    assert "P15_POLICY_REQUIRED_FIELD_FALSE:requires_reconciliation" in report["block_reasons"]
    assert "P15_POLICY_UNSAFE_FLAG_TRUE:runtime_scheduler_enabled" in report["block_reasons"]
    assert "P15_POLICY_UNSAFE_FLAG_TRUE:live_order_submission_allowed" in report["block_reasons"]
    assert "P15_POLICY_UNSAFE_FLAG_TRUE:place_order_enabled" in report["block_reasons"]
    assert "P15_POLICY_UNSAFE_FLAG_TRUE:secret_value_accessed" in report["block_reasons"]
    assert "P15_POLICY_UNSAFE_FLAG_TRUE:withdrawal_permission_allowed" in report["block_reasons"]
    assert report["live_order_submission_allowed"] is False


def test_p15_loop_validation_blocks_missing_controls_scheduler_enablement_endpoint_and_secret_leak() -> None:
    p14, request, policy, loop = _valid_chain()
    bad_loop = {
        **loop,
        "fresh_market_data_required": False,
        "idempotency_key_required": False,
        "reconciliation_required": False,
        "daily_report_required": False,
        "incident_report_required": False,
        "runtime_scheduler_enabled": True,
        "runtime_loop_started": True,
        "live_order_endpoint_called": True,
        "live_order_submission_allowed": True,
        "secret_value_logged": True,
        "runtime_settings_mutated": True,
    }

    report = build_limited_live_scaled_runtime_enablement_boundary_report(
        p14_report=p14,
        runtime_enablement_request=request,
        runtime_stage_policy=policy,
        runtime_loop_controls=bad_loop,
    )

    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P15_LOOP_REQUIRED_FIELD_FALSE:fresh_market_data_required" in report["block_reasons"]
    assert "P15_LOOP_REQUIRED_FIELD_FALSE:idempotency_key_required" in report["block_reasons"]
    assert "P15_LOOP_REQUIRED_FIELD_FALSE:reconciliation_required" in report["block_reasons"]
    assert "P15_LOOP_REQUIRED_FIELD_FALSE:daily_report_required" in report["block_reasons"]
    assert "P15_LOOP_REQUIRED_FIELD_FALSE:incident_report_required" in report["block_reasons"]
    assert "P15_LOOP_UNSAFE_FLAG_TRUE:runtime_scheduler_enabled" in report["block_reasons"]
    assert "P15_LOOP_UNSAFE_FLAG_TRUE:runtime_loop_started" in report["block_reasons"]
    assert "P15_LOOP_UNSAFE_FLAG_TRUE:live_order_endpoint_called" in report["block_reasons"]
    assert "P15_LOOP_UNSAFE_FLAG_TRUE:live_order_submission_allowed" in report["block_reasons"]
    assert "P15_LOOP_UNSAFE_FLAG_TRUE:secret_value_logged" in report["block_reasons"]
    assert "P15_LOOP_UNSAFE_FLAG_TRUE:runtime_settings_mutated" in report["block_reasons"]
    assert report["runtime_scheduler_enabled"] is False
    assert report["live_order_endpoint_called"] is False


def test_p15_negative_fixture_results_all_blocked_fail_closed() -> None:
    payload = build_p15_negative_fixture_results()

    assert payload["all_negative_fixtures_blocked_fail_closed"] is True
    assert payload["limited_live_scaled_auto_trading_allowed"] is False
    assert payload["runtime_scheduler_enabled"] is False
    assert payload["runtime_loop_started"] is False
    assert payload["live_scaled_execution_enabled"] is False
    assert payload["live_order_submission_allowed"] is False
    assert payload["secret_value_accessed"] is False
    for name, item in payload["fixture_results"].items():
        assert item["blocked_fail_closed"] is True, name
        assert item["p15_limited_live_scaled_runtime_boundary_valid_review_only"] is False
        assert item["limited_live_scaled_auto_trading_allowed"] is False
        assert item["runtime_scheduler_enabled"] is False
        assert item["live_order_submission_allowed"] is False
        assert item["secret_value_accessed"] is False

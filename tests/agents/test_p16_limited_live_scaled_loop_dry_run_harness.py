from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.limited_live_scaled_loop_dry_run_harness import (
    MIN_DRY_RUN_TICKS,
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALID_REVIEW_ONLY_NO_EXECUTION,
    STATUS_WAITING_REVIEW_ONLY,
    build_limited_live_scaled_loop_dry_run_harness_report,
    build_p16_negative_fixture_results,
    build_review_only_dry_run_daily_report,
    build_review_only_dry_run_ticks,
    persist_limited_live_scaled_loop_dry_run_harness,
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


def _p15_waiting() -> dict:
    return {
        "status": "P15_LIMITED_LIVE_SCALED_RUNTIME_ENABLEMENT_BOUNDARY_WAITING_REVIEW_ONLY",
        "p15_limited_live_scaled_runtime_enablement_boundary_sha256": "e" * 64,
        "p15_limited_live_scaled_runtime_boundary_valid_review_only": False,
        "runtime_stage_policy_valid_review_only": False,
        "runtime_loop_controls_valid_review_only": False,
        "operator_runtime_enablement_request_valid_review_only": False,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "secret_value_accessed": False,
    }


def _p15_valid() -> dict:
    return {
        "status": "P15_LIMITED_LIVE_SCALED_RUNTIME_ENABLEMENT_BOUNDARY_VALID_REVIEW_ONLY_NO_EXECUTION",
        "p15_limited_live_scaled_runtime_enablement_boundary_sha256": "f" * 64,
        "p15_limited_live_scaled_runtime_boundary_valid_review_only": True,
        "runtime_stage_policy_valid_review_only": True,
        "runtime_loop_controls_valid_review_only": True,
        "operator_runtime_enablement_request_valid_review_only": True,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_runtime_enablement_performed": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "actual_live_order_submitted": False,
        "live_order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
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


def _valid_chain() -> tuple[dict, list[dict], dict]:
    p15 = _p15_valid()
    ticks = build_review_only_dry_run_ticks(p15)
    daily = build_review_only_dry_run_daily_report(p15, ticks)
    return p15, ticks, daily


def test_p16_waits_review_only_without_p15_valid_boundary(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)
    atomic_write_json(
        tmp_path / "storage" / "latest" / "p15_limited_live_scaled_runtime_enablement_boundary_report.json",
        _p15_waiting(),
    )

    report = persist_limited_live_scaled_loop_dry_run_harness(cfg=cfg)

    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["waiting"] is True
    assert report["blocked"] is False
    assert "P16_SOURCE_P15_RUNTIME_BOUNDARY_NOT_VALID" in report["waiting_reasons"]
    assert report["p16_limited_live_scaled_loop_dry_run_harness_valid_review_only"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["runtime_loop_started"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["actual_live_order_submitted"] is False
    assert report["secret_value_accessed"] is False
    assert report["unsafe_truthy_execution_flags"] == []

    summary = read_json(tmp_path / "storage" / "latest" / "p16_limited_live_scaled_loop_dry_run_harness_summary.json")
    assert summary["status"] == STATUS_WAITING_REVIEW_ONLY
    assert summary["runtime_scheduler_enabled"] is False
    assert summary["live_order_submission_allowed"] is False


def test_p16_validates_loop_dry_run_review_only_no_execution() -> None:
    p15, ticks, daily = _valid_chain()

    report = build_limited_live_scaled_loop_dry_run_harness_report(
        p15_report=p15,
        dry_run_ticks=ticks,
        dry_run_daily_report=daily,
    )

    assert report["status"] == STATUS_VALID_REVIEW_ONLY_NO_EXECUTION
    assert report["blocked"] is False
    assert report["waiting"] is False
    assert report["dry_run_tick_count"] == MIN_DRY_RUN_TICKS
    assert report["p16_limited_live_scaled_loop_dry_run_harness_valid_review_only"] is True
    assert report["p16_scheduler_tick_simulation_valid_review_only"] is True
    assert report["p16_would_submit_evidence_chain_valid_review_only"] is True
    assert report["p16_reconciliation_report_chain_valid_review_only"] is True
    assert report["p16_daily_incident_reporting_valid_review_only"] is True
    assert report["scheduler_tick_simulation_performed_review_only"] is True
    assert report["would_submit_evidence_created_review_only"] is True
    assert report["post_submit_relock_simulated_review_only"] is True
    assert report["limited_live_scaled_auto_trading_allowed"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["runtime_loop_started"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["actual_live_order_submitted"] is False
    assert report["live_order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["secret_value_accessed"] is False
    assert report["unsafe_truthy_execution_flags"] == []


def test_p16_generates_ticks_and_daily_report_when_p15_valid(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)
    atomic_write_json(
        tmp_path / "storage" / "latest" / "p15_limited_live_scaled_runtime_enablement_boundary_report.json",
        _p15_valid(),
    )

    report = persist_limited_live_scaled_loop_dry_run_harness(cfg=cfg)

    assert report["status"] == STATUS_VALID_REVIEW_ONLY_NO_EXECUTION
    ticks = read_json(tmp_path / "storage" / "latest" / "p16_limited_live_scaled_dry_run_ticks.json")
    daily = read_json(tmp_path / "storage" / "latest" / "p16_limited_live_scaled_dry_run_daily_report.json")
    registry = read_json(tmp_path / "storage" / "latest" / "p16_limited_live_scaled_loop_dry_run_harness_registry_record.json")
    assert isinstance(ticks, list)
    assert len(ticks) == MIN_DRY_RUN_TICKS
    assert daily["daily_report_created"] is True
    assert registry["live_order_submission_allowed"] is False
    assert registry["secret_value_accessed"] is False


def test_p16_blocks_missing_fresh_data_failed_signal_risk_and_duplicate_idempotency() -> None:
    p15, ticks, daily = _valid_chain()
    bad_ticks = [
        {
            **ticks[0],
            "fresh_market_data_loaded": False,
            "signal_qa_passed": False,
            "hot_path_preorder_risk_gate_passed": False,
            "idempotency_key_seen_before": True,
        },
        *ticks[1:],
    ]

    report = build_limited_live_scaled_loop_dry_run_harness_report(
        p15_report=p15,
        dry_run_ticks=bad_ticks,
        dry_run_daily_report=daily,
    )

    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P16_TICK_0_REQUIRED_FIELD_FALSE:fresh_market_data_loaded" in report["block_reasons"]
    assert "P16_TICK_0_REQUIRED_FIELD_FALSE:signal_qa_passed" in report["block_reasons"]
    assert "P16_TICK_0_REQUIRED_FIELD_FALSE:hot_path_preorder_risk_gate_passed" in report["block_reasons"]
    assert "P16_TICK_0_DUPLICATE_IDEMPOTENCY_KEY" in report["block_reasons"]
    assert report["p16_limited_live_scaled_loop_dry_run_harness_valid_review_only"] is False
    assert report["live_order_submission_allowed"] is False


def test_p16_blocks_endpoint_call_scheduler_enablement_secret_leak_and_runtime_mutation() -> None:
    p15, ticks, daily = _valid_chain()
    bad_ticks = [
        {
            **ticks[0],
            "runtime_scheduler_enabled": True,
            "runtime_loop_started": True,
            "live_order_submission_allowed": True,
            "place_order_enabled": True,
            "live_order_endpoint_called": True,
            "http_request_sent": True,
            "signature_created": True,
            "secret_value_logged": True,
            "runtime_settings_mutated": True,
        },
        *ticks[1:],
    ]

    report = build_limited_live_scaled_loop_dry_run_harness_report(
        p15_report=p15,
        dry_run_ticks=bad_ticks,
        dry_run_daily_report=daily,
    )

    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P16_TICK_0_UNSAFE_FLAG_TRUE:runtime_scheduler_enabled" in report["block_reasons"]
    assert "P16_TICK_0_UNSAFE_FLAG_TRUE:runtime_loop_started" in report["block_reasons"]
    assert "P16_TICK_0_UNSAFE_FLAG_TRUE:live_order_submission_allowed" in report["block_reasons"]
    assert "P16_TICK_0_UNSAFE_FLAG_TRUE:place_order_enabled" in report["block_reasons"]
    assert "P16_TICK_0_UNSAFE_FLAG_TRUE:live_order_endpoint_called" in report["block_reasons"]
    assert "P16_TICK_0_UNSAFE_FLAG_TRUE:http_request_sent" in report["block_reasons"]
    assert "P16_TICK_0_UNSAFE_FLAG_TRUE:signature_created" in report["block_reasons"]
    assert "P16_TICK_0_UNSAFE_FLAG_TRUE:secret_value_logged" in report["block_reasons"]
    assert "P16_TICK_0_UNSAFE_FLAG_TRUE:runtime_settings_mutated" in report["block_reasons"]
    assert report["runtime_scheduler_enabled"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["secret_value_accessed"] is False


def test_p16_blocks_missing_post_submit_relock_reconciliation_and_reports() -> None:
    p15, ticks, daily = _valid_chain()
    bad_ticks = [
        {
            **ticks[0],
            "post_submit_relock_confirmed": False,
            "reconciliation_required": False,
            "daily_report_required": False,
            "incident_report_required": False,
        },
        *ticks[1:],
    ]
    bad_daily = {
        **daily,
        "daily_report_created": False,
        "incident_report_created": False,
        "api_error_count": 1,
        "reconciliation_mismatch_count": 1,
    }

    report = build_limited_live_scaled_loop_dry_run_harness_report(
        p15_report=p15,
        dry_run_ticks=bad_ticks,
        dry_run_daily_report=bad_daily,
    )

    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P16_TICK_0_REQUIRED_FIELD_FALSE:post_submit_relock_confirmed" in report["block_reasons"]
    assert "P16_TICK_0_REQUIRED_FIELD_FALSE:reconciliation_required" in report["block_reasons"]
    assert "P16_TICK_0_REQUIRED_FIELD_FALSE:daily_report_required" in report["block_reasons"]
    assert "P16_TICK_0_REQUIRED_FIELD_FALSE:incident_report_required" in report["block_reasons"]
    assert "P16_DAILY_REPORT_REQUIRED_FIELD_FALSE:daily_report_created" in report["block_reasons"]
    assert "P16_DAILY_REPORT_REQUIRED_FIELD_FALSE:incident_report_created" in report["block_reasons"]
    assert "P16_DAILY_REPORT_NONZERO_FIELD:api_error_count" in report["block_reasons"]
    assert "P16_DAILY_REPORT_NONZERO_FIELD:reconciliation_mismatch_count" in report["block_reasons"]


def test_p16_negative_fixture_matrix_blocks_all_cases() -> None:
    payload = build_p16_negative_fixture_results()

    assert payload["all_negative_fixtures_blocked_fail_closed"] is True
    assert payload["limited_live_scaled_auto_trading_allowed"] is False
    assert payload["runtime_scheduler_enabled"] is False
    assert payload["live_order_submission_allowed"] is False
    assert payload["secret_value_accessed"] is False
    assert "tick_missing_fresh_data" in payload["fixture_results"]
    assert "endpoint_called" in payload["fixture_results"]
    assert "secret_leak" in payload["fixture_results"]

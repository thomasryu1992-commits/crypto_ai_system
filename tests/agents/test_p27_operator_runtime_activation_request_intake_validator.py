from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_runtime_activation_request_intake_validator import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALID_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_operator_runtime_activation_request_intake_template,
    build_operator_runtime_activation_request_intake_validator_report,
    build_p27_negative_fixture_results,
    persist_operator_runtime_activation_request_intake_validator,
)
from crypto_ai_system.execution.operator_runtime_activation_request_template_gate import P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_EXACT_PHRASE


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  name: tmp-crypto-ai-system\n  version: test\n"
        "storage:\n  latest_dir: storage/latest\n  registry_dir: storage/registries\n",
        encoding="utf-8",
    )


def _valid_sources() -> tuple[dict, dict, dict, dict, dict]:
    gate_hash = "a" * 64
    template_hash = "b" * 64
    skeleton_hash = "c" * 64
    p26_summary = {
        "status": "P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_TEMPLATE_GATE_GENERATED_REVIEW_ONLY",
        "p26_operator_runtime_activation_request_template_gate_report_sha256": gate_hash,
        "p26_operator_runtime_activation_request_template_generated_review_only": True,
        "p26_final_activation_gate_skeleton_generated_review_only": True,
        "p26_operator_runtime_activation_gate_ready_review_only": True,
        "activation_request_template_is_runtime_authority": False,
        "final_activation_gate_skeleton_is_runtime_authority": False,
        "separate_filled_operator_activation_request_required_after_this_template": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    p26_report = {
        "status": "P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_TEMPLATE_GATE_GENERATED_REVIEW_ONLY",
        "p26_operator_runtime_activation_request_template_gate_report_sha256": gate_hash,
        "p26_operator_runtime_activation_request_template_generated_review_only": True,
        "p26_final_activation_gate_skeleton_generated_review_only": True,
        "p26_operator_runtime_activation_gate_ready_review_only": True,
        "activation_request_template_is_runtime_authority": False,
        "final_activation_gate_skeleton_is_runtime_authority": False,
        "runtime_enablement_performed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    controls = {
        "load_current_stage_policy_before_every_tick",
        "fresh_market_data_before_every_tick",
        "source_qa_before_signal",
        "data_snapshot_and_feature_lineage_required",
        "research_signal_v2_required",
        "signal_qa_required",
        "trading_decision_required",
        "hot_path_preorder_risk_gate_required",
        "order_intent_after_risk_gate_only",
        "duplicate_submit_lock_required",
        "idempotency_key_required",
        "hard_caps_required",
        "post_submit_relock_required",
        "status_polling_required",
        "reconciliation_required",
        "outcome_feedback_required",
        "daily_report_required",
        "incident_report_required",
        "monitoring_alerting_required",
        "rollback_required",
        "full_shutdown_required",
        "all_kill_switches_required",
    }
    p26_template = {
        "request_type": "operator_runtime_activation_request_template_review_only",
        "exact_operator_runtime_activation_request_phrase": P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_EXACT_PHRASE,
        "p26_operator_runtime_activation_request_template_sha256": template_hash,
        "request_is_runtime_authority": False,
        "request_executes_runtime": False,
        "activation_request_executes_runtime": False,
        "runtime_enablement_performed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    p26_skeleton = {
        "skeleton_type": "final_operator_runtime_activation_gate_skeleton_review_only",
        "p26_final_activation_gate_skeleton_sha256": skeleton_hash,
        "activation_gate_is_runtime_authority": False,
        "activation_gate_executes_runtime": False,
        "separate_filled_operator_activation_request_required": True,
        "gate_controls": {field: True for field in controls},
        "runtime_activation_performed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    intake = build_operator_runtime_activation_request_intake_template(
        p26_gate_report_sha256=gate_hash,
        p26_template_sha256=template_hash,
        p26_skeleton_sha256=skeleton_hash,
    )
    intake.update({"operator_id": "operator-thomas", "ticket_or_signature": "TICKET-P27-VALID-001", "requested_at_utc": "2026-07-08T00:00:00Z"})
    return p26_summary, p26_report, p26_template, p26_skeleton, intake


def test_p27_waits_when_p26_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_operator_runtime_activation_request_intake_validator_report(root=tmp_path)
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert "P27_SOURCE_P26_SUMMARY_MISSING" in report["waiting_reasons"]
    assert "P27_OPERATOR_RUNTIME_ACTIVATION_REQUEST_INTAKE_MISSING" in report["waiting_reasons"]
    assert report["live_scaled_execution_enabled"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["secret_value_accessed"] is False


def test_p27_validates_filled_intake_review_only(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    p26_summary, p26_report, p26_template, p26_skeleton, intake = _valid_sources()
    report = build_operator_runtime_activation_request_intake_validator_report(
        root=tmp_path,
        p26_summary=p26_summary,
        p26_report=p26_report,
        p26_template=p26_template,
        p26_skeleton=p26_skeleton,
        p27_intake=intake,
    )
    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert report["p27_operator_runtime_activation_request_intake_valid_review_only"] is True
    assert report["operator_runtime_activation_request_validated_review_only"] is True
    assert report["operator_runtime_activation_request_is_runtime_authority"] is False
    assert report["separate_final_operator_runtime_activation_gate_required"] is True
    assert report["live_scaled_execution_enabled"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["runtime_enablement_performed"] is False
    assert report["operator_runtime_activation_performed"] is False
    assert report["secret_value_accessed"] is False


def test_p27_persists_summary_template_registry_and_negative_results(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    latest = tmp_path / "storage" / "latest"
    p26_summary, p26_report, p26_template, p26_skeleton, intake = _valid_sources()
    atomic_write_json(latest / "p26_operator_runtime_activation_request_template_gate_summary.json", p26_summary)
    atomic_write_json(latest / "p26_operator_runtime_activation_request_template_gate_report.json", p26_report)
    atomic_write_json(latest / "p26_operator_runtime_activation_request_TEMPLATE.json", p26_template)
    atomic_write_json(latest / "p26_final_activation_gate_skeleton.json", p26_skeleton)
    atomic_write_json(latest / "p27_operator_runtime_activation_request_intake.json", intake)
    report = persist_operator_runtime_activation_request_intake_validator(load_config(tmp_path))
    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert (latest / "p27_operator_runtime_activation_request_intake_validator_report.json").exists()
    assert (latest / "p27_operator_runtime_activation_request_intake_validator_summary.json").exists()
    assert (latest / "p27_operator_runtime_activation_request_intake_TEMPLATE.json").exists()
    assert (latest / "p27_operator_runtime_activation_request_intake_validator_negative_fixture_results.json").exists()
    assert (latest / "p27_operator_runtime_activation_request_intake_validator_registry_record.json").exists()
    summary = read_json(latest / "p27_operator_runtime_activation_request_intake_validator_summary.json")
    template = read_json(latest / "p27_operator_runtime_activation_request_intake_TEMPLATE.json")
    negative = read_json(latest / "p27_operator_runtime_activation_request_intake_validator_negative_fixture_results.json")
    registry = read_json(latest / "p27_operator_runtime_activation_request_intake_validator_registry_record.json")
    assert summary["p27_operator_runtime_activation_request_intake_valid_review_only"] is True
    assert template["intake_is_runtime_authority"] is False
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert registry["live_scaled_execution_enabled"] is False


def test_p27_blocks_wrong_phrase_scheduler_endpoint_secret_and_runtime_authority(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    p26_summary, p26_report, p26_template, p26_skeleton, intake = _valid_sources()
    wrong_phrase = build_operator_runtime_activation_request_intake_validator_report(
        root=tmp_path,
        p26_summary=p26_summary,
        p26_report=p26_report,
        p26_template=p26_template,
        p26_skeleton=p26_skeleton,
        p27_intake={**intake, "exact_operator_runtime_activation_request_phrase": "WRONG"},
    )
    assert wrong_phrase["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P27_INTAKE_EXACT_OPERATOR_RUNTIME_ACTIVATION_REQUEST_PHRASE_INVALID" in wrong_phrase["block_reasons"]

    scheduler = build_operator_runtime_activation_request_intake_validator_report(
        root=tmp_path,
        p26_summary=p26_summary,
        p26_report=p26_report,
        p26_template=p26_template,
        p26_skeleton=p26_skeleton,
        p27_intake={**intake, "runtime_scheduler_enabled": True},
    )
    assert scheduler["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P27_UNSAFE_TRUTHY_FLAG_FOUND" in scheduler["block_reasons"]

    endpoint = build_operator_runtime_activation_request_intake_validator_report(
        root=tmp_path,
        p26_summary=p26_summary,
        p26_report=p26_report,
        p26_template=p26_template,
        p26_skeleton=p26_skeleton,
        p27_intake={**intake, "order_endpoint_called": True},
    )
    assert endpoint["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P27_UNSAFE_TRUTHY_FLAG_FOUND" in endpoint["block_reasons"]

    secret = build_operator_runtime_activation_request_intake_validator_report(
        root=tmp_path,
        p26_summary=p26_summary,
        p26_report=p26_report,
        p26_template=p26_template,
        p26_skeleton=p26_skeleton,
        p27_intake={**intake, "operator_note": "BINANCE_API_SECRET=leaked"},
    )
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P27_SECRET_VALUE_PATTERN_FOUND" in secret["block_reasons"]

    authority = build_operator_runtime_activation_request_intake_validator_report(
        root=tmp_path,
        p26_summary=p26_summary,
        p26_report=p26_report,
        p26_template=p26_template,
        p26_skeleton=p26_skeleton,
        p27_intake={**intake, "intake_is_runtime_authority": True},
    )
    assert authority["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P27_INTAKE_RUNTIME_AUTHORITY_CLAIMED" in authority["block_reasons"]


def test_p27_template_is_not_runtime_authority() -> None:
    template = build_operator_runtime_activation_request_intake_template()
    assert template["intake_is_runtime_authority"] is False
    assert template["request_executes_runtime"] is False
    assert template["activation_request_executes_runtime"] is False
    assert template["live_scaled_execution_enabled"] is False
    assert template["runtime_scheduler_enabled"] is False
    assert template["secret_value_accessed"] is False
    assert template["no_endpoint_call_allowed_by_this_intake_acknowledged"] is True


def test_p27_negative_fixtures_fail_closed() -> None:
    results = build_p27_negative_fixture_results()
    assert results["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    for item in results["fixture_results"].values():
        assert item["live_scaled_execution_enabled"] is False
        assert item["runtime_scheduler_enabled"] is False
        assert item["secret_value_accessed"] is False

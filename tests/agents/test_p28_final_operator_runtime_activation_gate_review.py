from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.final_operator_runtime_activation_gate_review import (
    P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_EXACT_PHRASE,
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALID_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_final_operator_runtime_activation_gate_review_controls_template,
    build_final_operator_runtime_activation_gate_review_report,
    build_p28_negative_fixture_results,
    persist_final_operator_runtime_activation_gate_review,
)
from crypto_ai_system.utils.audit import sha256_json


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text("storage:\n  latest_dir: storage/latest\n", encoding="utf-8")


def _valid_sources() -> tuple[dict, dict, dict, dict]:
    p27_report_hash = "a" * 64
    p27_intake = {
        "request_type": "operator_runtime_activation_request_intake_review_only",
        "operator_id": "operator-thomas",
        "ticket_or_signature": "TICKET-P27-VALID-001",
        "manual_operator_submission": True,
        "intake_is_runtime_authority": False,
        "request_executes_runtime": False,
        "activation_request_executes_runtime": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    p27_intake_hash = sha256_json(p27_intake)
    p27_summary = {
        "status": "P27_OPERATOR_RUNTIME_ACTIVATION_REQUEST_INTAKE_VALIDATOR_VALID_REVIEW_ONLY",
        "p27_operator_runtime_activation_request_intake_validator_sha256": p27_report_hash,
        "p27_operator_runtime_activation_request_intake_sha256": p27_intake_hash,
        "p27_operator_runtime_activation_request_intake_valid_review_only": True,
        "operator_runtime_activation_request_validated_review_only": True,
        "operator_runtime_activation_request_is_runtime_authority": False,
        "separate_final_operator_runtime_activation_gate_required": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    p27_report = {
        "status": "P27_OPERATOR_RUNTIME_ACTIVATION_REQUEST_INTAKE_VALIDATOR_VALID_REVIEW_ONLY",
        "p27_operator_runtime_activation_request_intake_validator_sha256": p27_report_hash,
        "p27_operator_runtime_activation_request_intake_sha256": p27_intake_hash,
        "p27_operator_runtime_activation_request_intake_valid_review_only": True,
        "operator_runtime_activation_request_validated_review_only": True,
        "operator_runtime_activation_request_is_runtime_authority": False,
        "separate_final_operator_runtime_activation_gate_required": True,
        "runtime_enablement_performed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    controls = build_final_operator_runtime_activation_gate_review_controls_template(
        p27_validator_report_sha256=p27_report_hash,
        p27_intake_sha256=p27_intake_hash,
    )
    controls.update({
        "operator_id": "operator-thomas",
        "ticket_or_signature": "TICKET-P28-VALID-001",
        "reviewed_at_utc": "2026-07-08T00:00:00Z",
    })
    return p27_summary, p27_report, p27_intake, controls


def test_p28_waits_when_p27_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_final_operator_runtime_activation_gate_review_report(root=tmp_path)
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert "P28_SOURCE_P27_SUMMARY_MISSING" in report["waiting_reasons"]
    assert "P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_CONTROLS_MISSING" in report["waiting_reasons"]
    assert report["live_scaled_execution_enabled"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["secret_value_accessed"] is False


def test_p28_validates_final_gate_review_only(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    p27_summary, p27_report, p27_intake, controls = _valid_sources()
    report = build_final_operator_runtime_activation_gate_review_report(
        root=tmp_path,
        p27_summary=p27_summary,
        p27_report=p27_report,
        p27_intake=p27_intake,
        p28_controls=controls,
    )
    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert report["p28_final_operator_runtime_activation_gate_review_valid_review_only"] is True
    assert report["final_operator_runtime_activation_gate_ready_review_only"] is True
    assert report["final_operator_runtime_activation_gate_review_is_runtime_authority"] is False
    assert report["separate_operator_runtime_activation_execution_required_after_this_review"] is True
    assert report["live_scaled_execution_enabled"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["runtime_enablement_performed"] is False
    assert report["operator_runtime_activation_performed"] is False
    assert report["secret_value_accessed"] is False


def test_p28_persists_summary_template_packet_registry_and_negative_results(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    latest = tmp_path / "storage" / "latest"
    p27_summary, p27_report, p27_intake, controls = _valid_sources()
    atomic_write_json(latest / "p27_operator_runtime_activation_request_intake_validator_summary.json", p27_summary)
    atomic_write_json(latest / "p27_operator_runtime_activation_request_intake_validator_report.json", p27_report)
    atomic_write_json(latest / "p27_operator_runtime_activation_request_intake.json", p27_intake)
    atomic_write_json(latest / "p28_final_operator_runtime_activation_gate_review_controls.json", controls)
    report = persist_final_operator_runtime_activation_gate_review(load_config(tmp_path))
    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert (latest / "p28_final_operator_runtime_activation_gate_review_report.json").exists()
    assert (latest / "p28_final_operator_runtime_activation_gate_review_summary.json").exists()
    assert (latest / "p28_final_operator_runtime_activation_gate_review_controls_TEMPLATE.json").exists()
    assert (latest / "p28_final_operator_runtime_activation_gate_review_packet.json").exists()
    assert (latest / "p28_final_operator_runtime_activation_gate_review_negative_fixture_results.json").exists()
    assert (latest / "p28_final_operator_runtime_activation_gate_review_registry_record.json").exists()
    summary = read_json(latest / "p28_final_operator_runtime_activation_gate_review_summary.json")
    template = read_json(latest / "p28_final_operator_runtime_activation_gate_review_controls_TEMPLATE.json")
    packet = read_json(latest / "p28_final_operator_runtime_activation_gate_review_packet.json")
    negative = read_json(latest / "p28_final_operator_runtime_activation_gate_review_negative_fixture_results.json")
    registry = read_json(latest / "p28_final_operator_runtime_activation_gate_review_registry_record.json")
    assert summary["p28_final_operator_runtime_activation_gate_review_valid_review_only"] is True
    assert template["exact_final_operator_runtime_activation_gate_review_phrase"] == P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_EXACT_PHRASE
    assert packet["runtime_authority"] is False
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert registry["live_scaled_execution_enabled"] is False


def test_p28_blocks_wrong_phrase_scheduler_endpoint_secret_runtime_authority(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    p27_summary, p27_report, p27_intake, controls = _valid_sources()
    wrong_phrase = build_final_operator_runtime_activation_gate_review_report(
        root=tmp_path,
        p27_summary=p27_summary,
        p27_report=p27_report,
        p27_intake=p27_intake,
        p28_controls={**controls, "exact_final_operator_runtime_activation_gate_review_phrase": "WRONG"},
    )
    assert wrong_phrase["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P28_CONTROLS_EXACT_PHRASE_INVALID" in wrong_phrase["block_reasons"]

    scheduler = build_final_operator_runtime_activation_gate_review_report(
        root=tmp_path,
        p27_summary=p27_summary,
        p27_report=p27_report,
        p27_intake=p27_intake,
        p28_controls={**controls, "runtime_scheduler_enabled": True},
    )
    assert scheduler["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P28_UNSAFE_TRUTHY_FLAG_FOUND" in scheduler["block_reasons"]

    endpoint = build_final_operator_runtime_activation_gate_review_report(
        root=tmp_path,
        p27_summary=p27_summary,
        p27_report=p27_report,
        p27_intake=p27_intake,
        p28_controls={**controls, "order_endpoint_called": True},
    )
    assert endpoint["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P28_UNSAFE_TRUTHY_FLAG_FOUND" in endpoint["block_reasons"]

    secret = build_final_operator_runtime_activation_gate_review_report(
        root=tmp_path,
        p27_summary=p27_summary,
        p27_report=p27_report,
        p27_intake=p27_intake,
        p28_controls={**controls, "operator_note": "BINANCE_API_SECRET=leaked"},
    )
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P28_SECRET_VALUE_PATTERN_FOUND" in secret["block_reasons"]

    authority = build_final_operator_runtime_activation_gate_review_report(
        root=tmp_path,
        p27_summary=p27_summary,
        p27_report=p27_report,
        p27_intake=p27_intake,
        p28_controls={**controls, "review_packet_is_runtime_authority": True},
    )
    assert authority["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P28_UNSAFE_TRUTHY_FLAG_FOUND" in authority["block_reasons"]


def test_p28_blocks_missing_fresh_validation_kill_switch_cap_and_reconciliation_controls(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    p27_summary, p27_report, p27_intake, controls = _valid_sources()
    missing_fresh = build_final_operator_runtime_activation_gate_review_report(
        root=tmp_path,
        p27_summary=p27_summary,
        p27_report=p27_report,
        p27_intake=p27_intake,
        p28_controls={**controls, "fresh_validation_controls": {**controls["fresh_validation_controls"], "fresh_market_data_before_activation": False}},
    )
    assert missing_fresh["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert any(reason.startswith("P28_FRESH_VALIDATION_CONTROLS_MISSING") for reason in missing_fresh["block_reasons"])

    missing_kill = build_final_operator_runtime_activation_gate_review_report(
        root=tmp_path,
        p27_summary=p27_summary,
        p27_report=p27_report,
        p27_intake=p27_intake,
        p28_controls={**controls, "kill_switch_controls": {**controls["kill_switch_controls"], "operator_manual_kill_switch_checked": False}},
    )
    assert missing_kill["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert any(reason.startswith("P28_KILL_SWITCH_CONTROLS_MISSING") for reason in missing_kill["block_reasons"])

    missing_cap = build_final_operator_runtime_activation_gate_review_report(
        root=tmp_path,
        p27_summary=p27_summary,
        p27_report=p27_report,
        p27_intake=p27_intake,
        p28_controls={**controls, "cap_controls": {**controls["cap_controls"], "max_leverage_checked": False}},
    )
    assert missing_cap["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert any(reason.startswith("P28_CAP_CONTROLS_MISSING") for reason in missing_cap["block_reasons"])

    missing_recon = build_final_operator_runtime_activation_gate_review_report(
        root=tmp_path,
        p27_summary=p27_summary,
        p27_report=p27_report,
        p27_intake=p27_intake,
        p28_controls={**controls, "runtime_loop_controls": {**controls["runtime_loop_controls"], "reconciliation_required": False}},
    )
    assert missing_recon["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert any(reason.startswith("P28_RUNTIME_LOOP_CONTROLS_MISSING") for reason in missing_recon["block_reasons"])


def test_p28_negative_fixtures_are_fail_closed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    negative = build_p28_negative_fixture_results(root=tmp_path)
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert negative["fixture_results"]["scheduler_enabled"]["blocked_or_waiting"] is True
    assert negative["fixture_results"]["endpoint_called"]["blocked_or_waiting"] is True
    assert negative["fixture_results"]["secret_pattern_found"]["blocked_or_waiting"] is True

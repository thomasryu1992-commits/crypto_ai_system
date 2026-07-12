from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.final_runtime_enablement_boundary_review_packet import (
    P25_FINAL_RUNTIME_REVIEW_EXACT_PHRASE,
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALID_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_final_runtime_enablement_boundary_review_packet_report,
    build_final_runtime_enablement_review_controls_template,
    build_p25_negative_fixture_results,
    persist_final_runtime_enablement_boundary_review_packet,
)
from crypto_ai_system.utils.audit import sha256_json


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  name: tmp-crypto-ai-system\n  version: test\n"
        "storage:\n  latest_dir: storage/latest\n  registry_dir: storage/registries\n",
        encoding="utf-8",
    )


def _p24_hash() -> str:
    return "a" * 64


def _template_hash() -> str:
    return "c" * 64


def _p24_intake() -> dict:
    return {
        "request_type": "limited_live_scaled_runtime_enablement_request_intake_review_only",
        "operator_id": "operator-thomas",
        "ticket_or_signature": "TICKET-P24-VALID-001",
        "request_executes_runtime": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _intake_hash() -> str:
    return sha256_json(_p24_intake())


def _p24_summary() -> dict:
    return {
        "status": "P24_RUNTIME_ENABLEMENT_REQUEST_INTAKE_VALIDATOR_VALID_REVIEW_ONLY",
        "p24_runtime_enablement_request_intake_validator_sha256": _p24_hash(),
        "p24_runtime_enablement_request_intake_sha256": _intake_hash(),
        "p24_runtime_enablement_request_intake_valid_review_only": True,
        "runtime_enablement_request_validated_review_only": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _p24_report() -> dict:
    return {
        "status": "P24_RUNTIME_ENABLEMENT_REQUEST_INTAKE_VALIDATOR_VALID_REVIEW_ONLY",
        "p24_runtime_enablement_request_intake_validator_sha256": _p24_hash(),
        "p24_runtime_enablement_request_intake_sha256": _intake_hash(),
        "p24_runtime_enablement_request_intake_valid_review_only": True,
        "runtime_enablement_request_validated_review_only": True,
        "runtime_enablement_request_is_runtime_authority": False,
        "separate_final_runtime_boundary_required": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _p24_template() -> dict:
    return {
        "request_type": "limited_live_scaled_runtime_enablement_request_intake_review_only",
        "p24_runtime_enablement_request_intake_template_sha256": _template_hash(),
        "runtime_enablement_performed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _valid_controls() -> dict:
    controls = build_final_runtime_enablement_review_controls_template(
        p24_validator_sha256=_p24_hash(),
        p24_intake_sha256=_intake_hash(),
    )
    controls.update({
        "operator_id": "operator-thomas",
        "ticket_or_signature": "TICKET-P25-VALID-001",
        "requested_at_utc": "2026-07-08T00:00:00Z",
    })
    return controls


def test_p25_waits_when_p24_or_controls_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_final_runtime_enablement_boundary_review_packet_report(root=tmp_path)
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert "P25_SOURCE_P24_SUMMARY_MISSING" in report["waiting_reasons"]
    assert "P25_FINAL_RUNTIME_REVIEW_CONTROLS_MISSING" in report["waiting_reasons"]
    assert report["live_scaled_execution_enabled"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["secret_value_accessed"] is False


def test_p25_validates_final_review_packet_review_only(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_final_runtime_enablement_boundary_review_packet_report(
        root=tmp_path,
        p24_summary=_p24_summary(),
        p24_report=_p24_report(),
        p24_template=_p24_template(),
        p24_intake=_p24_intake(),
        p25_controls=_valid_controls(),
    )
    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert report["p25_final_runtime_enablement_boundary_review_packet_valid_review_only"] is True
    assert report["fresh_validation_requirements_bound_review_only"] is True
    assert report["kill_switch_requirements_bound_review_only"] is True
    assert report["caps_requirements_bound_review_only"] is True
    assert report["scheduler_dry_run_requirements_bound_review_only"] is True
    assert report["daily_incident_reporting_requirements_bound_review_only"] is True
    assert report["final_review_packet_is_runtime_authority"] is False
    assert report["separate_operator_runtime_activation_required_after_this_packet"] is True
    assert report["live_scaled_execution_enabled"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["runtime_enablement_performed"] is False
    assert report["secret_value_accessed"] is False


def test_p25_persists_summary_template_packet_registry_and_negative_results(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    latest = tmp_path / "storage" / "latest"
    atomic_write_json(latest / "p24_runtime_enablement_request_intake_validator_summary.json", _p24_summary())
    atomic_write_json(latest / "p24_runtime_enablement_request_intake_validator_report.json", _p24_report())
    atomic_write_json(latest / "p24_runtime_enablement_request_intake_TEMPLATE.json", _p24_template())
    atomic_write_json(latest / "p24_runtime_enablement_request_intake.json", _p24_intake())
    atomic_write_json(latest / "p25_final_runtime_enablement_boundary_review_controls.json", _valid_controls())
    report = persist_final_runtime_enablement_boundary_review_packet(load_config(tmp_path))
    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert (latest / "p25_final_runtime_enablement_boundary_review_packet_report.json").exists()
    assert (latest / "p25_final_runtime_enablement_boundary_review_packet_summary.json").exists()
    assert (latest / "p25_final_runtime_enablement_boundary_review_controls_TEMPLATE.json").exists()
    assert (latest / "p25_final_runtime_enablement_boundary_review_packet.json").exists()
    assert (latest / "p25_final_runtime_enablement_boundary_review_packet_negative_fixture_results.json").exists()
    assert (latest / "p25_final_runtime_enablement_boundary_review_packet_registry_record.json").exists()
    summary = read_json(latest / "p25_final_runtime_enablement_boundary_review_packet_summary.json")
    template = read_json(latest / "p25_final_runtime_enablement_boundary_review_controls_TEMPLATE.json")
    packet = read_json(latest / "p25_final_runtime_enablement_boundary_review_packet.json")
    negative = read_json(latest / "p25_final_runtime_enablement_boundary_review_packet_negative_fixture_results.json")
    registry = read_json(latest / "p25_final_runtime_enablement_boundary_review_packet_registry_record.json")
    assert summary["p25_final_runtime_enablement_boundary_review_packet_ready_review_only"] is True
    assert summary["live_scaled_execution_enabled"] is False
    assert template["exact_final_runtime_review_phrase"] == P25_FINAL_RUNTIME_REVIEW_EXACT_PHRASE
    assert template["runtime_enablement_performed"] is False
    assert packet["packet_is_runtime_authority"] is False
    assert packet["runtime_enablement_performed"] is False
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert registry["live_scaled_execution_enabled"] is False


def test_p25_blocks_hash_mismatch_fresh_validation_kill_switch_and_caps(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    mismatch = build_final_runtime_enablement_boundary_review_packet_report(
        root=tmp_path,
        p24_summary=_p24_summary(),
        p24_report=_p24_report(),
        p24_template=_p24_template(),
        p24_intake=_p24_intake(),
        p25_controls={**_valid_controls(), "source_p24_runtime_enablement_request_intake_validator_sha256": "d" * 64},
    )
    assert mismatch["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P25_CONTROLS_P24_VALIDATOR_HASH_MISMATCH" in mismatch["block_reasons"]

    fresh_missing_controls = _valid_controls()
    fresh_missing_controls["fresh_validation_checklist"] = {**fresh_missing_controls["fresh_validation_checklist"], "signal_qa_required": False}
    fresh_missing = build_final_runtime_enablement_boundary_review_packet_report(
        root=tmp_path,
        p24_summary=_p24_summary(),
        p24_report=_p24_report(),
        p24_template=_p24_template(),
        p24_intake=_p24_intake(),
        p25_controls=fresh_missing_controls,
    )
    assert fresh_missing["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P25_REQUIRED_FRESH_VALIDATION_MISSING_SIGNAL_QA_REQUIRED" in fresh_missing["block_reasons"]

    kill_missing_controls = _valid_controls()
    kill_missing_controls["kill_switch_checklist"] = {**kill_missing_controls["kill_switch_checklist"], "operator_manual_kill_switch_required": False}
    kill_missing = build_final_runtime_enablement_boundary_review_packet_report(
        root=tmp_path,
        p24_summary=_p24_summary(),
        p24_report=_p24_report(),
        p24_template=_p24_template(),
        p24_intake=_p24_intake(),
        p25_controls=kill_missing_controls,
    )
    assert kill_missing["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P25_REQUIRED_KILL_SWITCH_MISSING_OPERATOR_MANUAL_KILL_SWITCH_REQUIRED" in kill_missing["block_reasons"]

    cap_high_controls = _valid_controls()
    cap_high_controls["cap_policy"] = {**cap_high_controls["cap_policy"], "fixed_max_notional_usdt": 999.0}
    cap_high = build_final_runtime_enablement_boundary_review_packet_report(
        root=tmp_path,
        p24_summary=_p24_summary(),
        p24_report=_p24_report(),
        p24_template=_p24_template(),
        p24_intake=_p24_intake(),
        p25_controls=cap_high_controls,
    )
    assert cap_high["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P25_FIXED_MAX_NOTIONAL_CAP_TOO_HIGH" in cap_high["block_reasons"]


def test_p25_blocks_scheduler_endpoint_secret_runtime_authority_and_mutation(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    for field in ("runtime_scheduler_enabled", "order_endpoint_called", "runtime_settings_mutated"):
        report = build_final_runtime_enablement_boundary_review_packet_report(
            root=tmp_path,
            p24_summary=_p24_summary(),
            p24_report=_p24_report(),
            p24_template=_p24_template(),
            p24_intake=_p24_intake(),
            p25_controls={**_valid_controls(), field: True},
        )
        assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
        assert "P25_UNSAFE_TRUTHY_FLAG_FOUND" in report["block_reasons"]
        assert report["live_scaled_execution_enabled"] is False

    authority = build_final_runtime_enablement_boundary_review_packet_report(
        root=tmp_path,
        p24_summary=_p24_summary(),
        p24_report=_p24_report(),
        p24_template=_p24_template(),
        p24_intake=_p24_intake(),
        p25_controls={**_valid_controls(), "packet_is_runtime_authority": True},
    )
    assert authority["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P25_CONTROLS_RUNTIME_AUTHORITY_CLAIMED" in authority["block_reasons"]

    secret = build_final_runtime_enablement_boundary_review_packet_report(
        root=tmp_path,
        p24_summary=_p24_summary(),
        p24_report=_p24_report(),
        p24_template=_p24_template(),
        p24_intake=_p24_intake(),
        p25_controls={**_valid_controls(), "operator_note": "BINANCE_API_SECRET=leaked"},
    )
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P25_SECRET_VALUE_PATTERN_FOUND" in secret["block_reasons"]


def test_p25_negative_fixtures_fail_closed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    results = build_p25_negative_fixture_results(tmp_path)
    assert results["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert results["fixture_results"]["missing_controls"]["waiting"] is True
    assert results["fixture_results"]["scheduler_enabled"]["blocked"] is True
    assert results["fixture_results"]["endpoint_called"]["blocked"] is True
    assert results["fixture_results"]["secret_pattern_found"]["blocked"] is True
    assert results["fixture_results"]["runtime_mutation_requested"]["blocked"] is True

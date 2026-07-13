from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_accepted_release_candidate_handoff import P23_RUNTIME_ENABLEMENT_REQUEST_EXACT_PHRASE
from crypto_ai_system.execution.runtime_enablement_request_intake_validator import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALID_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_p24_negative_fixture_results,
    build_runtime_enablement_request_intake_template,
    build_runtime_enablement_request_intake_validator_report,
    persist_runtime_enablement_request_intake_validator,
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


def _p23_hash() -> str:
    return "a" * 64


def _template_hash() -> str:
    return "b" * 64


def _p23_summary() -> dict:
    return {
        "status": "P23_OPERATOR_ACCEPTED_RELEASE_CANDIDATE_HANDOFF_READY_REVIEW_ONLY",
        "p23_operator_accepted_release_candidate_handoff_sha256": _p23_hash(),
        "p23_operator_accepted_release_candidate_handoff_valid_review_only": True,
        "operator_release_candidate_handoff_ready_review_only": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _p23_report() -> dict:
    return {
        "status": "P23_OPERATOR_ACCEPTED_RELEASE_CANDIDATE_HANDOFF_READY_REVIEW_ONLY",
        "p23_operator_accepted_release_candidate_handoff_sha256": _p23_hash(),
        "p23_operator_accepted_release_candidate_handoff_valid_review_only": True,
        "operator_release_candidate_handoff_ready_review_only": True,
        "handoff_is_runtime_authority": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _p23_template() -> dict:
    return {
        "request_type": "limited_live_scaled_runtime_enablement_request_template_review_only",
        "exact_runtime_enablement_request_phrase": P23_RUNTIME_ENABLEMENT_REQUEST_EXACT_PHRASE,
        "p23_runtime_enablement_request_template_sha256": _template_hash(),
        "template_only": True,
        "review_only": True,
        "runtime_enablement_performed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _valid_intake() -> dict:
    intake = build_runtime_enablement_request_intake_template(
        p23_handoff_sha256=_p23_hash(),
        p23_template_sha256=_template_hash(),
    )
    intake.update({"operator_id": "operator-thomas", "ticket_or_signature": "TICKET-P24-001", "requested_at_utc": "2026-07-08T00:00:00Z"})
    return intake


def test_p24_waits_when_p23_or_intake_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_runtime_enablement_request_intake_validator_report(root=tmp_path)
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert "P24_SOURCE_P23_SUMMARY_MISSING" in report["waiting_reasons"]
    assert "P24_RUNTIME_ENABLEMENT_REQUEST_INTAKE_MISSING" in report["waiting_reasons"]
    assert report["live_scaled_execution_enabled"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["secret_value_accessed"] is False


def test_p24_validates_runtime_enablement_intake_review_only(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_runtime_enablement_request_intake_validator_report(
        root=tmp_path,
        p23_summary=_p23_summary(),
        p23_report=_p23_report(),
        p23_template=_p23_template(),
        p24_intake=_valid_intake(),
    )
    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert report["p24_runtime_enablement_request_intake_valid_review_only"] is True
    assert report["runtime_enablement_request_validated_review_only"] is True
    assert report["runtime_enablement_request_is_runtime_authority"] is False
    assert report["separate_final_runtime_boundary_required"] is True
    assert report["live_scaled_execution_enabled"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["runtime_enablement_performed"] is False
    assert report["secret_value_accessed"] is False


def test_p24_persists_summary_template_registry_and_negative_fixture_results(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    latest = tmp_path / "storage" / "latest"
    atomic_write_json(latest / "p23_operator_accepted_release_candidate_handoff_summary.json", _p23_summary())
    atomic_write_json(latest / "p23_operator_accepted_release_candidate_handoff_report.json", _p23_report())
    atomic_write_json(latest / "p23_runtime_enablement_request_TEMPLATE.json", _p23_template())
    atomic_write_json(latest / "p24_runtime_enablement_request_intake.json", _valid_intake())
    report = persist_runtime_enablement_request_intake_validator(load_config(tmp_path))
    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert (latest / "p24_runtime_enablement_request_intake_validator_report.json").exists()
    assert (latest / "p24_runtime_enablement_request_intake_validator_summary.json").exists()
    assert (latest / "p24_runtime_enablement_request_intake_TEMPLATE.json").exists()
    assert (latest / "p24_runtime_enablement_request_intake_validator_negative_fixture_results.json").exists()
    assert (latest / "p24_runtime_enablement_request_intake_validator_registry_record.json").exists()
    summary = read_json(latest / "p24_runtime_enablement_request_intake_validator_summary.json")
    template = read_json(latest / "p24_runtime_enablement_request_intake_TEMPLATE.json")
    negative = read_json(latest / "p24_runtime_enablement_request_intake_validator_negative_fixture_results.json")
    registry = read_json(latest / "p24_runtime_enablement_request_intake_validator_registry_record.json")
    assert summary["runtime_enablement_request_validated_review_only"] is True
    assert summary["live_scaled_execution_enabled"] is False
    assert template["exact_runtime_enablement_request_phrase"] == P23_RUNTIME_ENABLEMENT_REQUEST_EXACT_PHRASE
    assert template["runtime_enablement_performed"] is False
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert registry["live_scaled_execution_enabled"] is False


def test_p24_blocks_hash_mismatch_runtime_authority_and_missing_ack(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    mismatch = build_runtime_enablement_request_intake_validator_report(
        root=tmp_path,
        p23_summary=_p23_summary(),
        p23_report=_p23_report(),
        p23_template=_p23_template(),
        p24_intake={**_valid_intake(), "source_p23_operator_accepted_release_candidate_handoff_sha256": "c" * 64},
    )
    assert mismatch["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P24_INTAKE_P23_HANDOFF_HASH_MISMATCH" in mismatch["block_reasons"]

    authority = build_runtime_enablement_request_intake_validator_report(
        root=tmp_path,
        p23_summary=_p23_summary(),
        p23_report=_p23_report(),
        p23_template=_p23_template(),
        p24_intake={**_valid_intake(), "intake_is_runtime_authority": True},
    )
    assert authority["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P24_INTAKE_RUNTIME_AUTHORITY_CLAIMED" in authority["block_reasons"]

    missing_ack = build_runtime_enablement_request_intake_validator_report(
        root=tmp_path,
        p23_summary=_p23_summary(),
        p23_report=_p23_report(),
        p23_template=_p23_template(),
        p24_intake={**_valid_intake(), "kill_switch_acknowledged": False},
    )
    assert missing_ack["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P24_REQUIRED_ACK_MISSING_KILL_SWITCH_ACKNOWLEDGED" in missing_ack["block_reasons"]


def test_p24_blocks_scheduler_endpoint_secret_and_runtime_mutation(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    for field in ("runtime_scheduler_enabled", "order_endpoint_called", "runtime_settings_mutated"):
        report = build_runtime_enablement_request_intake_validator_report(
            root=tmp_path,
            p23_summary=_p23_summary(),
            p23_report=_p23_report(),
            p23_template=_p23_template(),
            p24_intake={**_valid_intake(), field: True},
        )
        assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
        assert "P24_UNSAFE_TRUTHY_FLAG_FOUND" in report["block_reasons"]
        assert report["live_scaled_execution_enabled"] is False

    secret = build_runtime_enablement_request_intake_validator_report(
        root=tmp_path,
        p23_summary=_p23_summary(),
        p23_report=_p23_report(),
        p23_template=_p23_template(),
        p24_intake={**_valid_intake(), "operator_note": "BINANCE_API_SECRET=leaked"},
    )
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P24_SECRET_VALUE_PATTERN_FOUND" in secret["block_reasons"]


def test_p24_negative_fixtures_fail_closed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    results = build_p24_negative_fixture_results(tmp_path)
    assert results["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert results["fixture_results"]["scheduler_enablement_requested"]["blocked"] is True
    assert results["fixture_results"]["order_submission_requested"]["blocked"] is True
    assert results["fixture_results"]["endpoint_called"]["blocked"] is True
    assert results["fixture_results"]["secret_pattern_found"]["blocked"] is True
    assert results["fixture_results"]["missing_intake"]["waiting"] is True

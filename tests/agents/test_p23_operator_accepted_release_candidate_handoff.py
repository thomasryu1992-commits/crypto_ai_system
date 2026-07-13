from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_accepted_release_candidate_handoff import (
    P23_RUNTIME_ENABLEMENT_REQUEST_EXACT_PHRASE,
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALID_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_operator_accepted_release_candidate_handoff_report,
    build_p23_negative_fixture_results,
    build_runtime_enablement_request_template,
    persist_operator_accepted_release_candidate_handoff,
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


def _p22_hash() -> str:
    return "a" * 64


def _intake_hash() -> str:
    return "b" * 64


def _p22_summary() -> dict:
    return {
        "status": "P22_OPERATOR_RELEASE_CANDIDATE_ACCEPTANCE_REVIEW_VALID_REVIEW_ONLY",
        "p22_operator_release_candidate_acceptance_review_sha256": _p22_hash(),
        "p22_operator_release_candidate_acceptance_valid_review_only": True,
        "release_candidate_accepted_review_only": True,
        "operator_acceptance_intake_sha256": _intake_hash(),
        "separate_runtime_enablement_required": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _p22_report() -> dict:
    return {
        "status": "P22_OPERATOR_RELEASE_CANDIDATE_ACCEPTANCE_REVIEW_VALID_REVIEW_ONLY",
        "p22_operator_release_candidate_acceptance_review_sha256": _p22_hash(),
        "p22_operator_release_candidate_acceptance_valid_review_only": True,
        "release_candidate_accepted_review_only": True,
        "operator_acceptance_intake_sha256": _intake_hash(),
        "operator_acceptance_is_runtime_authority": False,
        "separate_runtime_enablement_required": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def test_p23_waits_when_p22_acceptance_is_not_valid(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_operator_accepted_release_candidate_handoff_report(
        root=tmp_path,
        p22_summary={**_p22_summary(), "p22_operator_release_candidate_acceptance_valid_review_only": False},
        p22_report={**_p22_report(), "p22_operator_release_candidate_acceptance_valid_review_only": False},
    )
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert "P23_SOURCE_P22_ACCEPTANCE_NOT_VALID" in report["waiting_reasons"]
    assert report["operator_release_candidate_handoff_ready_review_only"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["secret_value_accessed"] is False


def test_p23_builds_valid_review_only_handoff_and_runtime_request_template(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_operator_accepted_release_candidate_handoff_report(
        root=tmp_path,
        p22_summary=_p22_summary(),
        p22_report=_p22_report(),
    )
    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert report["p23_operator_accepted_release_candidate_handoff_valid_review_only"] is True
    assert report["operator_release_candidate_handoff_ready_review_only"] is True
    assert report["handoff_is_runtime_authority"] is False
    assert report["runtime_enablement_request_template_is_runtime_authority"] is False
    assert report["separate_runtime_enablement_request_required"] is True
    assert report["separate_runtime_enablement_validation_required"] is True
    template = report["runtime_enablement_request_template"]
    assert template["exact_runtime_enablement_request_phrase"] == P23_RUNTIME_ENABLEMENT_REQUEST_EXACT_PHRASE
    assert template["template_only"] is True
    assert template["runtime_enablement_performed"] is False
    assert template["live_scaled_execution_enabled"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["secret_value_accessed"] is False


def test_p23_persists_summary_templates_registry_and_negative_fixture_results(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    latest = tmp_path / "storage" / "latest"
    atomic_write_json(latest / "p22_operator_release_candidate_acceptance_review_summary.json", _p22_summary())
    atomic_write_json(latest / "p22_operator_release_candidate_acceptance_review_report.json", _p22_report())
    report = persist_operator_accepted_release_candidate_handoff(load_config(tmp_path))
    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert (latest / "p23_operator_accepted_release_candidate_handoff_report.json").exists()
    assert (latest / "p23_operator_accepted_release_candidate_handoff_summary.json").exists()
    assert (latest / "p23_runtime_enablement_request_TEMPLATE.json").exists()
    assert (latest / "p23_final_no_runtime_authority_handoff_checklist.json").exists()
    assert (latest / "p23_operator_accepted_release_candidate_handoff_negative_fixture_results.json").exists()
    assert (latest / "p23_operator_accepted_release_candidate_handoff_registry_record.json").exists()
    summary = read_json(latest / "p23_operator_accepted_release_candidate_handoff_summary.json")
    template = read_json(latest / "p23_runtime_enablement_request_TEMPLATE.json")
    checklist = read_json(latest / "p23_final_no_runtime_authority_handoff_checklist.json")
    negative = read_json(latest / "p23_operator_accepted_release_candidate_handoff_negative_fixture_results.json")
    registry = read_json(latest / "p23_operator_accepted_release_candidate_handoff_registry_record.json")
    assert summary["operator_release_candidate_handoff_ready_review_only"] is True
    assert summary["live_scaled_execution_enabled"] is False
    assert template["exact_runtime_enablement_request_phrase"] == P23_RUNTIME_ENABLEMENT_REQUEST_EXACT_PHRASE
    assert checklist["handoff_is_runtime_authority"] is False
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert registry["live_scaled_execution_enabled"] is False


def test_p23_blocks_runtime_authority_claims_and_hash_mismatch(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    blocked = build_operator_accepted_release_candidate_handoff_report(
        root=tmp_path,
        p22_summary=_p22_summary(),
        p22_report={**_p22_report(), "operator_acceptance_is_runtime_authority": True},
    )
    assert blocked["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P23_SOURCE_P22_RUNTIME_AUTHORITY_CLAIMED" in blocked["block_reasons"]
    assert blocked["live_scaled_execution_enabled"] is False

    mismatch = build_operator_accepted_release_candidate_handoff_report(
        root=tmp_path,
        p22_summary=_p22_summary(),
        p22_report={**_p22_report(), "p22_operator_release_candidate_acceptance_review_sha256": "c" * 64},
    )
    assert mismatch["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P23_SOURCE_P22_SUMMARY_REPORT_HASH_MISMATCH" in mismatch["block_reasons"]


def test_p23_runtime_template_is_review_only_and_not_authority() -> None:
    template = build_runtime_enablement_request_template(
        p22_operator_acceptance_review_sha256=_p22_hash(),
        p22_operator_acceptance_intake_sha256=_intake_hash(),
    )
    assert template["template_only"] is True
    assert template["review_only"] is True
    assert template["separate_runtime_boundary_required"] is True
    assert template["runtime_enablement_performed"] is False
    assert template["live_scaled_execution_enabled"] is False
    assert template["live_order_submission_allowed"] is False
    assert template["secret_value_accessed"] is False


def test_p23_negative_fixtures_fail_closed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    results = build_p23_negative_fixture_results(tmp_path)
    assert results["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert results["fixture_results"]["unsafe_runtime_flag"]["blocked"] is True
    assert results["fixture_results"]["runtime_scheduler_enabled"]["blocked"] is True
    assert results["fixture_results"]["secret_pattern_found"]["blocked"] is True
    assert results["fixture_results"]["p22_not_valid"]["waiting"] is True

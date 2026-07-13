from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_release_candidate_acceptance_review import (
    P22_EXACT_ACCEPTANCE_PHRASE,
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALID_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_operator_release_candidate_acceptance_intake_template,
    build_operator_release_candidate_acceptance_review_report,
    build_p22_negative_fixture_results,
    persist_operator_release_candidate_acceptance_review,
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


def _p21_hash() -> str:
    return "a" * 64


def _bundle_hash() -> str:
    return "b" * 64


def _p21_summary() -> dict:
    return {
        "status": "P21_CI_FILLED_EVIDENCE_RELEASE_CANDIDATE_BUNDLE_VALID_REVIEW_ONLY",
        "p21_ci_filled_evidence_release_candidate_bundle_sha256": _p21_hash(),
        "p21_release_candidate_bundle_ready_review_only": True,
        "release_candidate_bundle_path": "storage/latest/p21_release_candidate_bundle_review_only.zip",
        "release_candidate_bundle_content_sha256": _bundle_hash(),
        "separate_operator_acceptance_required": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _p21_report() -> dict:
    return {
        "status": "P21_CI_FILLED_EVIDENCE_RELEASE_CANDIDATE_BUNDLE_VALID_REVIEW_ONLY",
        "p21_ci_filled_evidence_release_candidate_bundle_sha256": _p21_hash(),
        "p21_release_candidate_bundle_ready_review_only": True,
        "release_candidate_bundle_is_runtime_authority": False,
        "separate_operator_acceptance_required": True,
        "separate_runtime_enablement_required": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _valid_intake() -> dict:
    intake = build_operator_release_candidate_acceptance_intake_template(
        p21_release_candidate_bundle_sha256=_p21_hash(),
        release_candidate_bundle_content_sha256=_bundle_hash(),
    )
    intake.update({"operator_id": "operator-thomas", "ticket_or_signature": "OPS-12345-signed"})
    return intake


def test_p22_waits_when_operator_acceptance_intake_is_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_operator_release_candidate_acceptance_review_report(
        root=tmp_path,
        p21_summary=_p21_summary(),
        p21_report=_p21_report(),
        acceptance_intake={},
    )
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert "P22_OPERATOR_ACCEPTANCE_INTAKE_MISSING" in report["waiting_reasons"]
    assert report["release_candidate_accepted_review_only"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["secret_value_accessed"] is False


def test_p22_builds_valid_review_only_operator_acceptance_report(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_operator_release_candidate_acceptance_review_report(
        root=tmp_path,
        p21_summary=_p21_summary(),
        p21_report=_p21_report(),
        acceptance_intake=_valid_intake(),
    )
    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert report["p22_operator_release_candidate_acceptance_valid_review_only"] is True
    assert report["release_candidate_accepted_review_only"] is True
    assert report["operator_acceptance_is_runtime_authority"] is False
    assert report["release_candidate_bundle_is_runtime_authority"] is False
    assert report["separate_runtime_enablement_required"] is True
    assert report["live_scaled_execution_enabled"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["secret_value_accessed"] is False


def test_p22_persists_summary_template_registry_and_negative_fixture_results(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    latest = tmp_path / "storage" / "latest"
    atomic_write_json(latest / "p21_ci_filled_evidence_release_candidate_bundle_summary.json", _p21_summary())
    atomic_write_json(latest / "p21_ci_filled_evidence_release_candidate_bundle_report.json", _p21_report())
    atomic_write_json(latest / "p22_operator_release_candidate_acceptance_intake.json", _valid_intake())
    report = persist_operator_release_candidate_acceptance_review(load_config(tmp_path))
    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert (latest / "p22_operator_release_candidate_acceptance_review_report.json").exists()
    assert (latest / "p22_operator_release_candidate_acceptance_review_summary.json").exists()
    assert (latest / "p22_operator_release_candidate_acceptance_intake_TEMPLATE.json").exists()
    assert (latest / "p22_operator_release_candidate_acceptance_review_negative_fixture_results.json").exists()
    assert (latest / "p22_operator_release_candidate_acceptance_review_registry_record.json").exists()
    summary = read_json(latest / "p22_operator_release_candidate_acceptance_review_summary.json")
    negative = read_json(latest / "p22_operator_release_candidate_acceptance_review_negative_fixture_results.json")
    registry = read_json(latest / "p22_operator_release_candidate_acceptance_review_registry_record.json")
    template = read_json(latest / "p22_operator_release_candidate_acceptance_intake_TEMPLATE.json")
    assert summary["release_candidate_accepted_review_only"] is True
    assert summary["live_scaled_execution_enabled"] is False
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert registry["live_scaled_execution_enabled"] is False
    assert template["exact_acceptance_phrase"] == P22_EXACT_ACCEPTANCE_PHRASE


def test_p22_blocks_runtime_authority_claims_and_hash_mismatch(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_operator_release_candidate_acceptance_review_report(
        root=tmp_path,
        p21_summary=_p21_summary(),
        p21_report=_p21_report(),
        acceptance_intake={**_valid_intake(), "runtime_enablement_requested": True},
    )
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P22_RUNTIME_ENABLEMENT_REQUESTED_MUST_BE_FALSE" in report["block_reasons"]
    assert report["live_scaled_execution_enabled"] is False

    mismatch = build_operator_release_candidate_acceptance_review_report(
        root=tmp_path,
        p21_summary=_p21_summary(),
        p21_report=_p21_report(),
        acceptance_intake={**_valid_intake(), "source_p21_ci_filled_evidence_release_candidate_bundle_sha256": "c" * 64},
    )
    assert mismatch["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P22_P21_HASH_MISMATCH" in mismatch["block_reasons"]


def test_p22_negative_fixtures_fail_closed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    results = build_p22_negative_fixture_results(tmp_path)
    assert results["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert results["fixture_results"]["unsafe_runtime_flag"]["blocked"] is True
    assert results["fixture_results"]["secret_pattern_found"]["blocked"] is True
    assert results["fixture_results"]["missing_acceptance_intake"]["waiting"] is True

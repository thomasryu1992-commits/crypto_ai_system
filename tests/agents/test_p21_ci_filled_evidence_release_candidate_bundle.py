from __future__ import annotations

import zipfile
from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.ci_filled_evidence_release_candidate_bundle import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALID_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_ci_filled_evidence_release_candidate_bundle_report,
    build_p21_negative_fixture_results,
    persist_ci_filled_evidence_release_candidate_bundle,
)
from crypto_ai_system.execution.docker_launcher_evidence_intake import (
    build_docker_build_external_evidence_template,
    build_docker_run_external_evidence_template,
    build_launcher_import_external_evidence_template,
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


def _p18_hash() -> str:
    return "a" * 64


def _p19_hash() -> str:
    return "b" * 64


def _p20_hash() -> str:
    return "c" * 64


def _manifest_hash() -> str:
    return "d" * 64


def _external_evidence() -> tuple[dict, dict, dict]:
    return (
        build_docker_build_external_evidence_template(_p18_hash()),
        build_docker_run_external_evidence_template(_p18_hash()),
        build_launcher_import_external_evidence_template(_p18_hash()),
    )


def _p19_summary() -> dict:
    return {
        "status": "P19_DOCKER_LAUNCHER_EVIDENCE_INTAKE_VALID_REVIEW_ONLY",
        "p19_docker_launcher_evidence_intake_sha256": _p19_hash(),
        "p19_docker_launcher_evidence_intake_valid_review_only": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _p19_report() -> dict:
    docker_build, docker_run, launcher = _external_evidence()
    return {
        "status": "P19_DOCKER_LAUNCHER_EVIDENCE_INTAKE_VALID_REVIEW_ONLY",
        "p19_docker_launcher_evidence_intake_sha256": _p19_hash(),
        "p19_docker_launcher_evidence_intake_valid_review_only": True,
        "source_p18_full_regression_ci_release_gate_sha256": _p18_hash(),
        "docker_build_evidence_sha256": sha256_json(docker_build),
        "docker_run_self_test_evidence_sha256": sha256_json(docker_run),
        "launcher_import_evidence_sha256": sha256_json(launcher),
        "docker_build_evidence_valid_review_only": True,
        "docker_run_self_test_evidence_valid_review_only": True,
        "launcher_import_evidence_valid_review_only": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _p20_manifest() -> dict:
    return {
        "artifact_pack_type": "docker_launcher_external_evidence_template_export_pack",
        "source_p18_full_regression_ci_release_gate_sha256": _p18_hash(),
        "p20_ci_artifact_export_manifest_sha256": _manifest_hash(),
        "artifact_entries": [
            {
                "artifact_id": "docker_build",
                "target_external_evidence_filename": "p19_docker_build_evidence_external.json",
                "must_be_filled_by_external_ci_or_operator": True,
                "must_not_be_filled_by_this_module": True,
            },
            {
                "artifact_id": "docker_run_self_test",
                "target_external_evidence_filename": "p19_docker_run_self_test_evidence_external.json",
                "must_be_filled_by_external_ci_or_operator": True,
                "must_not_be_filled_by_this_module": True,
            },
            {
                "artifact_id": "launcher_import",
                "target_external_evidence_filename": "p19_launcher_import_evidence_external.json",
                "must_be_filled_by_external_ci_or_operator": True,
                "must_not_be_filled_by_this_module": True,
            },
        ],
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _p20_summary() -> dict:
    return {
        "status": "P20_EXTERNAL_EVIDENCE_TEMPLATE_EXPORT_PACK_GENERATED_REVIEW_ONLY",
        "p20_external_evidence_template_export_pack_sha256": _p20_hash(),
        "p20_templates_ready_for_external_ci_fill": True,
        "ci_artifact_export_manifest_sha256": _manifest_hash(),
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _p20_report() -> dict:
    return {
        "status": "P20_EXTERNAL_EVIDENCE_TEMPLATE_EXPORT_PACK_GENERATED_REVIEW_ONLY",
        "p20_external_evidence_template_export_pack_sha256": _p20_hash(),
        "p20_templates_ready_for_external_ci_fill": True,
        "source_p18_full_regression_ci_release_gate_sha256": _p18_hash(),
        "ci_artifact_export_manifest_sha256": _manifest_hash(),
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _valid_report(tmp_path: Path) -> dict:
    docker_build, docker_run, launcher = _external_evidence()
    return build_ci_filled_evidence_release_candidate_bundle_report(
        root=tmp_path,
        p19_summary=_p19_summary(),
        p19_report=_p19_report(),
        p20_summary=_p20_summary(),
        p20_report=_p20_report(),
        p20_manifest=_p20_manifest(),
        docker_build_evidence=docker_build,
        docker_run_evidence=docker_run,
        launcher_import_evidence=launcher,
    )


def test_p21_waits_when_filled_external_evidence_is_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_ci_filled_evidence_release_candidate_bundle_report(
        root=tmp_path,
        p19_summary={**_p19_summary(), "p19_docker_launcher_evidence_intake_valid_review_only": False},
        p19_report=_p19_report(),
        p20_summary=_p20_summary(),
        p20_report=_p20_report(),
        p20_manifest=_p20_manifest(),
    )

    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert "P21_FILLED_EXTERNAL_EVIDENCE_MISSING" in report["waiting_reasons"]
    assert report["p21_release_candidate_bundle_ready_review_only"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["secret_value_accessed"] is False


def test_p21_builds_valid_review_only_release_candidate_bundle_report(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = _valid_report(tmp_path)

    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert report["p21_ci_filled_evidence_valid_review_only"] is True
    assert report["p21_release_candidate_bundle_ready_review_only"] is True
    assert report["release_candidate_bundle_is_runtime_authority"] is False
    assert report["separate_operator_acceptance_required"] is True
    assert report["separate_runtime_enablement_required"] is True
    assert report["live_scaled_execution_enabled"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["secret_value_accessed"] is False
    manifest = report["release_candidate_bundle_manifest"]
    assert manifest["bundle_type"] == "release_candidate_bundle_review_only"
    assert manifest["operator_handoff_instructions"]["not_runtime_authority"] is True


def test_p21_persists_bundle_only_when_filled_evidence_is_valid(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    latest = tmp_path / "storage" / "latest"
    docker_build, docker_run, launcher = _external_evidence()
    atomic_write_json(latest / "p19_docker_launcher_evidence_intake_summary.json", _p19_summary())
    atomic_write_json(latest / "p19_docker_launcher_evidence_intake_report.json", _p19_report())
    atomic_write_json(latest / "p20_external_evidence_template_export_pack_summary.json", _p20_summary())
    atomic_write_json(latest / "p20_external_evidence_template_export_pack_report.json", _p20_report())
    atomic_write_json(latest / "p20_ci_artifact_export_manifest.json", _p20_manifest())
    atomic_write_json(latest / "p19_docker_build_evidence_external.json", docker_build)
    atomic_write_json(latest / "p19_docker_run_self_test_evidence_external.json", docker_run)
    atomic_write_json(latest / "p19_launcher_import_evidence_external.json", launcher)

    report = persist_ci_filled_evidence_release_candidate_bundle(cfg=load_config(tmp_path))

    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert (latest / "p21_release_candidate_bundle_review_only.zip").exists()
    assert (latest / "p21_ci_filled_evidence_release_candidate_bundle_report.json").exists()
    assert (latest / "p21_ci_filled_evidence_release_candidate_bundle_summary.json").exists()
    assert (latest / "p21_ci_filled_evidence_release_candidate_bundle_negative_fixture_results.json").exists()
    assert (latest / "p21_ci_filled_evidence_release_candidate_bundle_registry_record.json").exists()
    summary = read_json(latest / "p21_ci_filled_evidence_release_candidate_bundle_summary.json")
    registry = read_json(latest / "p21_ci_filled_evidence_release_candidate_bundle_registry_record.json")
    negative = read_json(latest / "p21_ci_filled_evidence_release_candidate_bundle_negative_fixture_results.json")
    assert summary["p21_release_candidate_bundle_ready_review_only"] is True
    assert summary["live_scaled_execution_enabled"] is False
    assert registry["live_scaled_execution_enabled"] is False
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    with zipfile.ZipFile(latest / "p21_release_candidate_bundle_review_only.zip") as archive:
        names = set(archive.namelist())
    assert "p21_release_candidate_bundle_manifest.json" in names
    assert "p19_docker_build_evidence_external.json" in names
    assert "p21_ci_filled_evidence_release_candidate_bundle_report.json" in names


def test_p21_blocks_hash_mismatch_secret_endpoint_and_unsafe_flags(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    docker_build, docker_run, launcher = _external_evidence()

    report = build_ci_filled_evidence_release_candidate_bundle_report(
        root=tmp_path,
        p19_summary=_p19_summary(),
        p19_report=_p19_report(),
        p20_summary=_p20_summary(),
        p20_report=_p20_report(),
        p20_manifest=_p20_manifest(),
        docker_build_evidence={**docker_build, "image_digest_sha256": "9" * 64},
        docker_run_evidence=docker_run,
        launcher_import_evidence=launcher,
    )
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P21_DOCKER_BUILD_EVIDENCE_HASH_MISMATCH" in report["block_reasons"]

    report = build_ci_filled_evidence_release_candidate_bundle_report(
        root=tmp_path,
        p19_summary=_p19_summary(),
        p19_report=_p19_report(),
        p20_summary=_p20_summary(),
        p20_report=_p20_report(),
        p20_manifest=_p20_manifest(),
        docker_build_evidence={**docker_build, "stdout_excerpt": "BINANCE_API_SECRET=leaked"},
        docker_run_evidence=docker_run,
        launcher_import_evidence=launcher,
    )
    assert "P21_SECRET_VALUE_PATTERN_FOUND" in report["block_reasons"]

    report = build_ci_filled_evidence_release_candidate_bundle_report(
        root=tmp_path,
        p19_summary=_p19_summary(),
        p19_report=_p19_report(),
        p20_summary=_p20_summary(),
        p20_report=_p20_report(),
        p20_manifest=_p20_manifest(),
        docker_build_evidence=docker_build,
        docker_run_evidence={**docker_run, "order_endpoint_called": True},
        launcher_import_evidence=launcher,
    )
    assert "P21_UNSAFE_TRUTHY_FLAG_FOUND" in report["block_reasons"]

    report = build_ci_filled_evidence_release_candidate_bundle_report(
        root=tmp_path,
        p19_summary={**_p19_summary(), "live_scaled_execution_enabled": True},
        p19_report=_p19_report(),
        p20_summary=_p20_summary(),
        p20_report=_p20_report(),
        p20_manifest=_p20_manifest(),
        docker_build_evidence=docker_build,
        docker_run_evidence=docker_run,
        launcher_import_evidence=launcher,
    )
    assert "P21_UNSAFE_TRUTHY_FLAG_FOUND" in report["block_reasons"]


def test_p21_negative_fixture_results_fail_closed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    results = build_p21_negative_fixture_results(root=tmp_path)

    assert results["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert set(results["fixture_results"]) == {
        "missing_p20_summary",
        "p20_blocked",
        "missing_p19_summary",
        "p19_not_valid",
        "missing_filled_evidence",
        "evidence_hash_mismatch",
        "p18_hash_mismatch",
        "secret_pattern_found",
        "endpoint_called",
        "unsafe_runtime_flag",
        "manifest_allows_module_fill",
    }
    for result in results["fixture_results"].values():
        assert result["blocked_or_waiting"] is True
        assert result["live_scaled_execution_enabled"] is False
        assert result["live_order_submission_allowed"] is False
        assert result["runtime_scheduler_enabled"] is False
        assert result["secret_value_accessed"] is False

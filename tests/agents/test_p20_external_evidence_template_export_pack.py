from __future__ import annotations

import zipfile
from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.external_evidence_template_export_pack import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY,
    build_external_evidence_template_export_pack_report,
    build_p20_external_evidence_templates,
    build_p20_negative_fixture_results,
    persist_external_evidence_template_export_pack,
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


def _p18_hash() -> str:
    return "a" * 64


def _p19_hash() -> str:
    return "c" * 64


def _p18_summary() -> dict:
    return {
        "status": "P18_FULL_REGRESSION_CI_RELEASE_GATE_HARDENED_REVIEW_ONLY",
        "p18_full_regression_ci_release_gate_sha256": _p18_hash(),
        "p18_full_regression_ci_release_gate_summary_sha256": "b" * 64,
        "p18_ci_release_gate_hardened_review_only": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _p19_summary() -> dict:
    return {
        "status": "P19_DOCKER_LAUNCHER_EVIDENCE_INTAKE_WAITING_REVIEW_ONLY",
        "p19_docker_launcher_evidence_intake_sha256": _p19_hash(),
        "p19_docker_launcher_evidence_intake_valid_review_only": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _p19_report() -> dict:
    return {
        "status": "P19_DOCKER_LAUNCHER_EVIDENCE_INTAKE_WAITING_REVIEW_ONLY",
        "p19_docker_launcher_evidence_intake_sha256": _p19_hash(),
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def test_p20_generates_safe_external_evidence_templates(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_external_evidence_template_export_pack_report(
        root=tmp_path,
        p18_summary=_p18_summary(),
        p19_summary=_p19_summary(),
        p19_report=_p19_report(),
    )

    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert report["p20_templates_ready_for_external_ci_fill"] is True
    assert report["template_count"] == 3
    assert report["target_external_evidence_files"] == [
        "p19_docker_build_evidence_external.json",
        "p19_docker_run_self_test_evidence_external.json",
        "p19_launcher_import_evidence_external.json",
    ]
    assert report["live_scaled_execution_enabled"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["secret_value_accessed"] is False


def test_p20_templates_reuse_p18_hash_and_are_not_execution_evidence(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    templates = build_p20_external_evidence_templates(_p18_hash())

    for template in templates.values():
        assert template["source_p18_full_regression_ci_release_gate_sha256"] == _p18_hash()
        assert template["performed_by_this_module"] is False
        assert template["order_endpoint_called"] is False
        assert template["http_request_sent"] is False
        assert template["secret_value_accessed"] is False
        assert template["secret_value_logged"] is False


def test_p20_persists_templates_manifest_zip_summary_registry_and_negative_fixtures(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    latest = tmp_path / "storage" / "latest"
    atomic_write_json(latest / "p18_full_regression_ci_release_gate_summary.json", _p18_summary())
    atomic_write_json(latest / "p19_docker_launcher_evidence_intake_summary.json", _p19_summary())
    atomic_write_json(latest / "p19_docker_launcher_evidence_intake_report.json", _p19_report())
    cfg = load_config(tmp_path)

    report = persist_external_evidence_template_export_pack(cfg=cfg)

    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert (latest / "p19_docker_build_evidence_external_TEMPLATE.json").exists()
    assert (latest / "p19_docker_run_self_test_evidence_external_TEMPLATE.json").exists()
    assert (latest / "p19_launcher_import_evidence_external_TEMPLATE.json").exists()
    assert (latest / "p20_ci_artifact_export_manifest.json").exists()
    assert (latest / "p20_ci_artifact_export_pack_review_only.zip").exists()
    saved = read_json(latest / "p20_external_evidence_template_export_pack_report.json")
    summary = read_json(latest / "p20_external_evidence_template_export_pack_summary.json")
    registry = read_json(latest / "p20_external_evidence_template_export_pack_registry_record.json")
    negative = read_json(latest / "p20_external_evidence_template_export_pack_negative_fixture_results.json")
    assert saved["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert summary["p20_templates_ready_for_external_ci_fill"] is True
    assert registry["live_scaled_execution_enabled"] is False
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    with zipfile.ZipFile(latest / "p20_ci_artifact_export_pack_review_only.zip") as archive:
        names = set(archive.namelist())
    assert "p20_ci_artifact_export_manifest.json" in names
    assert "p19_docker_build_evidence_external_TEMPLATE.json" in names


def test_p20_blocks_missing_sources_unsafe_flags_and_secret_patterns(tmp_path: Path) -> None:
    _write_min_project(tmp_path)

    report = build_external_evidence_template_export_pack_report(
        root=tmp_path,
        p18_summary={},
        p19_summary=_p19_summary(),
    )
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P20_SOURCE_P18_SUMMARY_MISSING" in report["block_reasons"]

    report = build_external_evidence_template_export_pack_report(
        root=tmp_path,
        p18_summary=_p18_summary(),
        p19_summary={},
    )
    assert "P20_SOURCE_P19_SUMMARY_MISSING" in report["block_reasons"]

    report = build_external_evidence_template_export_pack_report(
        root=tmp_path,
        p18_summary={**_p18_summary(), "live_scaled_execution_enabled": True},
        p19_summary=_p19_summary(),
    )
    assert "P20_UNSAFE_TRUTHY_FLAG_FOUND" in report["block_reasons"]

    report = build_external_evidence_template_export_pack_report(
        root=tmp_path,
        p18_summary=_p18_summary(),
        p19_summary=_p19_summary(),
        extra_payloads_for_scan=[("unsafe_extra", {"note": "BINANCE_API_SECRET=leaked"})],
    )
    assert "P20_SECRET_VALUE_PATTERN_FOUND" in report["block_reasons"]


def test_p20_negative_fixture_results_all_block_fail_closed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    results = build_p20_negative_fixture_results(root=tmp_path)

    assert results["all_negative_fixtures_blocked_fail_closed"] is True
    assert set(results["fixture_results"]) == {
        "missing_p18_summary",
        "p18_blocked",
        "missing_p19_summary",
        "p19_blocked",
        "invalid_p18_hash",
        "unsafe_runtime_flag",
        "secret_pattern_found",
    }
    for result in results["fixture_results"].values():
        assert result["blocked"] is True
        assert result["limited_live_scaled_auto_trading_allowed"] is False
        assert result["live_scaled_execution_enabled"] is False
        assert result["live_order_submission_allowed"] is False
        assert result["runtime_scheduler_enabled"] is False
        assert result["secret_value_accessed"] is False

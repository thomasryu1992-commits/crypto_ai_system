from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.docker_launcher_evidence_intake import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALID_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_docker_build_external_evidence_template,
    build_docker_launcher_evidence_intake_report,
    build_docker_run_external_evidence_template,
    build_launcher_import_external_evidence_template,
    build_p19_negative_fixture_results,
    persist_docker_launcher_evidence_intake,
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


def _p18_summary() -> dict:
    return {
        "status": "P18_FULL_REGRESSION_CI_RELEASE_GATE_HARDENED_REVIEW_ONLY",
        "p18_full_regression_ci_release_gate_sha256": _p18_hash(),
        "p18_full_regression_ci_release_gate_summary_sha256": "b" * 64,
        "p18_ci_release_gate_hardened_review_only": True,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _p18_report() -> dict:
    return {
        "status": "P18_FULL_REGRESSION_CI_RELEASE_GATE_HARDENED_REVIEW_ONLY",
        "p18_full_regression_ci_release_gate_sha256": _p18_hash(),
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def _valid_evidence() -> tuple[dict, dict, dict]:
    h = _p18_hash()
    return (
        build_docker_build_external_evidence_template(h),
        build_docker_run_external_evidence_template(h),
        build_launcher_import_external_evidence_template(h),
    )


def test_p19_waits_when_external_docker_launcher_evidence_is_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_docker_launcher_evidence_intake_report(
        root=tmp_path,
        p18_summary=_p18_summary(),
        p18_report=_p18_report(),
    )

    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["waiting"] is True
    assert report["blocked"] is False
    assert "P19_EXTERNAL_DOCKER_OR_LAUNCHER_EVIDENCE_MISSING" in report["waiting_reasons"]
    assert report["missing_external_evidence_files"] == [
        "p19_docker_build_evidence_external.json",
        "p19_docker_run_self_test_evidence_external.json",
        "p19_launcher_import_evidence_external.json",
    ]
    assert report["limited_live_scaled_auto_trading_allowed"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["secret_value_accessed"] is False


def test_p19_validates_external_docker_build_run_and_launcher_import_evidence(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    docker_build, docker_run, launcher = _valid_evidence()
    report = build_docker_launcher_evidence_intake_report(
        root=tmp_path,
        p18_summary=_p18_summary(),
        p18_report=_p18_report(),
        docker_build_evidence=docker_build,
        docker_run_evidence=docker_run,
        launcher_import_evidence=launcher,
    )

    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert report["p19_docker_launcher_evidence_intake_valid_review_only"] is True
    assert report["docker_build_evidence_valid_review_only"] is True
    assert report["docker_run_self_test_evidence_valid_review_only"] is True
    assert report["launcher_import_evidence_valid_review_only"] is True
    assert report["missing_external_evidence_files"] == []
    assert report["live_order_submission_allowed"] is False
    assert report["order_endpoint_called"] is False
    assert report["secret_value_logged"] is False


def test_p19_persists_latest_report_summary_registry_and_negative_fixtures(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    latest = tmp_path / "storage" / "latest"
    docker_build, docker_run, launcher = _valid_evidence()
    atomic_write_json(latest / "p18_full_regression_ci_release_gate_summary.json", _p18_summary())
    atomic_write_json(latest / "p18_full_regression_ci_release_gate_report.json", _p18_report())
    atomic_write_json(latest / "p19_docker_build_evidence_external.json", docker_build)
    atomic_write_json(latest / "p19_docker_run_self_test_evidence_external.json", docker_run)
    atomic_write_json(latest / "p19_launcher_import_evidence_external.json", launcher)
    cfg = load_config(tmp_path)

    report = persist_docker_launcher_evidence_intake(cfg=cfg)

    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    saved = read_json(latest / "p19_docker_launcher_evidence_intake_report.json")
    summary = read_json(latest / "p19_docker_launcher_evidence_intake_summary.json")
    registry = read_json(latest / "p19_docker_launcher_evidence_intake_registry_record.json")
    negative = read_json(latest / "p19_docker_launcher_evidence_intake_negative_fixture_results.json")
    assert saved["status"] == STATUS_VALID_REVIEW_ONLY
    assert summary["p19_docker_launcher_evidence_intake_valid_review_only"] is True
    assert summary["docker_build_evidence_valid_review_only"] is True
    assert summary["launcher_import_evidence_valid_review_only"] is True
    assert registry["live_scaled_execution_enabled"] is False
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True


def test_p19_blocks_failed_or_unsafe_external_evidence(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    docker_build, docker_run, launcher = _valid_evidence()

    report = build_docker_launcher_evidence_intake_report(
        root=tmp_path,
        p18_summary={},
        p18_report=_p18_report(),
        docker_build_evidence=docker_build,
        docker_run_evidence=docker_run,
        launcher_import_evidence=launcher,
    )
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P19_SOURCE_P18_SUMMARY_MISSING" in report["block_reasons"]

    report = build_docker_launcher_evidence_intake_report(
        root=tmp_path,
        p18_summary=_p18_summary(),
        p18_report=_p18_report(),
        docker_build_evidence={**docker_build, "exit_code": 1},
        docker_run_evidence=docker_run,
        launcher_import_evidence=launcher,
    )
    assert "P19_DOCKER_BUILD_NOT_SUCCESSFUL" in report["block_reasons"]

    report = build_docker_launcher_evidence_intake_report(
        root=tmp_path,
        p18_summary=_p18_summary(),
        p18_report=_p18_report(),
        docker_build_evidence=docker_build,
        docker_run_evidence={**docker_run, "order_endpoint_called": True},
        launcher_import_evidence=launcher,
    )
    assert "P19_UNSAFE_TRUTHY_FLAG_FOUND" in report["block_reasons"]

    report = build_docker_launcher_evidence_intake_report(
        root=tmp_path,
        p18_summary=_p18_summary(),
        p18_report=_p18_report(),
        docker_build_evidence={**docker_build, "stdout_excerpt": "BINANCE_API_SECRET=leaked"},
        docker_run_evidence=docker_run,
        launcher_import_evidence=launcher,
    )
    assert "P19_SECRET_VALUE_PATTERN_FOUND" in report["block_reasons"]

    report = build_docker_launcher_evidence_intake_report(
        root=tmp_path,
        p18_summary=_p18_summary(),
        p18_report=_p18_report(),
        docker_build_evidence=docker_build,
        docker_run_evidence=docker_run,
        launcher_import_evidence={**launcher, "telegram_router_mutated_by_this_module": True},
    )
    assert "P19_LAUNCHER_IMPORT_MUTATION_DETECTED" in report["block_reasons"]


def test_p19_negative_fixture_results_all_block_fail_closed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    results = build_p19_negative_fixture_results(root=tmp_path)

    assert results["all_negative_fixtures_blocked_fail_closed"] is True
    assert set(results["fixture_results"]) == {
        "missing_p18_summary",
        "p18_blocked",
        "docker_build_failed",
        "docker_run_failed",
        "launcher_import_failed",
        "p18_hash_mismatch",
        "secret_pattern_found",
        "endpoint_called_in_evidence",
        "launcher_mutated_router",
        "unsafe_runtime_flag",
    }
    for result in results["fixture_results"].values():
        assert result["blocked"] is True
        assert result["limited_live_scaled_auto_trading_allowed"] is False
        assert result["live_scaled_execution_enabled"] is False
        assert result["live_order_submission_allowed"] is False
        assert result["runtime_scheduler_enabled"] is False
        assert result["secret_value_accessed"] is False

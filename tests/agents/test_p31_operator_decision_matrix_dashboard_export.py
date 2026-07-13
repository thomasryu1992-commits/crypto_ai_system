from __future__ import annotations

import csv
from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_decision_matrix_dashboard_export import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_operator_decision_matrix_dashboard_export_report,
    build_p31_negative_fixture_results,
    persist_operator_decision_matrix_dashboard_export,
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


def _p30_matrix(decision: str = "GO_REVIEW_ONLY") -> list[dict]:
    return [
        {
            "phase": f"P{idx}",
            "label": f"Phase {idx}",
            "decision": decision,
            "summary_status": f"P{idx}_VALID_REVIEW_ONLY",
            "summary_present": True,
            "decision_reasons": [],
            "runtime_authority": False,
            "order_submission_allowed_by_phase": False,
        }
        for idx in range(30)
    ]


def _p30_report(*, decision: str = "GO_REVIEW_ONLY_FOR_SEPARATE_OPERATOR_RUNTIME_ACTIVATION_DECISION_NOT_RUNTIME_AUTHORITY", waiting: bool = False) -> dict:
    matrix = _p30_matrix("WAITING" if waiting else "GO_REVIEW_ONLY")
    return {
        "status": "P30_FINAL_ACTIVATION_READINESS_GO_NO_GO_MATRIX_GENERATED_REVIEW_ONLY",
        "blocked": False,
        "waiting": waiting,
        "operator_final_activation_decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE" if waiting else decision,
        "required_phase_count": 30,
        "present_phase_count": 30,
        "go_review_only_phase_count": 10 if waiting else 30,
        "waiting_phase_count": 20 if waiting else 0,
        "no_go_phase_count": 0,
        "waiting_phases": ["P7", "P8"] if waiting else [],
        "no_go_phases": [],
        "go_review_only_phases": [f"P{idx}" for idx in range(10 if waiting else 30)],
        "go_no_go_matrix": matrix,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }


def _write_p30_latest(root: Path, report: dict | None = None, matrix: list[dict] | None = None) -> None:
    latest = root / "storage" / "latest"
    report = report or _p30_report(waiting=True)
    matrix = matrix if matrix is not None else report["go_no_go_matrix"]
    atomic_write_json(latest / "p30_final_activation_readiness_go_no_go_matrix_report.json", report)
    atomic_write_json(latest / "p30_final_activation_readiness_go_no_go_matrix_summary.json", {
        "status": report["status"],
        "operator_final_activation_decision": report["operator_final_activation_decision"],
        "final_activation_execution_allowed_by_this_matrix": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    })
    atomic_write_json(latest / "p30_final_activation_readiness_go_no_go_matrix.json", matrix)


def test_p31_waits_when_p30_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_operator_decision_matrix_dashboard_export_report(root=tmp_path)
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["waiting"] is True
    assert "P31_SOURCE_P30_REPORT_MISSING" in report["waiting_reasons"]
    assert report["live_scaled_execution_enabled"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["secret_value_accessed"] is False


def test_p31_generates_human_readable_dashboard_from_waiting_p30(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p30_latest(tmp_path, _p30_report(waiting=True))
    report = build_operator_decision_matrix_dashboard_export_report(root=tmp_path)
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert report["operator_final_activation_decision"] == "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE"
    assert report["dashboard_markdown_created_review_only"] is True
    assert report["dashboard_csv_created_review_only"] is True
    assert report["telegram_compact_summary_created_review_only"] is True
    assert report["launcher_compact_dashboard_created_review_only"] is True
    assert report["dashboard_is_runtime_authority"] is False
    assert report["launcher_dashboard_card"]["runtime_enabled"] is False
    assert "Runtime: DISABLED" in report["telegram_summary_text"]


def test_p31_blocks_source_p30_blocked_or_unsafe_payloads(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    blocked_report = {**_p30_report(), "blocked": True}
    report = build_operator_decision_matrix_dashboard_export_report(root=tmp_path, p30_report=blocked_report, p30_matrix=blocked_report["go_no_go_matrix"])
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P31_SOURCE_P30_BLOCKED_FAIL_CLOSED" in report["block_reasons"]

    unsafe_report = {**_p30_report(), "live_scaled_execution_enabled": True}
    unsafe = build_operator_decision_matrix_dashboard_export_report(root=tmp_path, p30_report=unsafe_report, p30_matrix=unsafe_report["go_no_go_matrix"])
    assert unsafe["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P31_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND" in unsafe["block_reasons"]

    endpoint_report = {**_p30_report(), "order_endpoint_called": True}
    endpoint = build_operator_decision_matrix_dashboard_export_report(root=tmp_path, p30_report=endpoint_report, p30_matrix=endpoint_report["go_no_go_matrix"])
    assert endpoint["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P31_ENDPOINT_CALL_EVIDENCE_FOUND" in endpoint["block_reasons"]

    secret_report = {**_p30_report(), "operator_note": "BINANCE_API_SECRET=leaked"}
    secret = build_operator_decision_matrix_dashboard_export_report(root=tmp_path, p30_report=secret_report, p30_matrix=secret_report["go_no_go_matrix"])
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P31_SECRET_VALUE_PATTERN_FOUND" in secret["block_reasons"]


def test_p31_persists_markdown_csv_compact_telegram_launcher_and_registry(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p30_latest(tmp_path, _p30_report(waiting=True))
    report = persist_operator_decision_matrix_dashboard_export(load_config(tmp_path))
    latest = tmp_path / "storage" / "latest"
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert (latest / "p31_operator_decision_matrix_dashboard_export_report.json").exists()
    assert (latest / "p31_operator_decision_matrix_dashboard_export_summary.json").exists()
    assert (latest / "p31_operator_decision_matrix_dashboard.md").exists()
    assert (latest / "p31_operator_decision_matrix_dashboard.csv").exists()
    assert (latest / "p31_operator_decision_matrix_compact_dashboard.json").exists()
    assert (latest / "p31_operator_decision_matrix_telegram_summary.txt").exists()
    assert (latest / "p31_operator_decision_matrix_launcher_card.json").exists()
    assert (latest / "p31_operator_decision_matrix_dashboard_export_registry_record.json").exists()
    markdown = (latest / "p31_operator_decision_matrix_dashboard.md").read_text(encoding="utf-8")
    assert "Crypto AI System Operator Decision Matrix Dashboard" in markdown
    assert "Runtime authority: `false`" in markdown
    csv_rows = list(csv.DictReader((latest / "p31_operator_decision_matrix_dashboard.csv").read_text(encoding="utf-8").splitlines()))
    assert len(csv_rows) == 30
    compact = read_json(latest / "p31_operator_decision_matrix_compact_dashboard.json")
    assert compact["runtime_authority"] is False
    assert compact["runtime_scheduler_enabled"] is False
    summary = read_json(latest / "p31_operator_decision_matrix_dashboard_export_summary.json")
    assert summary["dashboard_markdown_created_review_only"] is True
    assert summary["live_scaled_execution_enabled"] is False


def test_p31_negative_fixture_results_fail_closed_or_waiting(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    negative = build_p31_negative_fixture_results(root=tmp_path)
    assert negative["status"] == "P31_NEGATIVE_FIXTURES_RECORDED"
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert negative["fixture_results"]["unsafe_runtime_flag"]["blocked"] is True
    assert negative["fixture_results"]["endpoint_call_evidence_found"]["blocked"] is True
    assert negative["fixture_results"]["secret_pattern_found"]["blocked"] is True
    assert negative["fixture_results"]["missing_p30_report"]["waiting"] is True

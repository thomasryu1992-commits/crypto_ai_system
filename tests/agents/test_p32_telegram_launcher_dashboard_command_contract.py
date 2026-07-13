from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_decision_matrix_dashboard_export import STATUS_GENERATED_REVIEW_ONLY as P31_STATUS_GENERATED_REVIEW_ONLY
from crypto_ai_system.execution.telegram_launcher_dashboard_command_contract import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_p32_negative_fixture_results,
    build_telegram_launcher_dashboard_command_contract_report,
    persist_telegram_launcher_dashboard_command_contract,
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


def _p31_payloads() -> tuple[dict, dict, dict, dict, str]:
    compact = {
        "status": P31_STATUS_GENERATED_REVIEW_ONLY,
        "operator_final_activation_decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
        "required_phase_count": 30,
        "present_phase_count": 30,
        "go_review_only_phase_count": 10,
        "waiting_phase_count": 20,
        "no_go_phase_count": 0,
        "waiting_phases": ["P7", "P8", "P9"],
        "no_go_phases": [],
        "next_operator_action": "Collect missing external/operator evidence.",
        "runtime_authority": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    report = {
        "status": P31_STATUS_GENERATED_REVIEW_ONLY,
        "blocked": False,
        "waiting": False,
        "operator_final_activation_decision": compact["operator_final_activation_decision"],
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    summary = {
        "status": P31_STATUS_GENERATED_REVIEW_ONLY,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    launcher = {
        "title": "Crypto AI System Activation Matrix",
        "decision": compact["operator_final_activation_decision"],
        "runtime_enabled": False,
        "scheduler_enabled": False,
        "order_submission_allowed": False,
    }
    telegram = "Crypto_AI_System P31 Dashboard\nRuntime: DISABLED | Scheduler: DISABLED | Orders: DISABLED\nAuthority: REVIEW_ONLY"
    return report, summary, compact, launcher, telegram


def _write_p31_latest(root: Path) -> None:
    report, summary, compact, launcher, telegram = _p31_payloads()
    latest = root / "storage" / "latest"
    atomic_write_json(latest / "p31_operator_decision_matrix_dashboard_export_report.json", report)
    atomic_write_json(latest / "p31_operator_decision_matrix_dashboard_export_summary.json", summary)
    atomic_write_json(latest / "p31_operator_decision_matrix_compact_dashboard.json", compact)
    atomic_write_json(latest / "p31_operator_decision_matrix_launcher_card.json", launcher)
    (latest / "p31_operator_decision_matrix_telegram_summary.txt").write_text(telegram, encoding="utf-8")
    (latest / "p31_operator_decision_matrix_dashboard.md").write_text("# dashboard", encoding="utf-8")
    (latest / "p31_operator_decision_matrix_dashboard.csv").write_text("phase,decision\nP0,GO\n", encoding="utf-8")


def test_p32_waits_when_p31_artifacts_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_telegram_launcher_dashboard_command_contract_report(root=tmp_path)
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["waiting"] is True
    assert "P32_SOURCE_P31_REPORT_MISSING" in report["waiting_reasons"]
    assert report["telegram_command_executes_runtime"] is False
    assert report["launcher_command_executes_runtime"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["secret_value_accessed"] is False


def test_p32_generates_read_only_telegram_and_launcher_command_contract(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p31_latest(tmp_path)
    report = build_telegram_launcher_dashboard_command_contract_report(root=tmp_path)
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert report["allowed_command_count"] == 5
    assert report["surface_count"] == 2
    assert report["contract_command_count"] == 10
    assert report["status_command_available"] is True
    assert report["matrix_command_available"] is True
    assert report["waiting_command_available"] is True
    assert report["no_go_command_available"] is True
    assert report["export_paths_command_available"] is True
    assert report["command_contract"]["read_only"] is True
    assert report["command_contract"]["runtime_authority"] is False
    assert report["command_responses"]["status"]["runtime"] == "DISABLED"
    assert report["command_responses"]["status"]["scheduler"] == "DISABLED"
    assert report["command_responses"]["status"]["orders"] == "DISABLED"
    assert report["command_responses"]["waiting"]["waiting_phases"] == ["P7", "P8", "P9"]
    assert "Crypto_AI_System Status" in report["telegram_text_responses"]["status"]
    assert report["launcher_command_payload"]["runtime_enabled"] is False
    assert report["launcher_command_payload"]["scheduler_enabled"] is False
    assert report["launcher_command_payload"]["order_submission_allowed"] is False


def test_p32_blocks_unsafe_p31_or_command_payloads(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report_payload, summary, compact, launcher, telegram = _p31_payloads()
    unsafe = build_telegram_launcher_dashboard_command_contract_report(
        root=tmp_path,
        p31_report={**report_payload, "live_scaled_execution_enabled": True},
        p31_summary=summary,
        compact_dashboard=compact,
        launcher_card=launcher,
        telegram_summary_text=telegram,
    )
    assert unsafe["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P32_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND" in unsafe["block_reasons"]

    endpoint = build_telegram_launcher_dashboard_command_contract_report(
        root=tmp_path,
        p31_report={**report_payload, "order_endpoint_called": True},
        p31_summary=summary,
        compact_dashboard=compact,
        launcher_card=launcher,
        telegram_summary_text=telegram,
    )
    assert endpoint["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P32_ENDPOINT_CALL_EVIDENCE_FOUND" in endpoint["block_reasons"]

    secret = build_telegram_launcher_dashboard_command_contract_report(
        root=tmp_path,
        p31_report=report_payload,
        p31_summary=summary,
        compact_dashboard=compact,
        launcher_card=launcher,
        telegram_summary_text="BINANCE_API_SECRET=leaked",
    )
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P32_SECRET_VALUE_PATTERN_FOUND" in secret["block_reasons"]

    bad_command = build_telegram_launcher_dashboard_command_contract_report(
        root=tmp_path,
        p31_report=report_payload,
        p31_summary=summary,
        compact_dashboard=compact,
        launcher_card=launcher,
        telegram_summary_text=telegram,
        extra_payloads_for_scan=[("bad_command", {"telegram_command_executes_runtime": True})],
    )
    assert bad_command["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P32_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND" in bad_command["block_reasons"]


def test_p32_persists_command_contract_artifacts_and_registry(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p31_latest(tmp_path)
    report = persist_telegram_launcher_dashboard_command_contract(load_config(tmp_path))
    latest = tmp_path / "storage" / "latest"
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert (latest / "p32_telegram_launcher_dashboard_command_contract_report.json").exists()
    assert (latest / "p32_telegram_launcher_dashboard_command_contract_summary.json").exists()
    assert (latest / "p32_telegram_launcher_dashboard_command_contract.json").exists()
    assert (latest / "p32_telegram_dashboard_command_responses.json").exists()
    assert (latest / "p32_launcher_dashboard_command_responses.json").exists()
    assert (latest / "p32_telegram_dashboard_command_responses.txt").exists()
    assert (latest / "p32_telegram_launcher_dashboard_command_contract_registry_record.json").exists()
    summary = read_json(latest / "p32_telegram_launcher_dashboard_command_contract_summary.json")
    assert summary["command_contract_generated_review_only"] is True
    assert summary["live_scaled_execution_enabled"] is False
    assert summary["runtime_scheduler_enabled"] is False
    contract = read_json(latest / "p32_telegram_launcher_dashboard_command_contract.json")
    assert contract["read_only"] is True
    assert contract["runtime_authority"] is False
    assert len(contract["commands"]) == 10


def test_p32_negative_fixture_results_fail_closed_or_waiting(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    negative = build_p32_negative_fixture_results(root=tmp_path)
    assert negative["status"] == "P32_NEGATIVE_FIXTURES_RECORDED"
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert negative["fixture_results"]["unsafe_runtime_flag"]["blocked"] is True
    assert negative["fixture_results"]["endpoint_called"]["blocked"] is True
    assert negative["fixture_results"]["secret_pattern_found"]["blocked"] is True
    assert negative["fixture_results"]["telegram_command_executes_runtime"]["blocked"] is True
    assert negative["fixture_results"]["launcher_command_allows_order_submission"]["blocked"] is True
    assert negative["fixture_results"]["missing_p31_report"]["waiting"] is True

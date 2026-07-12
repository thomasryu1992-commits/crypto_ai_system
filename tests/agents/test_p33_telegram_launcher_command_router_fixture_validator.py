from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.telegram_launcher_command_router_fixture_validator import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_p33_negative_fixture_results,
    build_telegram_launcher_command_router_fixture_validator_report,
    persist_telegram_launcher_command_router_fixture_validator,
)
from crypto_ai_system.execution.telegram_launcher_dashboard_command_contract import STATUS_GENERATED_REVIEW_ONLY as P32_STATUS_GENERATED_REVIEW_ONLY


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  name: tmp-crypto-ai-system\n  version: test\n"
        "storage:\n  latest_dir: storage/latest\n  registry_dir: storage/registries\n",
        encoding="utf-8",
    )


def _p32_payloads() -> tuple[dict, dict, dict, dict, dict]:
    commands = [
        {"surface": surface, "command": command, "command_id": f"p32_{surface}_{command}"}
        for surface in ("telegram", "launcher")
        for command in ("status", "matrix", "waiting", "no_go", "export_paths")
    ]
    contract = {
        "status": P32_STATUS_GENERATED_REVIEW_ONLY,
        "read_only": True,
        "runtime_authority": False,
        "commands": commands,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    report = {
        "status": P32_STATUS_GENERATED_REVIEW_ONLY,
        "blocked": False,
        "waiting": False,
        "command_contract_generated_review_only": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    summary = dict(report)
    telegram = {
        "status": {"runtime": "DISABLED", "scheduler": "DISABLED", "orders": "DISABLED"},
        "matrix": {"runtime_authority": False},
        "waiting": {"runtime_authority": False},
        "no_go": {"runtime_authority": False},
        "export_paths": {"runtime_authority": False},
    }
    launcher = {
        "surface": "launcher",
        "runtime_enabled": False,
        "scheduler_enabled": False,
        "order_submission_allowed": False,
        "responses": telegram,
    }
    return report, summary, contract, telegram, launcher


def _write_p32_latest(root: Path) -> None:
    report, summary, contract, telegram, launcher = _p32_payloads()
    latest = root / "storage" / "latest"
    atomic_write_json(latest / "p32_telegram_launcher_dashboard_command_contract_report.json", report)
    atomic_write_json(latest / "p32_telegram_launcher_dashboard_command_contract_summary.json", summary)
    atomic_write_json(latest / "p32_telegram_launcher_dashboard_command_contract.json", contract)
    atomic_write_json(latest / "p32_telegram_dashboard_command_responses.json", telegram)
    atomic_write_json(latest / "p32_launcher_dashboard_command_responses.json", launcher)


def test_p33_waits_when_p32_artifacts_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_telegram_launcher_command_router_fixture_validator_report(root=tmp_path)
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["waiting"] is True
    assert "P33_SOURCE_P32_REPORT_MISSING" in report["waiting_reasons"]
    assert report["router_command_executes_runtime"] is False
    assert report["router_command_allows_order_submission"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["order_endpoint_called"] is False
    assert report["secret_value_accessed"] is False


def test_p33_generates_read_only_router_fixtures_from_p32_contract(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p32_latest(tmp_path)
    report = build_telegram_launcher_command_router_fixture_validator_report(root=tmp_path)
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert report["allowed_command_count"] == 5
    assert report["surface_count"] == 2
    assert report["telegram_allowed_route_count"] >= 5
    assert report["launcher_allowed_route_count"] >= 5
    assert report["telegram_denied_route_count"] >= 10
    assert report["launcher_denied_route_count"] >= 10
    assert report["all_surfaces_valid_review_only"] is True
    assert report["router_contract"]["read_only"] is True
    assert report["router_contract"]["runtime_authority"] is False
    assert report["telegram_router_fixture"]["mutates_telegram_router"] is False
    assert report["launcher_router_fixture"]["mutates_launcher_router"] is False
    telegram_routes = report["telegram_router_fixture"]["router_routes"]
    assert any(route["input_command"] == "/crypto_status" and route["status"] == "ROUTE_ALLOWED_READ_ONLY" for route in telegram_routes)
    denied = report["telegram_router_fixture"]["unsafe_routes"]
    assert any(route["input_command"] == "/crypto_live" and route["blocked"] is True for route in denied)
    assert all(route["executes_runtime"] is False for route in telegram_routes + denied)


def test_p33_blocks_unsafe_p32_or_router_payloads(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report_payload, summary, contract, telegram, launcher = _p32_payloads()
    unsafe = build_telegram_launcher_command_router_fixture_validator_report(
        root=tmp_path,
        p32_report={**report_payload, "live_scaled_execution_enabled": True},
        p32_summary=summary,
        p32_contract=contract,
        p32_telegram_responses=telegram,
        p32_launcher_payload=launcher,
    )
    assert unsafe["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P33_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND" in unsafe["block_reasons"]

    endpoint = build_telegram_launcher_command_router_fixture_validator_report(
        root=tmp_path,
        p32_report={**report_payload, "order_endpoint_called": True},
        p32_summary=summary,
        p32_contract=contract,
        p32_telegram_responses=telegram,
        p32_launcher_payload=launcher,
    )
    assert endpoint["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P33_ENDPOINT_CALL_EVIDENCE_FOUND" in endpoint["block_reasons"]

    secret = build_telegram_launcher_command_router_fixture_validator_report(
        root=tmp_path,
        p32_report=report_payload,
        p32_summary=summary,
        p32_contract=contract,
        p32_telegram_responses={"status": "BINANCE_API_SECRET=leaked"},
        p32_launcher_payload=launcher,
    )
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P33_SECRET_VALUE_PATTERN_FOUND" in secret["block_reasons"]

    bad_router = build_telegram_launcher_command_router_fixture_validator_report(
        root=tmp_path,
        p32_report=report_payload,
        p32_summary=summary,
        p32_contract=contract,
        p32_telegram_responses=telegram,
        p32_launcher_payload=launcher,
        extra_payloads_for_scan=[("bad_router", {"router_command_executes_runtime": True})],
    )
    assert bad_router["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P33_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND" in bad_router["block_reasons"]


def test_p33_persists_router_artifacts_and_registry(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p32_latest(tmp_path)
    report = persist_telegram_launcher_command_router_fixture_validator(load_config(tmp_path))
    latest = tmp_path / "storage" / "latest"
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert (latest / "p33_telegram_launcher_command_router_fixture_validator_report.json").exists()
    assert (latest / "p33_telegram_launcher_command_router_fixture_validator_summary.json").exists()
    assert (latest / "p33_telegram_launcher_command_router_contract.json").exists()
    assert (latest / "p33_telegram_command_router_fixture.json").exists()
    assert (latest / "p33_launcher_command_router_fixture.json").exists()
    assert (latest / "p33_command_router_fixture_validation_results.json").exists()
    assert (latest / "p33_command_router_read_only_routes.txt").exists()
    assert (latest / "p33_telegram_launcher_command_router_fixture_validator_registry_record.json").exists()
    summary = read_json(latest / "p33_telegram_launcher_command_router_fixture_validator_summary.json")
    assert summary["router_contract_generated_review_only"] is True
    assert summary["router_command_executes_runtime"] is False
    assert summary["live_scaled_execution_enabled"] is False
    assert summary["runtime_scheduler_enabled"] is False
    validation = read_json(latest / "p33_command_router_fixture_validation_results.json")
    assert validation["all_surfaces_valid_review_only"] is True


def test_p33_negative_fixture_results_fail_closed_or_waiting(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    negative = build_p33_negative_fixture_results(root=tmp_path)
    assert negative["status"] == "P33_NEGATIVE_FIXTURES_RECORDED"
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert negative["fixture_results"]["unsafe_runtime_flag"]["blocked"] is True
    assert negative["fixture_results"]["endpoint_called"]["blocked"] is True
    assert negative["fixture_results"]["secret_pattern_found"]["blocked"] is True
    assert negative["fixture_results"]["router_executes_runtime"]["blocked"] is True
    assert negative["fixture_results"]["launcher_allows_order_submission"]["blocked"] is True
    assert negative["fixture_results"]["telegram_router_mutated"]["blocked"] is True
    assert negative["fixture_results"]["missing_p32_report"]["waiting"] is True

from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.telegram_launcher_command_response_snapshot_pack import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_p34_negative_fixture_results,
    build_telegram_launcher_command_response_snapshot_pack_report,
    persist_telegram_launcher_command_response_snapshot_pack,
)
from crypto_ai_system.execution.telegram_launcher_command_router_fixture_validator import STATUS_GENERATED_REVIEW_ONLY as P33_STATUS_GENERATED_REVIEW_ONLY


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  name: tmp-crypto-ai-system\n  version: test\n"
        "storage:\n  latest_dir: storage/latest\n  registry_dir: storage/registries\n",
        encoding="utf-8",
    )


def _p33_payloads() -> tuple[dict, dict, dict, dict, dict, dict, dict]:
    allowed = ("status", "matrix", "waiting", "no_go", "export_paths")
    route_base = {
        "status": "ROUTE_ALLOWED_READ_ONLY",
        "blocked": False,
        "read_only": True,
        "executes_runtime": False,
        "allows_order_submission": False,
        "enables_scheduler": False,
        "calls_endpoint": False,
        "reads_secret_value": False,
        "mutates_runtime": False,
        "runtime_authority": False,
    }
    denied_base = {
        "status": "ROUTE_BLOCKED_FAIL_CLOSED",
        "blocked": True,
        "read_only": True,
        "executes_runtime": False,
        "allows_order_submission": False,
        "enables_scheduler": False,
        "calls_endpoint": False,
        "reads_secret_value": False,
        "mutates_runtime": False,
        "runtime_authority": False,
        "denied_reason": "P33_UNSAFE_OR_UNKNOWN_COMMAND_BLOCKED",
    }
    routes = [{**route_base, "canonical_command": c, "input_command": f"/crypto_{c}"} for c in allowed]
    denied = [{**denied_base, "input_command": cmd} for cmd in ("/crypto_enable", "/crypto_start", "/crypto_submit", "/crypto_order", "/crypto_live", "/crypto_activate", "/crypto_trade", "/crypto_scheduler_start", "/crypto_place_order", "/crypto_cancel_order")]
    p33_report = {
        "status": P33_STATUS_GENERATED_REVIEW_ONLY,
        "blocked": False,
        "waiting": False,
        "all_surfaces_valid_review_only": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    p33_summary = dict(p33_report)
    p33_contract = {"read_only": True, "runtime_authority": False, "allowed_commands": list(allowed)}
    telegram_router = {"surface": "telegram", "read_only": True, "responses_source": "p32_telegram_dashboard_command_responses.json", "router_routes": routes, "unsafe_routes": denied}
    launcher_router = {"surface": "launcher", "read_only": True, "responses_source": "p32_launcher_dashboard_command_responses.json", "router_routes": routes, "unsafe_routes": denied}
    telegram_responses = {
        "status": {"decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE", "runtime": "DISABLED", "scheduler": "DISABLED", "orders": "DISABLED", "authority": "REVIEW_ONLY"},
        "matrix": {"decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE", "go_review_only": 10, "waiting": 20, "no_go": 0, "dashboard_path": "storage/latest/p31_operator_decision_matrix_dashboard.md"},
        "waiting": {"waiting_phases": ["P7", "P8"], "runtime_authority": False},
        "no_go": {"no_go_phases": [], "runtime_authority": False},
        "export_paths": {"paths": {"markdown_dashboard": "storage/latest/p31_operator_decision_matrix_dashboard.md"}, "runtime_authority": False},
    }
    launcher_payload = {"responses": telegram_responses, "runtime_enabled": False, "scheduler_enabled": False, "order_submission_allowed": False}
    return p33_report, p33_summary, p33_contract, telegram_router, launcher_router, telegram_responses, launcher_payload


def _write_p33_latest(root: Path) -> None:
    p33_report, p33_summary, p33_contract, telegram_router, launcher_router, telegram_responses, launcher_payload = _p33_payloads()
    latest = root / "storage" / "latest"
    atomic_write_json(latest / "p33_telegram_launcher_command_router_fixture_validator_report.json", p33_report)
    atomic_write_json(latest / "p33_telegram_launcher_command_router_fixture_validator_summary.json", p33_summary)
    atomic_write_json(latest / "p33_telegram_launcher_command_router_contract.json", p33_contract)
    atomic_write_json(latest / "p33_telegram_command_router_fixture.json", telegram_router)
    atomic_write_json(latest / "p33_launcher_command_router_fixture.json", launcher_router)
    atomic_write_json(latest / "p32_telegram_dashboard_command_responses.json", telegram_responses)
    atomic_write_json(latest / "p32_launcher_dashboard_command_responses.json", launcher_payload)


def test_p34_waits_when_p33_artifacts_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_telegram_launcher_command_response_snapshot_pack_report(root=tmp_path)
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["waiting"] is True
    assert "P34_SOURCE_P33_REPORT_MISSING" in report["waiting_reasons"]
    assert report["snapshot_command_executes_runtime"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["order_endpoint_called"] is False
    assert report["secret_value_accessed"] is False


def test_p34_generates_read_only_response_snapshots(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p33_latest(tmp_path)
    report = build_telegram_launcher_command_response_snapshot_pack_report(root=tmp_path)
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert report["telegram_snapshot_count"] == 5
    assert report["launcher_snapshot_count"] == 5
    assert report["all_snapshots_safe_review_only"] is True
    telegram = report["telegram_snapshots"]
    assert telegram["snapshot_status"].endswith("GENERATED_REVIEW_ONLY")
    status_snapshot = next(item for item in telegram["command_snapshots"] if item["command"] == "status")
    assert "Crypto_AI_System Status" in status_snapshot["rendered_text"]
    assert status_snapshot["executes_runtime"] is False
    assert status_snapshot["allows_order_submission"] is False
    assert status_snapshot["calls_endpoint"] is False
    blocked = telegram["blocked_command_snapshots"]
    assert any(item["input_command"] == "/crypto_live" and item["blocked"] is True for item in blocked)
    assert "Runtime remains DISABLED" in report["text_snapshot_preview"]
    assert "P34 Telegram / Launcher" in report["markdown_snapshot_preview"]


def test_p34_blocks_unsafe_sources_or_snapshots(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    p33_report, p33_summary, p33_contract, telegram_router, launcher_router, telegram_responses, launcher_payload = _p33_payloads()
    unsafe = build_telegram_launcher_command_response_snapshot_pack_report(
        root=tmp_path,
        p33_report={**p33_report, "live_scaled_execution_enabled": True},
        p33_summary=p33_summary,
        p33_router_contract=p33_contract,
        p33_telegram_router=telegram_router,
        p33_launcher_router=launcher_router,
        p32_telegram_responses=telegram_responses,
        p32_launcher_payload=launcher_payload,
    )
    assert unsafe["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P34_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND" in unsafe["block_reasons"]

    endpoint = build_telegram_launcher_command_response_snapshot_pack_report(
        root=tmp_path,
        p33_report={**p33_report, "order_endpoint_called": True},
        p33_summary=p33_summary,
        p33_router_contract=p33_contract,
        p33_telegram_router=telegram_router,
        p33_launcher_router=launcher_router,
        p32_telegram_responses=telegram_responses,
        p32_launcher_payload=launcher_payload,
    )
    assert endpoint["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P34_ENDPOINT_CALL_EVIDENCE_FOUND" in endpoint["block_reasons"]

    secret = build_telegram_launcher_command_response_snapshot_pack_report(
        root=tmp_path,
        p33_report=p33_report,
        p33_summary=p33_summary,
        p33_router_contract=p33_contract,
        p33_telegram_router=telegram_router,
        p33_launcher_router=launcher_router,
        p32_telegram_responses={"status": "BINANCE_API_SECRET=leaked"},
        p32_launcher_payload=launcher_payload,
    )
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P34_SECRET_VALUE_PATTERN_FOUND" in secret["block_reasons"]

    bad_snapshot = build_telegram_launcher_command_response_snapshot_pack_report(
        root=tmp_path,
        p33_report=p33_report,
        p33_summary=p33_summary,
        p33_router_contract=p33_contract,
        p33_telegram_router=telegram_router,
        p33_launcher_router=launcher_router,
        p32_telegram_responses=telegram_responses,
        p32_launcher_payload=launcher_payload,
        extra_payloads_for_scan=[("bad_snapshot", {"snapshot_command_executes_runtime": True})],
    )
    assert bad_snapshot["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P34_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND" in bad_snapshot["block_reasons"]


def test_p34_persists_snapshot_artifacts_and_registry(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p33_latest(tmp_path)
    report = persist_telegram_launcher_command_response_snapshot_pack(load_config(tmp_path))
    latest = tmp_path / "storage" / "latest"
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert (latest / "p34_telegram_launcher_command_response_snapshot_pack_report.json").exists()
    assert (latest / "p34_telegram_launcher_command_response_snapshot_pack_summary.json").exists()
    assert (latest / "p34_telegram_command_response_snapshots.json").exists()
    assert (latest / "p34_launcher_command_response_snapshots.json").exists()
    assert (latest / "p34_command_response_snapshot_pack.json").exists()
    assert (latest / "p34_command_response_snapshot_pack.md").exists()
    assert (latest / "p34_command_response_snapshot_pack.txt").exists()
    assert (latest / "p34_telegram_launcher_command_response_snapshot_pack_registry_record.json").exists()
    summary = read_json(latest / "p34_telegram_launcher_command_response_snapshot_pack_summary.json")
    assert summary["all_snapshots_safe_review_only"] is True
    assert summary["snapshot_command_executes_runtime"] is False
    assert summary["live_scaled_execution_enabled"] is False
    telegram = read_json(latest / "p34_telegram_command_response_snapshots.json")
    assert telegram["allowed_command_count"] == 5


def test_p34_negative_fixture_results_fail_closed_or_waiting(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    negative = build_p34_negative_fixture_results(root=tmp_path)
    assert negative["status"] == "P34_NEGATIVE_FIXTURES_RECORDED"
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert negative["fixture_results"]["unsafe_runtime_flag"]["blocked"] is True
    assert negative["fixture_results"]["endpoint_called"]["blocked"] is True
    assert negative["fixture_results"]["secret_pattern_found"]["blocked"] is True
    assert negative["fixture_results"]["snapshot_executes_runtime"]["blocked"] is True
    assert negative["fixture_results"]["snapshot_allows_order_submission"]["blocked"] is True
    assert negative["fixture_results"]["missing_p33_report"]["waiting"] is True

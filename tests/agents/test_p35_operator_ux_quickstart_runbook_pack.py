from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_ux_quickstart_runbook_pack import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_operator_ux_quickstart_runbook_pack_report,
    build_p35_negative_fixture_results,
    persist_operator_ux_quickstart_runbook_pack,
)
from crypto_ai_system.execution.telegram_launcher_command_response_snapshot_pack import STATUS_GENERATED_REVIEW_ONLY as P34_STATUS_GENERATED_REVIEW_ONLY


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  name: tmp-crypto-ai-system\n  version: test\n"
        "storage:\n  latest_dir: storage/latest\n  registry_dir: storage/registries\n",
        encoding="utf-8",
    )


def _p34_payloads() -> tuple[dict, dict, dict, str, str]:
    p34_report = {
        "status": P34_STATUS_GENERATED_REVIEW_ONLY,
        "blocked": False,
        "waiting": False,
        "operator_final_activation_decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
        "snapshot_command_executes_runtime": False,
        "snapshot_command_allows_order_submission": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    p34_summary = {
        "status": P34_STATUS_GENERATED_REVIEW_ONLY,
        "blocked": False,
        "waiting": False,
        "all_snapshots_safe_review_only": True,
        "snapshot_command_executes_runtime": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    p34_pack = {
        "status": P34_STATUS_GENERATED_REVIEW_ONLY,
        "operator_final_activation_decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
        "read_only": True,
        "runtime_authority": False,
        "allowed_commands": ["status", "matrix", "waiting", "no_go", "export_paths"],
        "snapshot_command_executes_runtime": False,
        "snapshot_command_allows_order_submission": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    text = "Crypto_AI_System P34 Command Response Snapshot Pack\nRuntime: DISABLED\n"
    markdown = "# P34 Telegram / Launcher Command Response Snapshot Pack\nRuntime remains **DISABLED**.\n"
    return p34_report, p34_summary, p34_pack, text, markdown


def _write_p34_latest(root: Path) -> None:
    p34_report, p34_summary, p34_pack, text, markdown = _p34_payloads()
    latest = root / "storage" / "latest"
    atomic_write_json(latest / "p34_telegram_launcher_command_response_snapshot_pack_report.json", p34_report)
    atomic_write_json(latest / "p34_telegram_launcher_command_response_snapshot_pack_summary.json", p34_summary)
    atomic_write_json(latest / "p34_command_response_snapshot_pack.json", p34_pack)
    (latest / "p34_command_response_snapshot_pack.md").write_text(markdown, encoding="utf-8")
    (latest / "p34_command_response_snapshot_pack.txt").write_text(text, encoding="utf-8")
    atomic_write_json(latest / "p34_telegram_command_response_snapshots.json", {"allowed_command_count": 5})
    atomic_write_json(latest / "p34_launcher_command_response_snapshots.json", {"allowed_command_count": 5})


def test_p35_waits_when_p34_artifacts_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_operator_ux_quickstart_runbook_pack_report(root=tmp_path)
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["waiting"] is True
    assert "P35_SOURCE_P34_REPORT_MISSING" in report["waiting_reasons"]
    assert report["quickstart_executes_runtime"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["order_endpoint_called"] is False
    assert report["secret_value_accessed"] is False


def test_p35_generates_non_developer_runbook_pack(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p34_latest(tmp_path)
    report = build_operator_ux_quickstart_runbook_pack_report(root=tmp_path)
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert report["safe_command_count"] == 5
    assert report["operator_checklist_item_count"] >= 8
    assert report["all_quickstart_artifacts_safe_review_only"] is True
    assert "Operator UX Quickstart" in report["quickstart_markdown_preview"]
    assert "status" in report["safe_command_guide_preview"]
    assert report["quickstart_executes_runtime"] is False
    assert report["quickstart_allows_order_submission"] is False
    assert report["quickstart_calls_endpoint"] is False


def test_p35_blocks_unsafe_sources_or_runbook_claims(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    p34_report, p34_summary, p34_pack, text, markdown = _p34_payloads()
    unsafe = build_operator_ux_quickstart_runbook_pack_report(
        root=tmp_path,
        p34_report={**p34_report, "live_scaled_execution_enabled": True},
        p34_summary=p34_summary,
        p34_snapshot_pack=p34_pack,
        p34_text_snapshot=text,
        p34_markdown_snapshot=markdown,
    )
    assert unsafe["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P35_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND" in unsafe["block_reasons"]

    endpoint = build_operator_ux_quickstart_runbook_pack_report(
        root=tmp_path,
        p34_report={**p34_report, "order_endpoint_called": True},
        p34_summary=p34_summary,
        p34_snapshot_pack=p34_pack,
        p34_text_snapshot=text,
        p34_markdown_snapshot=markdown,
    )
    assert endpoint["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P35_ENDPOINT_CALL_EVIDENCE_FOUND" in endpoint["block_reasons"]

    secret = build_operator_ux_quickstart_runbook_pack_report(
        root=tmp_path,
        p34_report=p34_report,
        p34_summary=p34_summary,
        p34_snapshot_pack=p34_pack,
        p34_text_snapshot="BINANCE_API_SECRET=leak",
        p34_markdown_snapshot=markdown,
    )
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P35_SECRET_VALUE_PATTERN_FOUND" in secret["block_reasons"]

    bad_claim = build_operator_ux_quickstart_runbook_pack_report(
        root=tmp_path,
        p34_report=p34_report,
        p34_summary=p34_summary,
        p34_snapshot_pack=p34_pack,
        p34_text_snapshot=text,
        p34_markdown_snapshot=markdown,
        extra_payloads_for_scan=[("bad_runbook", {"quickstart_executes_runtime": True})],
    )
    assert bad_claim["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P35_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND" in bad_claim["block_reasons"]


def test_p35_persists_runbook_artifacts_and_registry(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p34_latest(tmp_path)
    report = persist_operator_ux_quickstart_runbook_pack(load_config(tmp_path))
    latest = tmp_path / "storage" / "latest"
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert (latest / "p35_operator_ux_quickstart_runbook_pack_report.json").exists()
    assert (latest / "p35_operator_ux_quickstart_runbook_pack_summary.json").exists()
    assert (latest / "p35_operator_ux_quickstart_runbook_pack.json").exists()
    assert (latest / "p35_operator_ux_quickstart_runbook.md").exists()
    assert (latest / "p35_operator_ux_checklist.md").exists()
    assert (latest / "p35_safe_command_guide.md").exists()
    assert (latest / "p35_operator_ux_quickstart.txt").exists()
    assert (latest / "p35_operator_ux_quickstart_runbook_pack_registry_record.json").exists()
    summary = read_json(latest / "p35_operator_ux_quickstart_runbook_pack_summary.json")
    assert summary["all_quickstart_artifacts_safe_review_only"] is True
    assert summary["runtime_scheduler_enabled"] is False
    assert summary["order_endpoint_called"] is False
    runbook = (latest / "p35_operator_ux_quickstart_runbook.md").read_text(encoding="utf-8")
    assert "Allowed dashboard commands" in runbook
    assert "Commands that must stay blocked" in runbook


def test_p35_negative_fixture_results_fail_closed_or_waiting(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    negative = build_p35_negative_fixture_results(root=tmp_path)
    assert negative["status"] == "P35_NEGATIVE_FIXTURES_RECORDED"
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert negative["fixture_results"]["missing_p34_report"]["waiting"] is True
    assert negative["fixture_results"]["p34_blocked"]["blocked"] is True
    assert negative["fixture_results"]["unsafe_runtime_flag"]["blocked"] is True
    assert negative["fixture_results"]["endpoint_called"]["blocked"] is True
    assert negative["fixture_results"]["secret_pattern_found"]["blocked"] is True
    assert negative["fixture_results"]["quickstart_executes_runtime"]["blocked"] is True
    assert negative["fixture_results"]["quickstart_allows_order_submission"]["blocked"] is True

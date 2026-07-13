from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.non_developer_onboarding_wizard import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_non_developer_onboarding_wizard_report,
    build_p36_negative_fixture_results,
    persist_non_developer_onboarding_wizard,
)
from crypto_ai_system.execution.operator_ux_quickstart_runbook_pack import STATUS_GENERATED_REVIEW_ONLY as P35_STATUS_GENERATED_REVIEW_ONLY


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  name: tmp-crypto-ai-system\n  version: test\n"
        "storage:\n  latest_dir: storage/latest\n  registry_dir: storage/registries\n",
        encoding="utf-8",
    )


def _p35_payloads() -> tuple[dict, dict, dict, str, str, str]:
    report = {
        "status": P35_STATUS_GENERATED_REVIEW_ONLY,
        "blocked": False,
        "waiting": False,
        "operator_final_activation_decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
        "quickstart_executes_runtime": False,
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    summary = {
        "status": P35_STATUS_GENERATED_REVIEW_ONLY,
        "blocked": False,
        "waiting": False,
        "all_quickstart_artifacts_safe_review_only": True,
        "runtime_scheduler_enabled": False,
        "live_scaled_execution_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    pack = {
        "status": P35_STATUS_GENERATED_REVIEW_ONLY,
        "operator_final_activation_decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
        "safe_commands": ["status", "matrix", "waiting", "no_go", "export_paths"],
        "quickstart_executes_runtime": False,
        "quickstart_allows_order_submission": False,
    }
    runbook = "# P35 Operator UX Quickstart\nAllowed dashboard commands\nCommands that must stay blocked\nRuntime remains DISABLED.\n"
    checklist = "# P35 Checklist\n- [ ] Runtime remains disabled.\n"
    safe = "# P35 Safe Command Guide\nstatus\nmatrix\nwaiting\nno_go\nexport_paths\n"
    return report, summary, pack, runbook, checklist, safe


def _write_p35_latest(root: Path) -> None:
    report, summary, pack, runbook, checklist, safe = _p35_payloads()
    latest = root / "storage" / "latest"
    atomic_write_json(latest / "p35_operator_ux_quickstart_runbook_pack_report.json", report)
    atomic_write_json(latest / "p35_operator_ux_quickstart_runbook_pack_summary.json", summary)
    atomic_write_json(latest / "p35_operator_ux_quickstart_runbook_pack.json", pack)
    (latest / "p35_operator_ux_quickstart_runbook.md").write_text(runbook, encoding="utf-8")
    (latest / "p35_operator_ux_checklist.md").write_text(checklist, encoding="utf-8")
    (latest / "p35_safe_command_guide.md").write_text(safe, encoding="utf-8")
    (latest / "p35_operator_ux_quickstart.txt").write_text("Runtime: DISABLED\n", encoding="utf-8")


def test_p36_waits_when_p35_artifacts_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_non_developer_onboarding_wizard_report(root=tmp_path)
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["waiting"] is True
    assert "P36_SOURCE_P35_REPORT_MISSING" in report["waiting_reasons"]
    assert report["wizard_executes_runtime"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["order_endpoint_called"] is False
    assert report["secret_value_accessed"] is False


def test_p36_generates_zip_drop_in_wizard(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p35_latest(tmp_path)
    report = build_non_developer_onboarding_wizard_report(root=tmp_path)
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert report["wizard_step_count"] >= 7
    assert report["failure_lookup_count"] >= 5
    assert report["operator_checklist_item_count"] >= 8
    assert report["all_wizard_artifacts_safe_review_only"] is True
    assert "ZIP Drop-in Guide" in report["zip_drop_in_markdown"]
    assert "status" in report["allowed_read_only_commands"]
    assert "enable" in report["blocked_command_keywords"]
    assert report["wizard_allows_order_submission"] is False
    assert report["wizard_calls_endpoint"] is False


def test_p36_blocks_unsafe_sources_or_claims(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    p35_report, p35_summary, p35_pack, runbook, checklist, safe = _p35_payloads()
    unsafe = build_non_developer_onboarding_wizard_report(
        root=tmp_path,
        p35_report={**p35_report, "live_scaled_execution_enabled": True},
        p35_summary=p35_summary,
        p35_pack=p35_pack,
        p35_runbook=runbook,
        p35_checklist=checklist,
        p35_safe_command_guide=safe,
    )
    assert unsafe["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P36_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND" in unsafe["block_reasons"]

    endpoint = build_non_developer_onboarding_wizard_report(
        root=tmp_path,
        p35_report={**p35_report, "order_endpoint_called": True},
        p35_summary=p35_summary,
        p35_pack=p35_pack,
        p35_runbook=runbook,
        p35_checklist=checklist,
        p35_safe_command_guide=safe,
    )
    assert endpoint["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P36_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND" in endpoint["block_reasons"]

    secret = build_non_developer_onboarding_wizard_report(
        root=tmp_path,
        p35_report=p35_report,
        p35_summary=p35_summary,
        p35_pack=p35_pack,
        p35_runbook="BINANCE_API_SECRET=leak",
        p35_checklist=checklist,
        p35_safe_command_guide=safe,
    )
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P36_SECRET_VALUE_PATTERN_FOUND" in secret["block_reasons"]

    bad_wizard = build_non_developer_onboarding_wizard_report(
        root=tmp_path,
        p35_report=p35_report,
        p35_summary=p35_summary,
        p35_pack=p35_pack,
        p35_runbook=runbook,
        p35_checklist=checklist,
        p35_safe_command_guide=safe,
        extra_payloads_for_scan=[("bad_wizard", {"wizard_executes_runtime": True})],
    )
    assert bad_wizard["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P36_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND" in bad_wizard["block_reasons"]


def test_p36_persists_wizard_artifacts_and_registry(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p35_latest(tmp_path)
    report = persist_non_developer_onboarding_wizard(load_config(tmp_path))
    latest = tmp_path / "storage" / "latest"
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert (latest / "p36_non_developer_onboarding_wizard_report.json").exists()
    assert (latest / "p36_non_developer_onboarding_wizard_summary.json").exists()
    assert (latest / "p36_zip_drop_in_wizard.md").exists()
    assert (latest / "p36_zip_drop_in_checklist.md").exists()
    assert (latest / "p36_failure_message_lookup.md").exists()
    assert (latest / "p36_onboarding_wizard_steps.json").exists()
    assert (latest / "p36_operator_onboarding_card.json").exists()
    assert (latest / "p36_non_developer_onboarding_wizard_registry_record.json").exists()
    summary = read_json(latest / "p36_non_developer_onboarding_wizard_summary.json")
    assert summary["all_wizard_artifacts_safe_review_only"] is True
    assert summary["runtime_scheduler_enabled"] is False
    assert summary["order_endpoint_called"] is False
    guide = (latest / "p36_zip_drop_in_wizard.md").read_text(encoding="utf-8")
    assert "허용되는 조회 명령" in guide
    assert "금지되는 명령 계열" in guide


def test_p36_negative_fixture_results_fail_closed_or_waiting(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    negative = build_p36_negative_fixture_results(root=tmp_path)
    assert negative["status"] == "P36_NEGATIVE_FIXTURES_RECORDED"
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert negative["fixture_results"]["missing_p35_report"]["waiting"] is True
    assert negative["fixture_results"]["p35_blocked"]["blocked"] is True
    assert negative["fixture_results"]["unsafe_runtime_flag"]["blocked"] is True
    assert negative["fixture_results"]["scheduler_enabled"]["blocked"] is True
    assert negative["fixture_results"]["endpoint_called"]["blocked"] is True
    assert negative["fixture_results"]["secret_pattern_found"]["blocked"] is True
    assert negative["fixture_results"]["wizard_executes_runtime"]["blocked"] is True
    assert negative["fixture_results"]["drop_in_allows_order_submission"]["blocked"] is True

from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.onboarding_wizard_failure_doctor import STATUS_GENERATED_REVIEW_ONLY as P37_STATUS_GENERATED_REVIEW_ONLY
from crypto_ai_system.execution.operator_support_bundle_troubleshooting_export_pack import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_operator_support_bundle_report,
    build_p38_negative_fixture_results,
    persist_operator_support_bundle,
)


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "src" / "crypto_ai_system").mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("# tmp\n", encoding="utf-8")
    (root / "config" / "settings.yaml").write_text(
        "project:\n  name: tmp-crypto-ai-system\n  version: test\n"
        "storage:\n  latest_dir: storage/latest\n  registry_dir: storage/registries\n",
        encoding="utf-8",
    )


def _p37_payloads() -> tuple[dict, dict]:
    report = {
        "status": P37_STATUS_GENERATED_REVIEW_ONLY,
        "blocked": False,
        "waiting": False,
        "diagnosis_issue_count": 0,
        "diagnosis_codes": [],
        "operator_final_activation_decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    summary = {
        "status": P37_STATUS_GENERATED_REVIEW_ONLY,
        "blocked": False,
        "waiting": False,
        "diagnosis_issue_count": 0,
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    return report, summary


def _write_support_sources(root: Path) -> None:
    latest = root / "storage" / "latest"
    p37_report, p37_summary = _p37_payloads()
    json_payloads = {
        "p37_onboarding_wizard_failure_doctor_report.json": p37_report,
        "p37_onboarding_wizard_failure_doctor_summary.json": p37_summary,
        "p37_onboarding_wizard_failure_doctor_pack.json": {"status": P37_STATUS_GENERATED_REVIEW_ONLY, "runtime_authority": False},
        "p37_self_diagnosis_results.json": [],
        "p37_failure_doctor_lookup.json": [{"code": "no_zip_found", "operator_action": "Check ZIP."}],
        "p37_operator_self_diagnosis_card.json": {"runtime_authority": False},
        "p36_non_developer_onboarding_wizard_report.json": {"status": "P36_NON_DEVELOPER_ONBOARDING_WIZARD_GENERATED_REVIEW_ONLY", "blocked": False},
        "p36_non_developer_onboarding_wizard_summary.json": {"status": "P36_NON_DEVELOPER_ONBOARDING_WIZARD_GENERATED_REVIEW_ONLY", "blocked": False},
        "p36_non_developer_onboarding_wizard_pack.json": {"status": "P36_NON_DEVELOPER_ONBOARDING_WIZARD_GENERATED_REVIEW_ONLY", "wizard_executes_runtime": False},
        "p36_operator_onboarding_card.json": {"runtime_authority": False},
        "p35_operator_ux_quickstart_runbook_pack_report.json": {"status": "P35_OPERATOR_UX_QUICKSTART_RUNBOOK_PACK_GENERATED_REVIEW_ONLY", "blocked": False},
        "p35_operator_ux_quickstart_runbook_pack_summary.json": {"status": "P35_OPERATOR_UX_QUICKSTART_RUNBOOK_PACK_GENERATED_REVIEW_ONLY", "blocked": False},
        "p35_operator_ux_quickstart_runbook_pack.json": {"status": "P35_OPERATOR_UX_QUICKSTART_RUNBOOK_PACK_GENERATED_REVIEW_ONLY"},
        "p34_telegram_launcher_command_response_snapshot_pack_report.json": {"status": "P34_TELEGRAM_LAUNCHER_COMMAND_RESPONSE_SNAPSHOT_PACK_GENERATED_REVIEW_ONLY", "blocked": False},
        "p34_command_response_snapshot_pack.json": {"status": "P34_TELEGRAM_LAUNCHER_COMMAND_RESPONSE_SNAPSHOT_PACK_GENERATED_REVIEW_ONLY"},
        "p34_telegram_command_response_snapshots.json": {"status": {"route": "READ_ONLY"}},
        "p34_launcher_command_response_snapshots.json": {"status": {"route": "READ_ONLY"}},
        "p33_telegram_launcher_command_router_fixture_validator_report.json": {"status": "P33_TELEGRAM_LAUNCHER_COMMAND_ROUTER_FIXTURE_VALIDATOR_GENERATED_REVIEW_ONLY", "blocked": False},
        "p33_command_router_fixture_validation_results.json": {"all_routes_read_only": True},
        "p33_telegram_launcher_command_router_contract.json": {"allowed_commands": ["status", "matrix", "waiting", "no_go", "export_paths"]},
    }
    text_payloads = {
        "p37_self_diagnosis_pack.md": "# P37 Self-Diagnosis Pack\nRuntime still remains DISABLED.\n",
        "p37_self_diagnosis_checklist.md": "# Checklist\n- [ ] Runtime disabled.\n",
        "p36_zip_drop_in_wizard.md": "# P36 ZIP Drop-in Guide\nRuntime: DISABLED\nScheduler: DISABLED\nOrders: DISABLED\n",
        "p36_zip_drop_in_checklist.md": "# P36 Checklist\n- [ ] status only.\n",
        "p36_failure_message_lookup.md": "# Failure Lookup\nROUTE_BLOCKED_FAIL_CLOSED\n",
        "p35_operator_ux_quickstart_runbook.md": "# P35 Runbook\nUse status/matrix/waiting/no_go/export_paths only.\n",
        "p35_operator_ux_checklist.md": "# Checklist\n- [ ] Do not enable runtime.\n",
        "p35_safe_command_guide.md": "# Safe Commands\nstatus\nmatrix\nwaiting\nno_go\nexport_paths\n",
        "p35_operator_ux_quickstart.txt": "Runtime: DISABLED\nOrders: DISABLED\n",
        "p34_command_response_snapshot_pack.md": "# P34 Snapshots\nstatus -> read-only\n",
        "p34_command_response_snapshot_pack.txt": "Crypto_AI_System Status\nRuntime: DISABLED\n",
        "p33_command_router_read_only_routes.txt": "status\nmatrix\nwaiting\nno_go\nexport_paths\n",
    }
    for filename, payload in json_payloads.items():
        atomic_write_json(latest / filename, payload)
    for filename, text in text_payloads.items():
        (latest / filename).write_text(text, encoding="utf-8")


def test_p38_waits_when_p37_report_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_operator_support_bundle_report(root=tmp_path)
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["waiting"] is True
    assert "missing_p37_report" in report["support_issue_codes"]
    assert report["support_bundle_executes_runtime"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["order_endpoint_called"] is False
    assert report["secret_value_accessed"] is False


def test_p38_generates_support_bundle_when_sources_clean(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_support_sources(tmp_path)
    report = build_operator_support_bundle_report(root=tmp_path)
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert report["support_issue_count"] == 0
    assert report["present_source_artifact_count"] == report["required_source_artifact_count"]
    assert report["missing_source_artifact_count"] == 0
    assert report["all_support_bundle_artifacts_safe_review_only"] is True
    assert "p38_operator_support_bundle_share_packet.json" in report["support_bundle_markdown"]
    assert "status" in report["allowed_read_only_commands"]
    assert "enable" in report["blocked_command_keywords"]
    assert report["redacted_share_packet"]["runtime_authority"] is False
    assert report["support_bundle_allows_order_submission"] is False


def test_p38_blocks_secret_runtime_scheduler_and_endpoint_flags(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    p37_report, p37_summary = _p37_payloads()
    secret = build_operator_support_bundle_report(
        root=tmp_path,
        p37_report=p37_report,
        p37_summary=p37_summary,
        extra_payloads_for_scan=[("bad_secret", "BINANCE_API_SECRET=leak")],
        require_all_sources=False,
    )
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "secret_detected" in secret["support_issue_codes"]

    runtime = build_operator_support_bundle_report(
        root=tmp_path,
        p37_report={**p37_report, "live_scaled_execution_enabled": True},
        p37_summary=p37_summary,
        require_all_sources=False,
    )
    assert runtime["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "runtime_flag_truthy" in runtime["support_issue_codes"]

    scheduler = build_operator_support_bundle_report(
        root=tmp_path,
        p37_report=p37_report,
        p37_summary={**p37_summary, "runtime_scheduler_enabled": True},
        require_all_sources=False,
    )
    assert scheduler["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "scheduler_enabled" in scheduler["support_issue_codes"]

    endpoint = build_operator_support_bundle_report(
        root=tmp_path,
        p37_report={**p37_report, "order_endpoint_called": True},
        p37_summary=p37_summary,
        require_all_sources=False,
    )
    assert endpoint["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "endpoint_called" in endpoint["support_issue_codes"]


def test_p38_persists_support_bundle_artifacts_and_registry(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_support_sources(tmp_path)
    report = persist_operator_support_bundle(load_config(tmp_path))
    latest = tmp_path / "storage" / "latest"
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert (latest / "p38_operator_support_bundle_report.json").exists()
    assert (latest / "p38_operator_support_bundle_summary.json").exists()
    assert (latest / "p38_operator_support_bundle_pack.json").exists()
    assert (latest / "p38_operator_support_bundle_manifest.json").exists()
    assert (latest / "p38_operator_support_bundle_manifest.csv").exists()
    assert (latest / "p38_operator_support_bundle.md").exists()
    assert (latest / "p38_operator_support_bundle_share_packet.json").exists()
    assert (latest / "p38_operator_support_bundle_paths.txt").exists()
    assert (latest / "p38_operator_support_bundle_negative_fixture_results.json").exists()
    assert (latest / "p38_operator_support_bundle_registry_record.json").exists()
    summary = read_json(latest / "p38_operator_support_bundle_summary.json")
    assert summary["all_support_bundle_artifacts_safe_review_only"] is True
    assert summary["runtime_scheduler_enabled"] is False
    assert summary["order_endpoint_called"] is False
    assert summary["secret_value_accessed"] is False
    markdown = (latest / "p38_operator_support_bundle.md").read_text(encoding="utf-8")
    assert "What to Share" in markdown
    share = read_json(latest / "p38_operator_support_bundle_share_packet.json")
    assert share["runtime"] == "DISABLED"
    assert share["contains_secret_values"] is False


def test_p38_negative_fixture_results_fail_closed_or_waiting(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    negative = build_p38_negative_fixture_results(root=tmp_path)
    assert negative["status"] == "P38_NEGATIVE_FIXTURES_RECORDED"
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert negative["fixture_results"]["missing_p37_report"]["waiting"] is True
    assert negative["fixture_results"]["missing_p37_summary"]["waiting"] is True
    assert negative["fixture_results"]["p37_waiting"]["waiting"] is True
    assert negative["fixture_results"]["p37_blocked"]["blocked"] is True
    assert negative["fixture_results"]["missing_support_source_artifacts"]["waiting"] is True
    assert negative["fixture_results"]["runtime_flag_truthy"]["blocked"] is True
    assert negative["fixture_results"]["scheduler_enabled"]["blocked"] is True
    assert negative["fixture_results"]["endpoint_called"]["blocked"] is True
    assert negative["fixture_results"]["secret_detected"]["blocked"] is True
    assert negative["fixture_results"]["support_bundle_executes_runtime"]["blocked"] is True
    assert negative["fixture_results"]["support_bundle_contains_secret_value"]["blocked"] is True

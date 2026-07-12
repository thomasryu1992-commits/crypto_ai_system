from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.non_developer_onboarding_wizard import STATUS_GENERATED_REVIEW_ONLY as P36_STATUS_GENERATED_REVIEW_ONLY
from crypto_ai_system.execution.onboarding_wizard_failure_doctor import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_onboarding_wizard_failure_doctor_report,
    build_p37_negative_fixture_results,
    persist_onboarding_wizard_failure_doctor,
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


def _p36_payloads() -> tuple[dict, dict, dict, str, str, str, list[dict]]:
    report = {
        "status": P36_STATUS_GENERATED_REVIEW_ONLY,
        "blocked": False,
        "waiting": False,
        "operator_final_activation_decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    summary = {
        "status": P36_STATUS_GENERATED_REVIEW_ONLY,
        "blocked": False,
        "waiting": False,
        "runtime_scheduler_enabled": False,
        "live_scaled_execution_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    pack = {
        "status": P36_STATUS_GENERATED_REVIEW_ONLY,
        "operator_final_activation_decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
        "allowed_read_only_commands": ["status", "matrix", "waiting", "no_go", "export_paths"],
        "wizard_executes_runtime": False,
        "wizard_allows_order_submission": False,
    }
    wizard = "# P36 ZIP Drop-in Guide\nRuntime: DISABLED\nScheduler: DISABLED\nOrders: DISABLED\n"
    checklist = "# P36 Checklist\n- [ ] Runtime remains disabled.\n"
    lookup = "# P36 Failure Lookup\nROUTE_BLOCKED_FAIL_CLOSED\n"
    steps = [{"step_id": "status", "executes_runtime": False}]
    return report, summary, pack, wizard, checklist, lookup, steps


def _write_p36_latest(root: Path) -> None:
    report, summary, pack, wizard, checklist, lookup, steps = _p36_payloads()
    latest = root / "storage" / "latest"
    atomic_write_json(latest / "p36_non_developer_onboarding_wizard_report.json", report)
    atomic_write_json(latest / "p36_non_developer_onboarding_wizard_summary.json", summary)
    atomic_write_json(latest / "p36_non_developer_onboarding_wizard_pack.json", pack)
    atomic_write_json(latest / "p36_onboarding_wizard_steps.json", steps)
    (latest / "p36_zip_drop_in_wizard.md").write_text(wizard, encoding="utf-8")
    (latest / "p36_zip_drop_in_checklist.md").write_text(checklist, encoding="utf-8")
    (latest / "p36_failure_message_lookup.md").write_text(lookup, encoding="utf-8")
    atomic_write_json(latest / "p36_operator_onboarding_card.json", {"runtime_authority": False})


def test_p37_waits_when_p36_artifacts_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_onboarding_wizard_failure_doctor_report(root=tmp_path)
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["waiting"] is True
    assert "missing_p36_artifacts" in report["diagnosis_codes"]
    assert report["failure_doctor_executes_runtime"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["order_endpoint_called"] is False
    assert report["secret_value_accessed"] is False


def test_p37_generates_self_diagnosis_when_sources_clean(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p36_latest(tmp_path)
    report = build_onboarding_wizard_failure_doctor_report(root=tmp_path)
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert report["diagnosis_issue_count"] == 0
    assert report["required_lookup_codes_present"] is True
    assert report["all_self_diagnosis_artifacts_safe_review_only"] is True
    assert "status" in report["allowed_read_only_commands"]
    assert "enable" in report["blocked_command_keywords"]
    assert "Self-Diagnosis Pack" in report["self_diagnosis_markdown"]
    assert report["failure_doctor_allows_order_submission"] is False
    assert report["failure_doctor_calls_endpoint"] is False


def test_p37_blocks_unsafe_command_secret_and_runtime_flags(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    p36_report, p36_summary, p36_pack, wizard, checklist, lookup, _steps = _p36_payloads()
    command = build_onboarding_wizard_failure_doctor_report(
        root=tmp_path,
        command_log=["/crypto_live"],
        p36_report=p36_report,
        p36_summary=p36_summary,
        p36_pack=p36_pack,
        p36_wizard_markdown=wizard,
        p36_checklist_markdown=checklist,
        p36_failure_lookup_markdown=lookup,
    )
    assert command["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "blocked_command_attempt" in command["diagnosis_codes"]

    secret = build_onboarding_wizard_failure_doctor_report(
        root=tmp_path,
        p36_report=p36_report,
        p36_summary=p36_summary,
        p36_pack=p36_pack,
        p36_wizard_markdown="BINANCE_API_SECRET=leak",
        p36_checklist_markdown=checklist,
        p36_failure_lookup_markdown=lookup,
    )
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "secret_detected" in secret["diagnosis_codes"]

    runtime = build_onboarding_wizard_failure_doctor_report(
        root=tmp_path,
        p36_report={**p36_report, "live_scaled_execution_enabled": True},
        p36_summary=p36_summary,
        p36_pack=p36_pack,
        p36_wizard_markdown=wizard,
        p36_checklist_markdown=checklist,
        p36_failure_lookup_markdown=lookup,
    )
    assert runtime["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "runtime_flag_truthy" in runtime["diagnosis_codes"]

    endpoint = build_onboarding_wizard_failure_doctor_report(
        root=tmp_path,
        p36_report={**p36_report, "order_endpoint_called": True},
        p36_summary=p36_summary,
        p36_pack=p36_pack,
        p36_wizard_markdown=wizard,
        p36_checklist_markdown=checklist,
        p36_failure_lookup_markdown=lookup,
    )
    assert endpoint["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "endpoint_called" in endpoint["diagnosis_codes"]


def test_p37_persists_self_diagnosis_artifacts_and_registry(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p36_latest(tmp_path)
    report = persist_onboarding_wizard_failure_doctor(load_config(tmp_path))
    latest = tmp_path / "storage" / "latest"
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert (latest / "p37_onboarding_wizard_failure_doctor_report.json").exists()
    assert (latest / "p37_onboarding_wizard_failure_doctor_summary.json").exists()
    assert (latest / "p37_onboarding_wizard_failure_doctor_pack.json").exists()
    assert (latest / "p37_self_diagnosis_results.json").exists()
    assert (latest / "p37_failure_doctor_lookup.json").exists()
    assert (latest / "p37_self_diagnosis_pack.md").exists()
    assert (latest / "p37_self_diagnosis_checklist.md").exists()
    assert (latest / "p37_operator_self_diagnosis_card.json").exists()
    assert (latest / "p37_onboarding_wizard_failure_doctor_registry_record.json").exists()
    summary = read_json(latest / "p37_onboarding_wizard_failure_doctor_summary.json")
    assert summary["all_self_diagnosis_artifacts_safe_review_only"] is True
    assert summary["runtime_scheduler_enabled"] is False
    assert summary["order_endpoint_called"] is False
    assert summary["secret_value_accessed"] is False
    markdown = (latest / "p37_self_diagnosis_pack.md").read_text(encoding="utf-8")
    assert "Detected Issues" in markdown
    assert "Allowed Commands" in markdown


def test_p37_negative_fixture_results_fail_closed_or_waiting(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    negative = build_p37_negative_fixture_results(root=tmp_path)
    assert negative["status"] == "P37_NEGATIVE_FIXTURES_RECORDED"
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert negative["fixture_results"]["no_zip_found"]["waiting"] is True
    assert negative["fixture_results"]["bad_zip_structure"]["waiting"] is True
    assert negative["fixture_results"]["missing_p36_report"]["waiting"] is True
    assert negative["fixture_results"]["p36_blocked"]["blocked"] is True
    assert negative["fixture_results"]["blocked_command_attempt"]["blocked"] is True
    assert negative["fixture_results"]["secret_detected"]["blocked"] is True
    assert negative["fixture_results"]["runtime_flag_truthy"]["blocked"] is True
    assert negative["fixture_results"]["scheduler_enabled"]["blocked"] is True
    assert negative["fixture_results"]["endpoint_called"]["blocked"] is True
    assert negative["fixture_results"]["failure_doctor_executes_runtime"]["blocked"] is True
    assert negative["fixture_results"]["self_diagnosis_allows_runtime"]["blocked"] is True

from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_support_bundle_intake_validator import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALID_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_operator_support_bundle_intake_report,
    build_p39_negative_fixture_results,
    persist_operator_support_bundle_intake_validator,
)
from crypto_ai_system.execution.operator_support_bundle_troubleshooting_export_pack import STATUS_GENERATED_REVIEW_ONLY as P38_STATUS_GENERATED_REVIEW_ONLY


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text("storage:\n  latest_dir: storage/latest\n", encoding="utf-8")


def _manifest() -> list[dict[str, object]]:
    return [
        {"phase": "p38", "filename": "p38_operator_support_bundle_share_packet.json", "exists": True, "sha256": "sha_packet", "size_bytes": 100},
        {"phase": "p37", "filename": "p37_onboarding_wizard_failure_doctor_report.json", "exists": True, "sha256": "sha_p37", "size_bytes": 200},
    ]


def _share_packet() -> dict[str, object]:
    return {
        "share_packet_id": "p38_share_packet_fixture",
        "status": P38_STATUS_GENERATED_REVIEW_ONLY,
        "waiting": False,
        "blocked": False,
        "operator_final_activation_decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
        "source_p37_status": "P37_ONBOARDING_WIZARD_FAILURE_DOCTOR_GENERATED_REVIEW_ONLY",
        "source_p37_diagnosis_issue_count": 0,
        "missing_source_artifacts": [],
        "allowed_read_only_commands": ["status", "matrix", "waiting", "no_go", "export_paths"],
        "blocked_command_keywords": ["enable", "start", "submit", "order", "live", "trade", "activate", "scheduler", "place", "cancel", "runtime"],
        "manifest": _manifest(),
        "redacted_text_excerpts": [],
        "runtime": "DISABLED",
        "scheduler": "DISABLED",
        "orders": "DISABLED",
        "authority": "REVIEW_ONLY",
        "contains_secret_values": False,
        "runtime_authority": False,
    }


def _write_intake_sources(root: Path) -> None:
    latest = root / "storage" / "latest"
    atomic_write_json(latest / "p38_operator_support_bundle_share_packet.json", _share_packet())
    atomic_write_json(latest / "p38_operator_support_bundle_manifest.json", _manifest())


def test_p39_waits_when_share_packet_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_operator_support_bundle_intake_report(root=tmp_path, manifest=_manifest())
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["waiting"] is True
    assert "missing_share_packet" in report["intake_issue_codes"]
    assert report["intake_validator_executes_runtime"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["order_endpoint_called"] is False
    assert report["secret_value_accessed"] is False


def test_p39_validates_clean_share_packet_and_manifest(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_operator_support_bundle_intake_report(root=tmp_path, share_packet=_share_packet(), manifest=_manifest())
    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert report["waiting"] is False
    assert report["blocked"] is False
    assert report["intake_issue_count"] == 0
    assert report["hash_mismatch_count"] == 0
    assert report["share_packet_manifest_entry_count"] == 2
    assert report["external_manifest_entry_count"] == 2
    assert report["intake_validation_results"]["valid_review_only"] is True
    assert report["intake_validation_results"]["runtime"] == "DISABLED"
    assert "status" in report["allowed_read_only_commands"]
    assert "enable" in report["blocked_command_keywords"]


def test_p39_blocks_hash_mismatch_secret_runtime_endpoint_and_authority(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    bad_manifest = [{**_manifest()[0], "sha256": "sha_mismatch"}, _manifest()[1]]
    mismatch = build_operator_support_bundle_intake_report(root=tmp_path, share_packet=_share_packet(), manifest=bad_manifest)
    assert mismatch["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "hash_mismatch" in mismatch["intake_issue_codes"]

    secret = build_operator_support_bundle_intake_report(
        root=tmp_path,
        share_packet=_share_packet(),
        manifest=_manifest(),
        extra_payloads_for_scan=[("bad_secret", "BINANCE_API_SECRET=leak")],
    )
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "secret_detected" in secret["intake_issue_codes"]

    runtime = build_operator_support_bundle_intake_report(
        root=tmp_path,
        share_packet=_share_packet(),
        manifest=_manifest(),
        extra_payloads_for_scan=[("bad_runtime", {"live_scaled_execution_enabled": True})],
    )
    assert runtime["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "runtime_flag_truthy" in runtime["intake_issue_codes"]

    endpoint = build_operator_support_bundle_intake_report(
        root=tmp_path,
        share_packet=_share_packet(),
        manifest=_manifest(),
        extra_payloads_for_scan=[("bad_endpoint", {"order_endpoint_called": True})],
    )
    assert endpoint["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "endpoint_called" in endpoint["intake_issue_codes"]

    authority = build_operator_support_bundle_intake_report(root=tmp_path, share_packet={**_share_packet(), "runtime_authority": True}, manifest=_manifest())
    assert authority["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "runtime_authority_claimed" in authority["intake_issue_codes"]


def test_p39_persists_intake_validator_artifacts_and_registry(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_intake_sources(tmp_path)
    report = persist_operator_support_bundle_intake_validator(load_config(tmp_path))
    latest = tmp_path / "storage" / "latest"
    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert (latest / "p39_operator_support_bundle_intake_validator_report.json").exists()
    assert (latest / "p39_operator_support_bundle_intake_validator_summary.json").exists()
    assert (latest / "p39_operator_support_bundle_intake_validation_results.json").exists()
    assert (latest / "p39_operator_support_bundle_intake_checklist.md").exists()
    assert (latest / "p39_operator_support_bundle_intake_validator.md").exists()
    assert (latest / "p39_operator_support_bundle_intake_validator_negative_fixture_results.json").exists()
    assert (latest / "p39_operator_support_bundle_intake_validator_registry_record.json").exists()
    summary = read_json(latest / "p39_operator_support_bundle_intake_validator_summary.json")
    assert summary["status"] == STATUS_VALID_REVIEW_ONLY
    assert summary["runtime_scheduler_enabled"] is False
    assert summary["order_endpoint_called"] is False
    assert summary["secret_value_accessed"] is False
    validation = read_json(latest / "p39_operator_support_bundle_intake_validation_results.json")
    assert validation["valid_review_only"] is True
    checklist = (latest / "p39_operator_support_bundle_intake_checklist.md").read_text(encoding="utf-8")
    assert "Manifest hashes match share packet" in checklist


def test_p39_negative_fixture_results_fail_closed_or_waiting(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    negative = build_p39_negative_fixture_results(root=tmp_path)
    assert negative["status"] == "P39_NEGATIVE_FIXTURES_RECORDED"
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert negative["fixture_results"]["missing_share_packet"]["waiting"] is True
    assert negative["fixture_results"]["missing_manifest"]["blocked"] is True
    assert negative["fixture_results"]["missing_required_fields"]["blocked"] is True
    assert negative["fixture_results"]["share_packet_blocked_status"]["blocked"] is True
    assert negative["fixture_results"]["share_packet_waiting_status"]["waiting"] is True
    assert negative["fixture_results"]["hash_mismatch"]["blocked"] is True
    assert negative["fixture_results"]["secret_detected"]["blocked"] is True
    assert negative["fixture_results"]["runtime_flag_truthy"]["blocked"] is True
    assert negative["fixture_results"]["endpoint_called"]["blocked"] is True
    assert negative["fixture_results"]["scheduler_enabled"]["blocked"] is True
    assert negative["fixture_results"]["runtime_authority_claimed"]["blocked"] is True
    assert negative["fixture_results"]["contains_secret_value"]["blocked"] is True
    assert negative["fixture_results"]["orders_enabled"]["blocked"] is True
    assert negative["fixture_results"]["intake_validator_executes_runtime"]["blocked"] is True

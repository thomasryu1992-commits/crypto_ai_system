from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_support_bundle_intake_validator import STATUS_VALID_REVIEW_ONLY as P39_STATUS_VALID_REVIEW_ONLY
from crypto_ai_system.execution.operator_support_bundle_round_trip_verification import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VERIFIED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_operator_support_bundle_round_trip_report,
    build_p40_negative_fixture_results,
    persist_operator_support_bundle_round_trip_verification,
)
from crypto_ai_system.execution.operator_support_bundle_troubleshooting_export_pack import STATUS_GENERATED_REVIEW_ONLY as P38_STATUS_GENERATED_REVIEW_ONLY
from crypto_ai_system.utils.audit import sha256_json


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text("storage:\n  latest_dir: storage/latest\n", encoding="utf-8")


def _manifest() -> list[dict[str, object]]:
    return [
        {"phase": "p38", "kind": "json", "filename": "p38_operator_support_bundle_share_packet.json", "exists": True, "sha256": "sha_packet", "size_bytes": 100, "shareable": True},
        {"phase": "p37", "kind": "json", "filename": "p37_onboarding_wizard_failure_doctor_report.json", "exists": True, "sha256": "sha_p37", "size_bytes": 200, "shareable": True},
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


def _p39_report(share_packet: dict[str, object] | None = None, manifest: list[dict[str, object]] | None = None) -> dict[str, object]:
    share_packet = share_packet or _share_packet()
    manifest = manifest or _manifest()
    return {
        "status": P39_STATUS_VALID_REVIEW_ONLY,
        "waiting": False,
        "blocked": False,
        "share_packet_present": True,
        "manifest_present": True,
        "share_packet_status": P38_STATUS_GENERATED_REVIEW_ONLY,
        "share_packet_sha256": sha256_json(share_packet),
        "manifest_sha256": sha256_json(manifest),
        "hash_mismatch_count": 0,
        "hash_mismatches": [],
        "intake_issue_count": 0,
        "intake_issue_codes": [],
        "runtime_flag_truthy": False,
        "scheduler_enabled": False,
        "endpoint_called": False,
        "secret_detected": False,
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }


def _p39_validation() -> dict[str, object]:
    return {
        "status": P39_STATUS_VALID_REVIEW_ONLY,
        "valid_review_only": True,
        "waiting": False,
        "blocked": False,
        "issue_codes": [],
        "runtime": "DISABLED",
        "scheduler": "DISABLED",
        "orders": "DISABLED",
        "authority": "REVIEW_ONLY",
    }


def _write_sources(root: Path) -> None:
    latest = root / "storage" / "latest"
    share = _share_packet()
    manifest = _manifest()
    atomic_write_json(latest / "p38_operator_support_bundle_share_packet.json", share)
    atomic_write_json(latest / "p38_operator_support_bundle_manifest.json", manifest)
    atomic_write_json(latest / "p39_operator_support_bundle_intake_validator_report.json", _p39_report(share, manifest))
    atomic_write_json(latest / "p39_operator_support_bundle_intake_validation_results.json", _p39_validation())


def test_p40_waits_when_p39_report_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_operator_support_bundle_round_trip_report(
        root=tmp_path,
        p38_share_packet=_share_packet(),
        p38_manifest=_manifest(),
        p39_report={},
        p39_validation_results=_p39_validation(),
    )
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["waiting"] is True
    assert "missing_p39_report" in report["round_trip_issue_codes"]
    assert report["round_trip_executes_runtime"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["order_endpoint_called"] is False
    assert report["secret_value_accessed"] is False


def test_p40_verifies_clean_p38_to_p39_round_trip(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    share = _share_packet()
    manifest = _manifest()
    report = build_operator_support_bundle_round_trip_report(
        root=tmp_path,
        p38_share_packet=share,
        p38_manifest=manifest,
        p39_report=_p39_report(share, manifest),
        p39_validation_results=_p39_validation(),
    )
    assert report["status"] == STATUS_VERIFIED_REVIEW_ONLY
    assert report["waiting"] is False
    assert report["blocked"] is False
    assert report["round_trip_issue_count"] == 0
    assert report["p38_share_packet_sha256"] == report["p39_observed_share_packet_sha256"]
    assert report["p38_manifest_sha256"] == report["p39_observed_manifest_sha256"]
    assert report["round_trip_chain"]["review_only"] is True
    assert report["round_trip_chain"]["runtime_authority"] is False
    assert report["round_trip_executes_runtime"] is False


def test_p40_blocks_hash_mismatch_secret_runtime_endpoint_and_authority(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    share = _share_packet()
    manifest = _manifest()
    clean_p39 = _p39_report(share, manifest)

    tampered_share = {**share, "share_packet_id": "tampered"}
    mismatch = build_operator_support_bundle_round_trip_report(
        root=tmp_path,
        p38_share_packet=tampered_share,
        p38_manifest=manifest,
        p39_report=clean_p39,
        p39_validation_results=_p39_validation(),
    )
    assert mismatch["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "share_packet_hash_mismatch" in mismatch["round_trip_issue_codes"]

    secret = build_operator_support_bundle_round_trip_report(
        root=tmp_path,
        p38_share_packet=share,
        p38_manifest=manifest,
        p39_report=clean_p39,
        p39_validation_results=_p39_validation(),
        extra_payloads_for_scan=[("bad_secret", "BINANCE_API_SECRET=leak")],
    )
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "secret_detected" in secret["round_trip_issue_codes"]

    runtime = build_operator_support_bundle_round_trip_report(
        root=tmp_path,
        p38_share_packet=share,
        p38_manifest=manifest,
        p39_report=clean_p39,
        p39_validation_results=_p39_validation(),
        extra_payloads_for_scan=[("bad_runtime", {"live_scaled_execution_enabled": True})],
    )
    assert runtime["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "runtime_flag_truthy" in runtime["round_trip_issue_codes"]

    endpoint = build_operator_support_bundle_round_trip_report(
        root=tmp_path,
        p38_share_packet=share,
        p38_manifest=manifest,
        p39_report=clean_p39,
        p39_validation_results=_p39_validation(),
        extra_payloads_for_scan=[("bad_endpoint", {"order_endpoint_called": True})],
    )
    assert endpoint["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "endpoint_called" in endpoint["round_trip_issue_codes"]

    authority = build_operator_support_bundle_round_trip_report(
        root=tmp_path,
        p38_share_packet={**share, "runtime_authority": True},
        p38_manifest=manifest,
        p39_report=clean_p39,
        p39_validation_results=_p39_validation(),
    )
    assert authority["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "runtime_authority_claimed" in authority["round_trip_issue_codes"]


def test_p40_persists_round_trip_artifacts_and_registry(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_sources(tmp_path)
    report = persist_operator_support_bundle_round_trip_verification(load_config(tmp_path))
    latest = tmp_path / "storage" / "latest"
    assert report["status"] == STATUS_VERIFIED_REVIEW_ONLY
    assert (latest / "p40_operator_support_bundle_round_trip_verification_report.json").exists()
    assert (latest / "p40_operator_support_bundle_round_trip_verification_summary.json").exists()
    assert (latest / "p40_operator_support_bundle_round_trip_chain.json").exists()
    assert (latest / "p40_operator_support_bundle_round_trip_checklist.md").exists()
    assert (latest / "p40_operator_support_bundle_round_trip_verification.md").exists()
    assert (latest / "p40_operator_support_bundle_round_trip_verification_negative_fixture_results.json").exists()
    assert (latest / "p40_operator_support_bundle_round_trip_verification_registry_record.json").exists()
    summary = read_json(latest / "p40_operator_support_bundle_round_trip_verification_summary.json")
    assert summary["status"] == STATUS_VERIFIED_REVIEW_ONLY
    assert summary["runtime_scheduler_enabled"] is False
    assert summary["order_endpoint_called"] is False
    assert summary["secret_value_accessed"] is False
    chain = read_json(latest / "p40_operator_support_bundle_round_trip_chain.json")
    assert chain["review_only"] is True
    checklist = (latest / "p40_operator_support_bundle_round_trip_checklist.md").read_text(encoding="utf-8")
    assert "P38 share packet hash matches P39 observed hash" in checklist


def test_p40_negative_fixture_results_fail_closed_or_waiting(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_sources(tmp_path)
    negative = build_p40_negative_fixture_results(root=tmp_path)
    assert negative["status"] == "P40_NEGATIVE_FIXTURES_RECORDED"
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert negative["fixture_results"]["missing_p38_share_packet"]["waiting"] is True
    assert negative["fixture_results"]["missing_p38_manifest"]["blocked"] is True
    assert negative["fixture_results"]["missing_p39_report"]["waiting"] is True
    assert negative["fixture_results"]["missing_p39_validation_results"]["waiting"] is True
    assert negative["fixture_results"]["share_packet_hash_mismatch"]["blocked"] is True
    assert negative["fixture_results"]["manifest_hash_mismatch"]["blocked"] is True
    assert negative["fixture_results"]["p39_blocked"]["blocked"] is True
    assert negative["fixture_results"]["p39_waiting"]["waiting"] is True
    assert negative["fixture_results"]["p39_validation_not_valid"]["waiting"] is True
    assert negative["fixture_results"]["runtime_flag_truthy"]["blocked"] is True
    assert negative["fixture_results"]["scheduler_enabled"]["blocked"] is True
    assert negative["fixture_results"]["endpoint_called"]["blocked"] is True
    assert negative["fixture_results"]["secret_detected"]["blocked"] is True
    assert negative["fixture_results"]["runtime_authority_claimed"]["blocked"] is True
    assert negative["fixture_results"]["round_trip_executes_runtime"]["blocked"] is True

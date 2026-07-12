from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_evidence_archive_external_review_packet_intake_validator import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALID_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_external_review_packet_intake_validator_report,
    build_p44_negative_fixture_results,
    persist_external_review_packet_intake_validator,
)
from crypto_ai_system.execution.operator_evidence_archive_round_trip_seal import (
    P43_OPERATOR_EVIDENCE_ARCHIVE_ROUND_TRIP_SEAL_VERSION,
    STATUS_SEALED_REVIEW_ONLY as P43_STATUS_SEALED_REVIEW_ONLY,
)
from crypto_ai_system.utils.audit import sha256_json


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text("storage:\n  latest_dir: storage/latest\n", encoding="utf-8")


def _seal_chain() -> dict[str, object]:
    payload = {
        "p41_status": "P41_OPERATOR_EVIDENCE_ARCHIVE_INDEX_GENERATED_REVIEW_ONLY",
        "p42_status": "P42_OPERATOR_EVIDENCE_ARCHIVE_INTAKE_VALIDATOR_VALID_REVIEW_ONLY",
        "p41_archive_index_hash": "archive_index_hash_fixture",
        "observed_p41_archive_index_hash": "archive_index_hash_fixture",
        "p41_audit_trail_chain_hash": "audit_trail_hash_fixture",
        "observed_p41_audit_trail_chain_hash": "audit_trail_hash_fixture",
        "p42_hash_recheck_chain_hash": "p42_hash_recheck_fixture",
        "observed_p42_hash_recheck_chain_hash": "p42_hash_recheck_fixture",
        "p42_intake_issue_count": 0,
        "p42_validation_results_hash": "p42_validation_fixture",
        "review_only": True,
        "runtime_authority": False,
    }
    return {"chain_id": "p43_chain_fixture", **payload, "seal_hash": sha256_json(payload)}


def _packet(chain: dict[str, object]) -> dict[str, object]:
    return {
        "packet_type": "operator_evidence_archive_round_trip_external_review_packet",
        "version": P43_OPERATOR_EVIDENCE_ARCHIVE_ROUND_TRIP_SEAL_VERSION,
        "status": P43_STATUS_SEALED_REVIEW_ONLY,
        "created_at_utc": "2026-07-09T00:00:00Z",
        "review_only": True,
        "runtime_authority": False,
        "decision": "REVIEW_ONLY_EXTERNAL_REVIEW_PACKET_NOT_RUNTIME_AUTHORITY",
        "p41_status": chain["p41_status"],
        "p42_status": chain["p42_status"],
        "seal_hash": chain["seal_hash"],
        "seal_chain_hash": sha256_json(chain),
        "issue_count": 0,
        "issue_codes": [],
        "safe_state": {
            "runtime_scheduler_enabled": False,
            "live_scaled_execution_enabled": False,
            "live_order_submission_allowed": False,
            "order_endpoint_called": False,
            "secret_value_accessed": False,
        },
        "input_hashes": {
            "p41_archive_index_hash": chain["p41_archive_index_hash"],
            "p41_audit_trail_chain_hash": chain["p41_audit_trail_chain_hash"],
            "p42_hash_recheck_chain_hash": chain["p42_hash_recheck_chain_hash"],
        },
        "operator_note": "review only",
    }


def _report(chain: dict[str, object], packet: dict[str, object]) -> dict[str, object]:
    return {
        "status": P43_STATUS_SEALED_REVIEW_ONLY,
        "waiting": False,
        "blocked": False,
        "seal_issue_count": 0,
        "seal_issue_codes": [],
        "seal_hash": packet["seal_hash"],
        "seal_chain_hash": packet["seal_chain_hash"],
        "p41_status": packet["p41_status"],
        "p42_status": packet["p42_status"],
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }


def _summary(report: dict[str, object]) -> dict[str, object]:
    return {
        "status": report["status"],
        "waiting": False,
        "blocked": False,
        "seal_issue_count": 0,
        "seal_issue_codes": [],
        "seal_hash": report["seal_hash"],
        "seal_chain_hash": report["seal_chain_hash"],
    }


def _write_p43(root: Path, report: dict[str, object], summary: dict[str, object], packet: dict[str, object], chain: dict[str, object]) -> None:
    latest = root / "storage" / "latest"
    atomic_write_json(latest / "p43_operator_evidence_archive_round_trip_seal_report.json", report)
    atomic_write_json(latest / "p43_operator_evidence_archive_round_trip_seal_summary.json", summary)
    atomic_write_json(latest / "p43_operator_evidence_archive_external_review_packet.json", packet)
    atomic_write_json(latest / "p43_operator_evidence_archive_round_trip_seal_chain.json", chain)


def _clean_payloads(root: Path) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    chain = _seal_chain()
    packet = _packet(chain)
    report = _report(chain, packet)
    summary = _summary(report)
    _write_p43(root, report, summary, packet, chain)
    return report, summary, packet, chain


def test_p44_waits_when_external_review_packet_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report, summary, packet, chain = _clean_payloads(tmp_path)
    result = build_external_review_packet_intake_validator_report(
        root=tmp_path,
        p43_report=report,
        p43_summary=summary,
        p43_packet={},
        p43_seal_chain=chain,
    )
    assert result["status"] == STATUS_WAITING_REVIEW_ONLY
    assert result["waiting"] is True
    assert "missing_p43_external_review_packet" in result["intake_issue_codes"]
    assert result["external_review_packet_intake_executes_runtime"] is False
    assert result["runtime_scheduler_enabled"] is False
    assert result["order_endpoint_called"] is False
    assert result["secret_value_accessed"] is False


def test_p44_validates_clean_external_review_packet(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report, summary, packet, chain = _clean_payloads(tmp_path)
    result = build_external_review_packet_intake_validator_report(
        root=tmp_path,
        p43_report=report,
        p43_summary=summary,
        p43_packet=packet,
        p43_seal_chain=chain,
    )
    assert result["status"] == STATUS_VALID_REVIEW_ONLY
    assert result["waiting"] is False
    assert result["blocked"] is False
    assert result["intake_issue_count"] == 0
    assert result["packet_hash"]
    assert result["packet_seal_hash"] == result["observed_seal_hash"]
    assert result["packet_seal_chain_hash"] == result["observed_seal_chain_hash"]
    assert result["validation_results"]["valid_review_only"] is True
    assert result["hash_recheck_chain"]["runtime_authority"] is False


def test_p44_blocks_hash_secret_runtime_endpoint_scheduler_authority_and_safe_state(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report, summary, packet, chain = _clean_payloads(tmp_path)

    bad_seal = build_external_review_packet_intake_validator_report(root=tmp_path, p43_report=report, p43_summary=summary, p43_packet={**packet, "seal_hash": "bad_hash"}, p43_seal_chain=chain)
    assert bad_seal["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "seal_hash_mismatch" in bad_seal["intake_issue_codes"]

    bad_chain = build_external_review_packet_intake_validator_report(root=tmp_path, p43_report=report, p43_summary=summary, p43_packet={**packet, "seal_chain_hash": "bad_hash"}, p43_seal_chain=chain)
    assert bad_chain["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "seal_chain_hash_mismatch" in bad_chain["intake_issue_codes"]

    secret = build_external_review_packet_intake_validator_report(root=tmp_path, p43_report=report, p43_summary=summary, p43_packet=packet, p43_seal_chain=chain, extra_payloads_for_scan=[("secret", "BINANCE_API_SECRET=leak")])
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "secret_detected" in secret["intake_issue_codes"]

    runtime = build_external_review_packet_intake_validator_report(root=tmp_path, p43_report=report, p43_summary=summary, p43_packet=packet, p43_seal_chain=chain, extra_payloads_for_scan=[("runtime", {"live_scaled_execution_enabled": True})])
    assert runtime["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "runtime_flag_truthy" in runtime["intake_issue_codes"]

    endpoint = build_external_review_packet_intake_validator_report(root=tmp_path, p43_report=report, p43_summary=summary, p43_packet=packet, p43_seal_chain=chain, extra_payloads_for_scan=[("endpoint", {"order_endpoint_called": True})])
    assert endpoint["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "endpoint_called" in endpoint["intake_issue_codes"]

    scheduler = build_external_review_packet_intake_validator_report(root=tmp_path, p43_report=report, p43_summary=summary, p43_packet=packet, p43_seal_chain=chain, extra_payloads_for_scan=[("scheduler", {"runtime_scheduler_enabled": True})])
    assert scheduler["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "scheduler_enabled" in scheduler["intake_issue_codes"]

    authority = build_external_review_packet_intake_validator_report(root=tmp_path, p43_report=report, p43_summary=summary, p43_packet={**packet, "runtime_authority": True}, p43_seal_chain=chain)
    assert authority["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "runtime_authority_claimed" in authority["intake_issue_codes"]

    safe_state = build_external_review_packet_intake_validator_report(root=tmp_path, p43_report=report, p43_summary=summary, p43_packet={**packet, "safe_state": {**packet["safe_state"], "live_order_submission_allowed": True}}, p43_seal_chain=chain)
    assert safe_state["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "safe_state_truthy" in safe_state["intake_issue_codes"]


def test_p44_persists_intake_artifacts_and_registry(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _clean_payloads(tmp_path)
    latest = tmp_path / "storage" / "latest"
    result = persist_external_review_packet_intake_validator(load_config(tmp_path))
    assert result["status"] == STATUS_VALID_REVIEW_ONLY
    assert result["intake_issue_count"] == 0
    assert (latest / "p44_external_review_packet_intake_validator_report.json").exists()
    assert (latest / "p44_external_review_packet_intake_validator_summary.json").exists()
    assert (latest / "p44_external_review_packet_intake_validation_results.json").exists()
    assert (latest / "p44_external_review_packet_hash_recheck_chain.json").exists()
    assert (latest / "p44_external_review_packet_intake_checklist.md").exists()
    assert (latest / "p44_external_review_packet_intake_validator.md").exists()
    assert (latest / "p44_external_review_packet_intake_validator_negative_fixture_results.json").exists()
    assert (latest / "p44_external_review_packet_intake_validator_registry_record.json").exists()


def test_p44_negative_fixtures_fail_closed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _clean_payloads(tmp_path)
    results = build_p44_negative_fixture_results(tmp_path)
    assert results["status"] == "P44_NEGATIVE_FIXTURES_RECORDED"
    assert results["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert results["runtime_scheduler_enabled"] is False
    assert results["order_endpoint_called"] is False
    assert results["secret_value_accessed"] is False

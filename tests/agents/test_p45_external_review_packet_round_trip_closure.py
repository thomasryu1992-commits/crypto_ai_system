from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_evidence_archive_external_review_packet_intake_validator import STATUS_VALID_REVIEW_ONLY as P44_STATUS_VALID_REVIEW_ONLY
from crypto_ai_system.execution.operator_evidence_archive_external_review_packet_round_trip_closure import (
    ALLOWED_REVIEWER_DECISIONS,
    PENDING_REVIEW_DECISION,
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_TEMPLATE_READY_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_external_review_packet_round_trip_closure_report,
    build_p45_negative_fixture_results,
    persist_external_review_packet_round_trip_closure,
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


def _p43_chain() -> dict[str, object]:
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


def _p43_packet(chain: dict[str, object]) -> dict[str, object]:
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


def _p44_report(packet: dict[str, object]) -> dict[str, object]:
    p44_chain = _p44_chain(packet)
    return {
        "status": P44_STATUS_VALID_REVIEW_ONLY,
        "waiting": False,
        "blocked": False,
        "intake_issue_count": 0,
        "intake_issue_codes": [],
        "packet_hash": sha256_json(packet),
        "packet_seal_hash": packet["seal_hash"],
        "observed_seal_hash": packet["seal_hash"],
        "packet_seal_chain_hash": packet["seal_chain_hash"],
        "observed_seal_chain_hash": packet["seal_chain_hash"],
        "hash_recheck_chain_hash": p44_chain["hash_recheck_chain_hash"],
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }


def _p44_validation(packet: dict[str, object]) -> dict[str, object]:
    return {
        "status": P44_STATUS_VALID_REVIEW_ONLY,
        "valid_review_only": True,
        "waiting": False,
        "blocked": False,
        "intake_issue_count": 0,
        "intake_issue_codes": [],
        "packet_hash": sha256_json(packet),
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
        "runtime_authority": False,
    }


def _p44_chain(packet: dict[str, object]) -> dict[str, object]:
    payload = {
        "p43_status": P43_STATUS_SEALED_REVIEW_ONLY,
        "packet_status": P43_STATUS_SEALED_REVIEW_ONLY,
        "packet_hash": sha256_json(packet),
        "reported_seal_hash": packet["seal_hash"],
        "observed_seal_hash": packet["seal_hash"],
        "reported_seal_chain_hash": packet["seal_chain_hash"],
        "observed_seal_chain_hash": packet["seal_chain_hash"],
        "safe_state_hash": sha256_json(packet["safe_state"]),
        "intake_issue_count": 0,
        "review_only": True,
        "runtime_authority": False,
    }
    return {"chain_id": "p44_hash_recheck_fixture", **payload, "hash_recheck_chain_hash": sha256_json(payload)}


def _write_inputs(root: Path) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    chain = _p43_chain()
    packet = _p43_packet(chain)
    report = _p44_report(packet)
    validation = _p44_validation(packet)
    p44_chain = _p44_chain(packet)
    latest = root / "storage" / "latest"
    atomic_write_json(latest / "p43_operator_evidence_archive_external_review_packet.json", packet)
    atomic_write_json(latest / "p43_operator_evidence_archive_round_trip_seal_chain.json", chain)
    atomic_write_json(latest / "p44_external_review_packet_intake_validator_report.json", report)
    atomic_write_json(latest / "p44_external_review_packet_intake_validation_results.json", validation)
    atomic_write_json(latest / "p44_external_review_packet_hash_recheck_chain.json", p44_chain)
    return packet, chain, report, p44_chain


def test_p45_waits_when_p44_report_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    packet, chain, report, p44_chain = _write_inputs(tmp_path)
    result = build_external_review_packet_round_trip_closure_report(
        root=tmp_path,
        p43_packet=packet,
        p43_seal_chain=chain,
        p44_report={},
        p44_validation_results=_p44_validation(packet),
        p44_hash_recheck_chain=p44_chain,
    )
    assert result["status"] == STATUS_WAITING_REVIEW_ONLY
    assert result["waiting"] is True
    assert "missing_p44_report" in result["closure_issue_codes"]
    assert result["reviewer_acceptance_executes_runtime"] is False
    assert result["runtime_scheduler_enabled"] is False
    assert result["order_endpoint_called"] is False
    assert result["secret_value_accessed"] is False


def test_p45_generates_clean_reviewer_acceptance_template(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    packet, chain, report, p44_chain = _write_inputs(tmp_path)
    result = build_external_review_packet_round_trip_closure_report(
        root=tmp_path,
        p43_packet=packet,
        p43_seal_chain=chain,
        p44_report=report,
        p44_validation_results=_p44_validation(packet),
        p44_hash_recheck_chain=p44_chain,
    )
    assert result["status"] == STATUS_TEMPLATE_READY_REVIEW_ONLY
    assert result["waiting"] is False
    assert result["blocked"] is False
    assert result["closure_issue_count"] == 0
    assert result["reviewer_decision"] == PENDING_REVIEW_DECISION
    assert tuple(result["allowed_reviewer_decisions"]) == ALLOWED_REVIEWER_DECISIONS
    assert result["validation_results"]["template_ready_review_only"] is True
    assert result["closure_chain"]["runtime_authority"] is False


def test_p45_blocks_bad_decision_hash_secret_runtime_endpoint_scheduler_authority(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    packet, chain, report, p44_chain = _write_inputs(tmp_path)
    validation = _p44_validation(packet)
    clean = build_external_review_packet_round_trip_closure_report(root=tmp_path, p43_packet=packet, p43_seal_chain=chain, p44_report=report, p44_validation_results=validation, p44_hash_recheck_chain=p44_chain)
    base_template = read_json(tmp_path / "storage" / "latest" / "p45_reviewer_acceptance_template.json", default={}) or {}
    if not base_template:
        # Use the generated template from persistence-style fields by calling once through persist below if needed.
        persist_external_review_packet_round_trip_closure(load_config(tmp_path))
        base_template = read_json(tmp_path / "storage" / "latest" / "p45_reviewer_acceptance_template.json", default={})

    bad_decision = build_external_review_packet_round_trip_closure_report(root=tmp_path, p43_packet=packet, p43_seal_chain=chain, p44_report=report, p44_validation_results=validation, p44_hash_recheck_chain=p44_chain, reviewer_acceptance_template={**base_template, "reviewer_decision": "APPROVE_RUNTIME"})
    assert bad_decision["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "reviewer_decision_not_allowed" in bad_decision["closure_issue_codes"]

    bad_hash = build_external_review_packet_round_trip_closure_report(root=tmp_path, p43_packet=packet, p43_seal_chain=chain, p44_report=report, p44_validation_results=validation, p44_hash_recheck_chain=p44_chain, reviewer_acceptance_template={**base_template, "template_hash": "bad_hash"})
    assert bad_hash["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "template_hash_mismatch" in bad_hash["closure_issue_codes"]

    secret = build_external_review_packet_round_trip_closure_report(root=tmp_path, p43_packet=packet, p43_seal_chain=chain, p44_report=report, p44_validation_results=validation, p44_hash_recheck_chain=p44_chain, extra_payloads_for_scan=[("secret", "BINANCE_API_SECRET=leak")])
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "secret_detected" in secret["closure_issue_codes"]

    runtime = build_external_review_packet_round_trip_closure_report(root=tmp_path, p43_packet=packet, p43_seal_chain=chain, p44_report=report, p44_validation_results=validation, p44_hash_recheck_chain=p44_chain, extra_payloads_for_scan=[("runtime", {"live_scaled_execution_enabled": True})])
    assert runtime["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "runtime_flag_truthy" in runtime["closure_issue_codes"]

    endpoint = build_external_review_packet_round_trip_closure_report(root=tmp_path, p43_packet=packet, p43_seal_chain=chain, p44_report=report, p44_validation_results=validation, p44_hash_recheck_chain=p44_chain, extra_payloads_for_scan=[("endpoint", {"order_endpoint_called": True})])
    assert endpoint["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "endpoint_called" in endpoint["closure_issue_codes"]

    scheduler = build_external_review_packet_round_trip_closure_report(root=tmp_path, p43_packet=packet, p43_seal_chain=chain, p44_report=report, p44_validation_results=validation, p44_hash_recheck_chain=p44_chain, extra_payloads_for_scan=[("scheduler", {"runtime_scheduler_enabled": True})])
    assert scheduler["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "scheduler_enabled" in scheduler["closure_issue_codes"]

    authority = build_external_review_packet_round_trip_closure_report(root=tmp_path, p43_packet=packet, p43_seal_chain=chain, p44_report=report, p44_validation_results=validation, p44_hash_recheck_chain=p44_chain, reviewer_acceptance_template={**base_template, "runtime_authority": True})
    assert authority["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "runtime_authority_claimed" in authority["closure_issue_codes"]


def test_p45_persists_outputs_and_negative_fixtures(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_inputs(tmp_path)
    report = persist_external_review_packet_round_trip_closure(load_config(tmp_path))
    assert report["status"] == STATUS_TEMPLATE_READY_REVIEW_ONLY
    latest = tmp_path / "storage" / "latest"
    assert (latest / "p45_external_review_packet_round_trip_closure_report.json").exists()
    assert (latest / "p45_reviewer_acceptance_template.json").exists()
    assert (latest / "p45_external_review_packet_closure_chain.json").exists()
    negative = read_json(latest / "p45_external_review_packet_round_trip_closure_negative_fixture_results.json", default={})
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert negative["fixture_count"] >= 12
    direct_negative = build_p45_negative_fixture_results(tmp_path)
    assert direct_negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True

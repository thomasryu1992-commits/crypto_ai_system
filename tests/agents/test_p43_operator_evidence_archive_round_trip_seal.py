from __future__ import annotations

import hashlib
from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_evidence_archive_index_audit_trail import STATUS_GENERATED_REVIEW_ONLY as P41_STATUS_GENERATED_REVIEW_ONLY
from crypto_ai_system.execution.operator_evidence_archive_intake_validator import (
    STATUS_VALID_REVIEW_ONLY as P42_STATUS_VALID_REVIEW_ONLY,
    build_operator_evidence_archive_intake_validator_report,
)
from crypto_ai_system.execution.operator_evidence_archive_round_trip_seal import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_SEALED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_operator_evidence_archive_round_trip_seal_report,
    build_p43_negative_fixture_results,
    persist_operator_evidence_archive_round_trip_seal,
)
from crypto_ai_system.utils.audit import sha256_json


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text("storage:\n  latest_dir: storage/latest\n", encoding="utf-8")


def _write_file(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _archive_index(root: Path) -> list[dict[str, object]]:
    latest = root / "storage" / "latest"
    sha1 = _write_file(latest / "p33_a.json", '{"review_only": true, "runtime_authority": false}\n')
    sha2 = _write_file(latest / "p40_a.json", '{"review_only": true, "runtime_authority": false}\n')
    return [
        {"ordinal": 1, "phase": "p33", "kind": "json", "filename": "p33_a.json", "exists": True, "size_bytes": 47, "sha256": sha1, "artifact_payload_sha256": "payload1", "review_only": True, "runtime_authority": False},
        {"ordinal": 2, "phase": "p40", "kind": "json", "filename": "p40_a.json", "exists": True, "size_bytes": 47, "sha256": sha2, "artifact_payload_sha256": "payload2", "review_only": True, "runtime_authority": False},
    ]


def _p41_chain(index: list[dict[str, object]]) -> dict[str, object]:
    return {
        "chain_id": "p41_chain_fixture",
        "archive_index_hash": sha256_json(index),
        "p40_round_trip_hash": "round_trip_fixture_hash",
        "review_only": True,
        "runtime_authority": False,
    }


def _p41_report(index: list[dict[str, object]], chain: dict[str, object]) -> dict[str, object]:
    return {
        "status": P41_STATUS_GENERATED_REVIEW_ONLY,
        "waiting": False,
        "blocked": False,
        "archive_issue_count": 0,
        "archive_issue_codes": [],
        "archive_index_hash": sha256_json(index),
        "audit_trail_chain_hash": sha256_json(chain),
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }


def _p41_summary(report: dict[str, object]) -> dict[str, object]:
    return {
        "status": report["status"],
        "waiting": False,
        "blocked": False,
        "archive_issue_count": 0,
        "archive_issue_codes": [],
        "archive_index_hash": report["archive_index_hash"],
        "audit_trail_chain_hash": report["audit_trail_chain_hash"],
    }


def _write_p41(root: Path, index: list[dict[str, object]], chain: dict[str, object], report: dict[str, object], summary: dict[str, object]) -> None:
    latest = root / "storage" / "latest"
    atomic_write_json(latest / "p41_operator_evidence_archive_index_report.json", report)
    atomic_write_json(latest / "p41_operator_evidence_archive_index_summary.json", summary)
    atomic_write_json(latest / "p41_operator_evidence_archive_index.json", index)
    atomic_write_json(latest / "p41_operator_evidence_audit_trail_chain.json", chain)
    for filename in (
        "p41_operator_evidence_archive_index.csv",
        "p41_operator_evidence_archive_checklist.md",
        "p41_operator_evidence_audit_trail.md",
    ):
        (latest / filename).write_text("review_only=true\nruntime_authority=false\n", encoding="utf-8")
    atomic_write_json(latest / "p41_operator_evidence_archive_index_negative_fixture_results.json", {"status": "P41_NEGATIVE_FIXTURES_RECORDED"})
    atomic_write_json(latest / "p41_operator_evidence_archive_index_registry_record.json", {"status": P41_STATUS_GENERATED_REVIEW_ONLY})


def _write_p42(root: Path, p42_report: dict[str, object]) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    latest = root / "storage" / "latest"
    validation = dict(p42_report["validation_results"])
    hash_chain = dict(p42_report["hash_recheck_chain"])
    summary = {
        "status": p42_report["status"],
        "waiting": p42_report["waiting"],
        "blocked": p42_report["blocked"],
        "intake_issue_count": p42_report["intake_issue_count"],
        "intake_issue_codes": p42_report["intake_issue_codes"],
        "hash_recheck_chain_hash": p42_report["hash_recheck_chain_hash"],
    }
    atomic_write_json(latest / "p42_operator_evidence_archive_intake_validator_report.json", p42_report)
    atomic_write_json(latest / "p42_operator_evidence_archive_intake_validator_summary.json", summary)
    atomic_write_json(latest / "p42_operator_evidence_archive_intake_validation_results.json", validation)
    atomic_write_json(latest / "p42_operator_evidence_archive_hash_recheck_chain.json", hash_chain)
    return summary, validation, hash_chain


def _clean_payloads(root: Path) -> tuple[list[dict[str, object]], dict[str, object], dict[str, object], dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    index = _archive_index(root)
    p41_chain = _p41_chain(index)
    p41_report = _p41_report(index, p41_chain)
    p41_summary = _p41_summary(p41_report)
    _write_p41(root, index, p41_chain, p41_report, p41_summary)
    p42_report = build_operator_evidence_archive_intake_validator_report(root=root, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=index, p41_audit_trail_chain=p41_chain)
    p42_summary, p42_validation, p42_hash_chain = _write_p42(root, p42_report)
    return index, p41_chain, p41_report, p41_summary, p42_report, p42_summary, p42_hash_chain


def test_p43_waits_when_p42_report_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    index, p41_chain, p41_report, p41_summary, p42_report, p42_summary, p42_hash_chain = _clean_payloads(tmp_path)
    report = build_operator_evidence_archive_round_trip_seal_report(
        root=tmp_path,
        p41_report=p41_report,
        p41_summary=p41_summary,
        p41_archive_index=index,
        p41_audit_trail_chain=p41_chain,
        p42_report={},
        p42_summary=p42_summary,
        p42_validation_results=p42_report["validation_results"],
        p42_hash_recheck_chain=p42_hash_chain,
    )
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["waiting"] is True
    assert "missing_p42_report" in report["seal_issue_codes"]
    assert report["round_trip_seal_executes_runtime"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["order_endpoint_called"] is False
    assert report["secret_value_accessed"] is False


def test_p43_seals_clean_p41_p42_round_trip(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    index, p41_chain, p41_report, p41_summary, p42_report, p42_summary, p42_hash_chain = _clean_payloads(tmp_path)
    report = build_operator_evidence_archive_round_trip_seal_report(
        root=tmp_path,
        p41_report=p41_report,
        p41_summary=p41_summary,
        p41_archive_index=index,
        p41_audit_trail_chain=p41_chain,
        p42_report=p42_report,
        p42_summary=p42_summary,
        p42_validation_results=p42_report["validation_results"],
        p42_hash_recheck_chain=p42_hash_chain,
    )
    assert report["status"] == STATUS_SEALED_REVIEW_ONLY
    assert report["waiting"] is False
    assert report["blocked"] is False
    assert report["seal_issue_count"] == 0
    assert report["p42_status"] == P42_STATUS_VALID_REVIEW_ONLY
    assert report["seal_hash"]
    assert report["seal_chain_hash"]
    assert report["external_review_packet"]["review_only"] is True
    assert report["external_review_packet"]["runtime_authority"] is False


def test_p43_blocks_mismatch_secret_runtime_endpoint_scheduler_and_authority(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    index, p41_chain, p41_report, p41_summary, p42_report, p42_summary, p42_hash_chain = _clean_payloads(tmp_path)
    validation = p42_report["validation_results"]

    mismatch = build_operator_evidence_archive_round_trip_seal_report(root=tmp_path, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=index, p41_audit_trail_chain=p41_chain, p42_report={**p42_report, "hash_recheck_chain_hash": "bad_hash"}, p42_summary=p42_summary, p42_validation_results=validation, p42_hash_recheck_chain=p42_hash_chain)
    assert mismatch["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "p42_hash_recheck_chain_hash_mismatch" in mismatch["seal_issue_codes"]

    secret = build_operator_evidence_archive_round_trip_seal_report(root=tmp_path, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=index, p41_audit_trail_chain=p41_chain, p42_report=p42_report, p42_summary=p42_summary, p42_validation_results=validation, p42_hash_recheck_chain=p42_hash_chain, extra_payloads_for_scan=[("secret", "BINANCE_API_SECRET=leak")])
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "secret_detected" in secret["seal_issue_codes"]

    runtime = build_operator_evidence_archive_round_trip_seal_report(root=tmp_path, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=index, p41_audit_trail_chain=p41_chain, p42_report=p42_report, p42_summary=p42_summary, p42_validation_results=validation, p42_hash_recheck_chain=p42_hash_chain, extra_payloads_for_scan=[("runtime", {"live_scaled_execution_enabled": True})])
    assert runtime["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "runtime_flag_truthy" in runtime["seal_issue_codes"]

    endpoint = build_operator_evidence_archive_round_trip_seal_report(root=tmp_path, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=index, p41_audit_trail_chain=p41_chain, p42_report=p42_report, p42_summary=p42_summary, p42_validation_results=validation, p42_hash_recheck_chain=p42_hash_chain, extra_payloads_for_scan=[("endpoint", {"order_endpoint_called": True})])
    assert endpoint["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "endpoint_called" in endpoint["seal_issue_codes"]

    scheduler = build_operator_evidence_archive_round_trip_seal_report(root=tmp_path, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=index, p41_audit_trail_chain=p41_chain, p42_report=p42_report, p42_summary=p42_summary, p42_validation_results=validation, p42_hash_recheck_chain=p42_hash_chain, extra_payloads_for_scan=[("scheduler", {"runtime_scheduler_enabled": True})])
    assert scheduler["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "scheduler_enabled" in scheduler["seal_issue_codes"]

    authority = build_operator_evidence_archive_round_trip_seal_report(root=tmp_path, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=index, p41_audit_trail_chain={**p41_chain, "runtime_authority": True}, p42_report=p42_report, p42_summary=p42_summary, p42_validation_results=validation, p42_hash_recheck_chain=p42_hash_chain)
    assert authority["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "runtime_authority_claimed" in authority["seal_issue_codes"]


def test_p43_persists_seal_artifacts_and_registry(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _clean_payloads(tmp_path)
    latest = tmp_path / "storage" / "latest"
    report = persist_operator_evidence_archive_round_trip_seal(load_config(tmp_path))
    assert report["status"] == STATUS_SEALED_REVIEW_ONLY
    assert report["seal_issue_count"] == 0
    assert (latest / "p43_operator_evidence_archive_round_trip_seal_report.json").exists()
    assert (latest / "p43_operator_evidence_archive_round_trip_seal_summary.json").exists()
    assert (latest / "p43_operator_evidence_archive_external_review_packet.json").exists()
    assert (latest / "p43_operator_evidence_archive_round_trip_seal_chain.json").exists()
    assert (latest / "p43_operator_evidence_archive_round_trip_seal_checklist.md").exists()
    assert (latest / "p43_operator_evidence_archive_external_review_packet.md").exists()
    assert (latest / "p43_operator_evidence_archive_round_trip_seal_negative_fixture_results.json").exists()
    assert (latest / "p43_operator_evidence_archive_round_trip_seal_registry_record.json").exists()


def test_p43_negative_fixtures_fail_closed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _clean_payloads(tmp_path)
    results = build_p43_negative_fixture_results(tmp_path)
    assert results["status"] == "P43_NEGATIVE_FIXTURES_RECORDED"
    assert results["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert results["runtime_scheduler_enabled"] is False
    assert results["order_endpoint_called"] is False
    assert results["secret_value_accessed"] is False

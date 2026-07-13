from __future__ import annotations

import hashlib
from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_evidence_archive_index_audit_trail import STATUS_GENERATED_REVIEW_ONLY as P41_STATUS_GENERATED_REVIEW_ONLY
from crypto_ai_system.execution.operator_evidence_archive_intake_validator import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALID_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_operator_evidence_archive_intake_validator_report,
    build_p42_negative_fixture_results,
    persist_operator_evidence_archive_intake_validator,
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


def _write_required_p41_files(root: Path, index: list[dict[str, object]], chain: dict[str, object], p41_report: dict[str, object], p41_summary: dict[str, object]) -> None:
    latest = root / "storage" / "latest"
    atomic_write_json(latest / "p41_operator_evidence_archive_index_report.json", p41_report)
    atomic_write_json(latest / "p41_operator_evidence_archive_index_summary.json", p41_summary)
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


def test_p42_waits_when_p41_report_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    index = _archive_index(tmp_path)
    chain = _p41_chain(index)
    report = build_operator_evidence_archive_intake_validator_report(root=tmp_path, p41_report={}, p41_summary=_p41_summary(_p41_report(index, chain)), p41_archive_index=index, p41_audit_trail_chain=chain)
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["waiting"] is True
    assert "missing_p41_report" in report["intake_issue_codes"]
    assert report["archive_intake_executes_runtime"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["order_endpoint_called"] is False
    assert report["secret_value_accessed"] is False


def test_p42_validates_clean_archive_hashes(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    index = _archive_index(tmp_path)
    chain = _p41_chain(index)
    p41_report = _p41_report(index, chain)
    p41_summary = _p41_summary(p41_report)
    _write_required_p41_files(tmp_path, index, chain, p41_report, p41_summary)
    report = build_operator_evidence_archive_intake_validator_report(root=tmp_path, p41_report=p41_report, p41_summary=p41_summary, p41_archive_index=index, p41_audit_trail_chain=chain)
    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert report["waiting"] is False
    assert report["blocked"] is False
    assert report["intake_issue_count"] == 0
    assert report["observed_archive_index_hash"] == p41_report["archive_index_hash"]
    assert report["observed_audit_trail_chain_hash"] == p41_report["audit_trail_chain_hash"]
    assert report["archive_entry_hash_mismatch_count"] == 0
    assert report["hash_recheck_chain_hash"]
    assert report["hash_recheck_chain"]["review_only"] is True
    assert report["hash_recheck_chain"]["runtime_authority"] is False


def test_p42_blocks_hash_secret_runtime_endpoint_scheduler_and_authority(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    index = _archive_index(tmp_path)
    chain = _p41_chain(index)
    p41_report = _p41_report(index, chain)
    mismatch = build_operator_evidence_archive_intake_validator_report(root=tmp_path, p41_report={**p41_report, "archive_index_hash": "bad_hash"}, p41_summary=_p41_summary(p41_report), p41_archive_index=index, p41_audit_trail_chain=chain)
    assert mismatch["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "archive_index_hash_mismatch" in mismatch["intake_issue_codes"]

    bad_index = [dict(item) for item in index]
    bad_index[0] = {**bad_index[0], "sha256": "tampered"}
    entry = build_operator_evidence_archive_intake_validator_report(root=tmp_path, p41_report=p41_report, p41_summary=_p41_summary(p41_report), p41_archive_index=bad_index, p41_audit_trail_chain=chain)
    assert entry["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "archive_entry_hash_mismatch" in entry["intake_issue_codes"]

    secret = build_operator_evidence_archive_intake_validator_report(root=tmp_path, p41_report=p41_report, p41_summary=_p41_summary(p41_report), p41_archive_index=index, p41_audit_trail_chain=chain, extra_payloads_for_scan=[("bad_secret", "BINANCE_API_SECRET=leak")])
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "secret_detected" in secret["intake_issue_codes"]

    runtime = build_operator_evidence_archive_intake_validator_report(root=tmp_path, p41_report=p41_report, p41_summary=_p41_summary(p41_report), p41_archive_index=index, p41_audit_trail_chain=chain, extra_payloads_for_scan=[("bad_runtime", {"live_scaled_execution_enabled": True})])
    assert runtime["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "runtime_flag_truthy" in runtime["intake_issue_codes"]

    endpoint = build_operator_evidence_archive_intake_validator_report(root=tmp_path, p41_report=p41_report, p41_summary=_p41_summary(p41_report), p41_archive_index=index, p41_audit_trail_chain=chain, extra_payloads_for_scan=[("bad_endpoint", {"order_endpoint_called": True})])
    assert endpoint["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "endpoint_called" in endpoint["intake_issue_codes"]

    scheduler = build_operator_evidence_archive_intake_validator_report(root=tmp_path, p41_report=p41_report, p41_summary=_p41_summary(p41_report), p41_archive_index=index, p41_audit_trail_chain=chain, extra_payloads_for_scan=[("bad_scheduler", {"runtime_scheduler_enabled": True})])
    assert scheduler["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "scheduler_enabled" in scheduler["intake_issue_codes"]

    authority = build_operator_evidence_archive_intake_validator_report(root=tmp_path, p41_report=p41_report, p41_summary=_p41_summary(p41_report), p41_archive_index=index, p41_audit_trail_chain={**chain, "runtime_authority": True})
    assert authority["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "runtime_authority_claimed" in authority["intake_issue_codes"]


def test_p42_persists_intake_artifacts_and_registry(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    latest = tmp_path / "storage" / "latest"
    index = _archive_index(tmp_path)
    chain = _p41_chain(index)
    p41_report = _p41_report(index, chain)
    p41_summary = _p41_summary(p41_report)
    _write_required_p41_files(tmp_path, index, chain, p41_report, p41_summary)

    report = persist_operator_evidence_archive_intake_validator(load_config(tmp_path))
    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert report["intake_issue_count"] == 0
    assert (latest / "p42_operator_evidence_archive_intake_validator_report.json").exists()
    assert (latest / "p42_operator_evidence_archive_intake_validator_summary.json").exists()
    assert (latest / "p42_operator_evidence_archive_intake_validation_results.json").exists()
    assert (latest / "p42_operator_evidence_archive_hash_recheck_chain.json").exists()
    assert (latest / "p42_operator_evidence_archive_intake_checklist.md").exists()
    assert (latest / "p42_operator_evidence_archive_intake_validator.md").exists()
    assert (latest / "p42_operator_evidence_archive_intake_validator_negative_fixture_results.json").exists()
    assert (latest / "p42_operator_evidence_archive_intake_validator_registry_record.json").exists()


def test_p42_negative_fixtures_fail_closed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    latest = tmp_path / "storage" / "latest"
    index = _archive_index(tmp_path)
    chain = _p41_chain(index)
    p41_report = _p41_report(index, chain)
    p41_summary = _p41_summary(p41_report)
    atomic_write_json(latest / "p41_operator_evidence_archive_index_report.json", p41_report)
    atomic_write_json(latest / "p41_operator_evidence_archive_index_summary.json", p41_summary)
    atomic_write_json(latest / "p41_operator_evidence_archive_index.json", index)
    atomic_write_json(latest / "p41_operator_evidence_audit_trail_chain.json", chain)
    results = build_p42_negative_fixture_results(tmp_path)
    assert results["status"] == "P42_NEGATIVE_FIXTURES_RECORDED"
    assert results["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert results["runtime_scheduler_enabled"] is False
    assert results["order_endpoint_called"] is False
    assert results["secret_value_accessed"] is False

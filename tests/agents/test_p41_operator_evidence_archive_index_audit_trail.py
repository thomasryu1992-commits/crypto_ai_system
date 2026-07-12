from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_evidence_archive_index_audit_trail import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_operator_evidence_archive_index_report,
    build_p41_negative_fixture_results,
    persist_operator_evidence_archive_index,
)
from crypto_ai_system.execution.operator_support_bundle_round_trip_verification import STATUS_VERIFIED_REVIEW_ONLY as P40_STATUS_VERIFIED_REVIEW_ONLY


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text("storage:\n  latest_dir: storage/latest\n", encoding="utf-8")


def _p40_report() -> dict[str, object]:
    return {
        "status": P40_STATUS_VERIFIED_REVIEW_ONLY,
        "waiting": False,
        "blocked": False,
        "round_trip_issue_count": 0,
        "round_trip_issue_codes": [],
        "round_trip_hash": "round_trip_fixture_hash",
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }


def _p40_chain() -> dict[str, object]:
    return {
        "chain_id": "p40_chain_fixture",
        "p38_share_packet_sha256": "share_sha",
        "p38_manifest_sha256": "manifest_sha",
        "p39_observed_share_packet_sha256": "share_sha",
        "p39_observed_manifest_sha256": "manifest_sha",
        "review_only": True,
        "runtime_authority": False,
    }


def _index() -> list[dict[str, object]]:
    return [
        {"ordinal": 1, "phase": "p33", "kind": "json", "filename": "p33_a.json", "exists": True, "sha256": "sha1", "artifact_payload_sha256": "payload1", "review_only": True, "runtime_authority": False},
        {"ordinal": 2, "phase": "p40", "kind": "json", "filename": "p40_a.json", "exists": True, "sha256": "sha2", "artifact_payload_sha256": "payload2", "review_only": True, "runtime_authority": False},
    ]


def test_p41_waits_when_p40_report_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_operator_evidence_archive_index_report(root=tmp_path, archive_index=_index(), p40_report={}, p40_chain=_p40_chain())
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert report["waiting"] is True
    assert "missing_p40_report" in report["archive_issue_codes"]
    assert report["archive_index_executes_runtime"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["order_endpoint_called"] is False
    assert report["secret_value_accessed"] is False


def test_p41_generates_clean_archive_index(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_operator_evidence_archive_index_report(root=tmp_path, archive_index=_index(), p40_report=_p40_report(), p40_chain=_p40_chain())
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert report["waiting"] is False
    assert report["blocked"] is False
    assert report["archive_issue_count"] == 0
    assert report["expected_archive_artifact_count"] == 2
    assert report["present_archive_artifact_count"] == 2
    assert report["missing_archive_artifact_count"] == 0
    assert report["archive_index_hash"]
    assert report["audit_trail_chain_hash"]
    assert report["audit_trail_chain"]["review_only"] is True
    assert report["audit_trail_chain"]["runtime_authority"] is False


def test_p41_blocks_secret_runtime_endpoint_scheduler_and_authority(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    secret = build_operator_evidence_archive_index_report(root=tmp_path, archive_index=_index(), p40_report=_p40_report(), p40_chain=_p40_chain(), extra_payloads_for_scan=[("bad_secret", "BINANCE_API_SECRET=leak")])
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "secret_detected" in secret["archive_issue_codes"]

    runtime = build_operator_evidence_archive_index_report(root=tmp_path, archive_index=_index(), p40_report=_p40_report(), p40_chain=_p40_chain(), extra_payloads_for_scan=[("bad_runtime", {"live_scaled_execution_enabled": True})])
    assert runtime["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "runtime_flag_truthy" in runtime["archive_issue_codes"]

    endpoint = build_operator_evidence_archive_index_report(root=tmp_path, archive_index=_index(), p40_report=_p40_report(), p40_chain=_p40_chain(), extra_payloads_for_scan=[("bad_endpoint", {"order_endpoint_called": True})])
    assert endpoint["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "endpoint_called" in endpoint["archive_issue_codes"]

    scheduler = build_operator_evidence_archive_index_report(root=tmp_path, archive_index=_index(), p40_report=_p40_report(), p40_chain=_p40_chain(), extra_payloads_for_scan=[("bad_scheduler", {"runtime_scheduler_enabled": True})])
    assert scheduler["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "scheduler_enabled" in scheduler["archive_issue_codes"]

    authority = build_operator_evidence_archive_index_report(root=tmp_path, archive_index=_index(), p40_report=_p40_report(), p40_chain={**_p40_chain(), "runtime_authority": True})
    assert authority["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "runtime_authority_claimed" in authority["archive_issue_codes"]


def test_p41_persists_archive_artifacts_and_registry(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    latest = tmp_path / "storage" / "latest"
    # Provide a minimal real subset by writing all expected artifact filenames discovered from the source list in the module.
    from crypto_ai_system.execution import operator_evidence_archive_index_audit_trail as p41

    for _phase, kind, filename in p41._SOURCE_ARTIFACTS:  # noqa: SLF001 - test fixture uses internal constant intentionally.
        if kind == "json":
            atomic_write_json(latest / filename, {"filename": filename, "review_only": True, "runtime_authority": False})
        else:
            (latest / filename).write_text(f"{filename}\nreview_only=true\nruntime_authority=false\n", encoding="utf-8")
    atomic_write_json(latest / "p40_operator_support_bundle_round_trip_verification_report.json", _p40_report())
    atomic_write_json(latest / "p40_operator_support_bundle_round_trip_chain.json", _p40_chain())

    report = persist_operator_evidence_archive_index(load_config(tmp_path))
    assert report["status"] == STATUS_GENERATED_REVIEW_ONLY
    assert report["missing_archive_artifact_count"] == 0
    assert (latest / "p41_operator_evidence_archive_index_report.json").exists()
    assert (latest / "p41_operator_evidence_archive_index_summary.json").exists()
    assert (latest / "p41_operator_evidence_archive_index.json").exists()
    assert (latest / "p41_operator_evidence_archive_index.csv").exists()
    assert (latest / "p41_operator_evidence_audit_trail_chain.json").exists()
    assert (latest / "p41_operator_evidence_archive_checklist.md").exists()
    assert (latest / "p41_operator_evidence_audit_trail.md").exists()
    assert (latest / "p41_operator_evidence_archive_index_negative_fixture_results.json").exists()
    assert (latest / "p41_operator_evidence_archive_index_registry_record.json").exists()


def test_p41_negative_fixtures_fail_closed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    latest = tmp_path / "storage" / "latest"
    atomic_write_json(latest / "p40_operator_support_bundle_round_trip_verification_report.json", _p40_report())
    atomic_write_json(latest / "p40_operator_support_bundle_round_trip_chain.json", _p40_chain())
    results = build_p41_negative_fixture_results(tmp_path)
    assert results["status"] == "P41_NEGATIVE_FIXTURES_RECORDED"
    assert results["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert results["runtime_scheduler_enabled"] is False
    assert results["order_endpoint_called"] is False
    assert results["secret_value_accessed"] is False

from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.final_runtime_activation_dry_run_evidence_bundle import (
    P29_FINAL_RUNTIME_ACTIVATION_DRY_RUN_EVIDENCE_EXACT_PHRASE,
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_VALID_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY,
    build_final_runtime_activation_dry_run_evidence_bundle_report,
    build_final_runtime_activation_dry_run_evidence_template,
    build_p29_negative_fixture_results,
    persist_final_runtime_activation_dry_run_evidence_bundle,
)
from crypto_ai_system.utils.audit import sha256_json


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text("storage:\n  latest_dir: storage/latest\n", encoding="utf-8")


def _valid_sources() -> tuple[dict, dict, dict, dict]:
    p28_report_hash = "a" * 64
    p28_packet = {
        "packet_type": "p28_final_operator_runtime_activation_gate_review_packet_review_only",
        "valid_review_only": True,
        "runtime_authority": False,
        "runtime_activation_performed": False,
        "scheduler_enabled": False,
        "order_submission_allowed": False,
        "secret_value_accessed": False,
        "endpoint_called": False,
    }
    p28_packet["p28_final_operator_runtime_activation_gate_review_packet_sha256"] = sha256_json(p28_packet)
    p28_summary = {
        "status": "P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_VALID_REVIEW_ONLY",
        "p28_final_operator_runtime_activation_gate_review_sha256": p28_report_hash,
        "p28_final_operator_runtime_activation_gate_review_valid_review_only": True,
        "final_operator_runtime_activation_gate_ready_review_only": True,
        "final_operator_runtime_activation_gate_review_is_runtime_authority": False,
        "separate_operator_runtime_activation_execution_required_after_this_review": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    p28_report = {
        "status": "P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_VALID_REVIEW_ONLY",
        "p28_final_operator_runtime_activation_gate_review_sha256": p28_report_hash,
        "p28_final_operator_runtime_activation_gate_review_valid_review_only": True,
        "final_operator_runtime_activation_gate_ready_review_only": True,
        "final_operator_runtime_activation_gate_review_is_runtime_authority": False,
        "separate_operator_runtime_activation_execution_required_after_this_review": True,
        "runtime_enablement_performed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    evidence = build_final_runtime_activation_dry_run_evidence_template(
        p28_final_operator_runtime_activation_gate_review_report_sha256=p28_report_hash,
        p28_final_operator_runtime_activation_gate_review_packet_sha256=p28_packet["p28_final_operator_runtime_activation_gate_review_packet_sha256"],
    )
    evidence.update({"operator_id": "operator-thomas", "ticket_or_signature": "TICKET-P29-VALID-001", "reviewed_at_utc": "2026-07-08T00:00:00Z"})
    return p28_summary, p28_report, p28_packet, evidence


def test_p29_waits_when_p28_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    report = build_final_runtime_activation_dry_run_evidence_bundle_report(root=tmp_path)
    assert report["status"] == STATUS_WAITING_REVIEW_ONLY
    assert "P29_SOURCE_P28_SUMMARY_MISSING" in report["waiting_reasons"]
    assert "P29_FINAL_RUNTIME_ACTIVATION_DRY_RUN_EVIDENCE_MISSING" in report["waiting_reasons"]
    assert report["live_scaled_execution_enabled"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["secret_value_accessed"] is False


def test_p29_validates_dry_run_evidence_bundle_review_only(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    p28_summary, p28_report, p28_packet, evidence = _valid_sources()
    report = build_final_runtime_activation_dry_run_evidence_bundle_report(
        root=tmp_path,
        p28_summary=p28_summary,
        p28_report=p28_report,
        p28_packet=p28_packet,
        p29_dry_run_evidence=evidence,
    )
    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert report["p29_final_runtime_activation_dry_run_evidence_bundle_valid_review_only"] is True
    assert report["final_runtime_activation_dry_run_evidence_bundle_ready_review_only"] is True
    assert report["final_runtime_activation_dry_run_evidence_bundle_is_runtime_authority"] is False
    assert report["scheduler_tick_dry_run_evidence_valid_review_only"] is True
    assert report["risk_refresh_evidence_valid_review_only"] is True
    assert report["idempotency_evidence_valid_review_only"] is True
    assert report["reconciliation_required_evidence_valid_review_only"] is True
    assert report["kill_switch_ready_evidence_valid_review_only"] is True
    assert report["live_scaled_execution_enabled"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["runtime_scheduler_enabled"] is False
    assert report["runtime_loop_started"] is False
    assert report["order_endpoint_called"] is False
    assert report["secret_value_accessed"] is False


def test_p29_persists_summary_template_packet_registry_and_negative_results(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    latest = tmp_path / "storage" / "latest"
    p28_summary, p28_report, p28_packet, evidence = _valid_sources()
    atomic_write_json(latest / "p28_final_operator_runtime_activation_gate_review_summary.json", p28_summary)
    atomic_write_json(latest / "p28_final_operator_runtime_activation_gate_review_report.json", p28_report)
    atomic_write_json(latest / "p28_final_operator_runtime_activation_gate_review_packet.json", p28_packet)
    atomic_write_json(latest / "p29_final_runtime_activation_dry_run_evidence.json", evidence)
    report = persist_final_runtime_activation_dry_run_evidence_bundle(load_config(tmp_path))
    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert (latest / "p29_final_runtime_activation_dry_run_evidence_bundle_report.json").exists()
    assert (latest / "p29_final_runtime_activation_dry_run_evidence_bundle_summary.json").exists()
    assert (latest / "p29_final_runtime_activation_dry_run_evidence_TEMPLATE.json").exists()
    assert (latest / "p29_final_runtime_activation_dry_run_evidence_bundle_packet.json").exists()
    assert (latest / "p29_final_runtime_activation_dry_run_evidence_bundle_negative_fixture_results.json").exists()
    assert (latest / "p29_final_runtime_activation_dry_run_evidence_bundle_registry_record.json").exists()
    summary = read_json(latest / "p29_final_runtime_activation_dry_run_evidence_bundle_summary.json")
    template = read_json(latest / "p29_final_runtime_activation_dry_run_evidence_TEMPLATE.json")
    packet = read_json(latest / "p29_final_runtime_activation_dry_run_evidence_bundle_packet.json")
    negative = read_json(latest / "p29_final_runtime_activation_dry_run_evidence_bundle_negative_fixture_results.json")
    registry = read_json(latest / "p29_final_runtime_activation_dry_run_evidence_bundle_registry_record.json")
    assert summary["p29_final_runtime_activation_dry_run_evidence_bundle_valid_review_only"] is True
    assert template["exact_final_runtime_activation_dry_run_evidence_phrase"] == P29_FINAL_RUNTIME_ACTIVATION_DRY_RUN_EVIDENCE_EXACT_PHRASE
    assert packet["runtime_authority"] is False
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert registry["live_scaled_execution_enabled"] is False


def test_p29_blocks_wrong_phrase_scheduler_endpoint_secret_runtime_authority(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    p28_summary, p28_report, p28_packet, evidence = _valid_sources()
    wrong_phrase = build_final_runtime_activation_dry_run_evidence_bundle_report(
        root=tmp_path,
        p28_summary=p28_summary,
        p28_report=p28_report,
        p28_packet=p28_packet,
        p29_dry_run_evidence={**evidence, "exact_final_runtime_activation_dry_run_evidence_phrase": "WRONG"},
    )
    assert wrong_phrase["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P29_DRY_RUN_EVIDENCE_EXACT_PHRASE_INVALID" in wrong_phrase["block_reasons"]

    scheduler = build_final_runtime_activation_dry_run_evidence_bundle_report(
        root=tmp_path,
        p28_summary=p28_summary,
        p28_report=p28_report,
        p28_packet=p28_packet,
        p29_dry_run_evidence={**evidence, "runtime_scheduler_enabled": True},
    )
    assert scheduler["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P29_UNSAFE_TRUTHY_FLAG_FOUND" in scheduler["block_reasons"]

    endpoint_ticks = [{**evidence["scheduler_dry_run_ticks"][0], "order_endpoint_called": True}, *evidence["scheduler_dry_run_ticks"][1:]]
    endpoint = build_final_runtime_activation_dry_run_evidence_bundle_report(
        root=tmp_path,
        p28_summary=p28_summary,
        p28_report=p28_report,
        p28_packet=p28_packet,
        p29_dry_run_evidence={**evidence, "scheduler_dry_run_ticks": endpoint_ticks},
    )
    assert endpoint["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P29_UNSAFE_TRUTHY_FLAG_FOUND" in endpoint["block_reasons"]

    secret = build_final_runtime_activation_dry_run_evidence_bundle_report(
        root=tmp_path,
        p28_summary=p28_summary,
        p28_report=p28_report,
        p28_packet=p28_packet,
        p29_dry_run_evidence={**evidence, "operator_note": "BINANCE_API_SECRET=leaked"},
    )
    assert secret["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P29_SECRET_VALUE_PATTERN_FOUND" in secret["block_reasons"]

    authority = build_final_runtime_activation_dry_run_evidence_bundle_report(
        root=tmp_path,
        p28_summary=p28_summary,
        p28_report=p28_report,
        p28_packet=p28_packet,
        p29_dry_run_evidence={**evidence, "bundle_is_runtime_authority": True},
    )
    assert authority["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P29_UNSAFE_TRUTHY_FLAG_FOUND" in authority["block_reasons"]


def test_p29_blocks_missing_fresh_data_risk_idempotency_reconciliation_and_kill_switch(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    p28_summary, p28_report, p28_packet, evidence = _valid_sources()
    missing_fresh = build_final_runtime_activation_dry_run_evidence_bundle_report(
        root=tmp_path,
        p28_summary=p28_summary,
        p28_report=p28_report,
        p28_packet=p28_packet,
        p29_dry_run_evidence={**evidence, "scheduler_dry_run_ticks": [{**evidence["scheduler_dry_run_ticks"][0], "fresh_market_data_loaded": False}, *evidence["scheduler_dry_run_ticks"][1:]]},
    )
    assert missing_fresh["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert any(reason.startswith("P29_TICK_1_MISSING_TRUE_FRESH_MARKET_DATA_LOADED") for reason in missing_fresh["block_reasons"])

    missing_risk = build_final_runtime_activation_dry_run_evidence_bundle_report(
        root=tmp_path,
        p28_summary=p28_summary,
        p28_report=p28_report,
        p28_packet=p28_packet,
        p29_dry_run_evidence={**evidence, "risk_refresh_evidence": {**evidence["risk_refresh_evidence"], "hot_path_preorder_risk_gate_fresh_confirmed": False}},
    )
    assert missing_risk["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert any(reason.startswith("P29_RISK_REFRESH_EVIDENCE_MISSING") for reason in missing_risk["block_reasons"])

    duplicate_ticks = [dict(item) for item in evidence["scheduler_dry_run_ticks"]]
    duplicate_ticks[1]["idempotency_key"] = duplicate_ticks[0]["idempotency_key"]
    duplicate = build_final_runtime_activation_dry_run_evidence_bundle_report(
        root=tmp_path,
        p28_summary=p28_summary,
        p28_report=p28_report,
        p28_packet=p28_packet,
        p29_dry_run_evidence={**evidence, "scheduler_dry_run_ticks": duplicate_ticks},
    )
    assert duplicate["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P29_DRY_RUN_DUPLICATE_IDEMPOTENCY_KEY" in duplicate["block_reasons"]

    missing_recon = build_final_runtime_activation_dry_run_evidence_bundle_report(
        root=tmp_path,
        p28_summary=p28_summary,
        p28_report=p28_report,
        p28_packet=p28_packet,
        p29_dry_run_evidence={**evidence, "reconciliation_required_evidence": {**evidence["reconciliation_required_evidence"], "reconciliation_required_for_every_would_submit": False}},
    )
    assert missing_recon["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert any(reason.startswith("P29_RECONCILIATION_REQUIRED_EVIDENCE_MISSING") for reason in missing_recon["block_reasons"])

    missing_kill = build_final_runtime_activation_dry_run_evidence_bundle_report(
        root=tmp_path,
        p28_summary=p28_summary,
        p28_report=p28_report,
        p28_packet=p28_packet,
        p29_dry_run_evidence={**evidence, "kill_switch_ready_evidence": {**evidence["kill_switch_ready_evidence"], "operator_manual_kill_switch_ready": False}},
    )
    assert missing_kill["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert any(reason.startswith("P29_KILL_SWITCH_READY_EVIDENCE_MISSING") for reason in missing_kill["block_reasons"])


def test_p29_negative_fixtures_are_fail_closed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    negative = build_p29_negative_fixture_results(root=tmp_path)
    assert negative["all_negative_fixtures_blocked_or_waiting_fail_closed"] is True
    assert negative["fixture_results"]["scheduler_enabled"]["blocked_or_waiting"] is True
    assert negative["fixture_results"]["endpoint_called"]["blocked_or_waiting"] is True
    assert negative["fixture_results"]["secret_pattern_found"]["blocked_or_waiting"] is True

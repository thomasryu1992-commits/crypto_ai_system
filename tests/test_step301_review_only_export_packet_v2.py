from __future__ import annotations

import json
from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from crypto_ai_system.reports.review_only_export_packet import (
    REVIEW_ONLY_EXPORT_PACKET_REGISTRY_NAME,
    REVIEW_ONLY_EXPORT_PACKET_VERSION,
    STATUS_REVIEW_ONLY_EXPORT_PACKET_CREATED,
    build_and_persist_review_only_export_packet,
    run_review_only_export_packet_latest,
)
from crypto_ai_system.registry.base_registry import registry_path


def _cfg(tmp_path: Path):
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "storage" / "registries")
    cfg.settings.setdefault("storage", {})["latest_dir"] = str(tmp_path / "storage" / "latest")
    cfg.settings.setdefault("storage", {})["review_export_dir"] = str(tmp_path / "storage" / "review_packets")
    return cfg


def _latest_payloads() -> dict[str, dict]:
    signal = {
        "research_signal_id": "research_signal_step301",
        "signal_version": "v2",
        "profile_id": "default_review_profile",
        "data_snapshot_id": "data_snapshot_step301",
        "data_snapshot_manifest_sha256": "data_snapshot_hash_step301",
        "feature_snapshot_id": "feature_snapshot_step301",
        "feature_matrix_sha256": "feature_matrix_hash_step301",
        "source_bundle_sha256": "source_bundle_hash_step301",
        "permission_result": "review_only",
        "optional_data_health": {"status": "valid_with_optional_missing"},
        "missing_optional_source_count": 4,
        "live_candidate_eligible": False,
        "feature_snapshot_manifest": {
            "feature_snapshot_id": "feature_snapshot_step301",
            "feature_matrix_sha256": "feature_matrix_hash_step301",
            "source_bundle_sha256": "source_bundle_hash_step301",
        },
    }
    decision = {
        "decision_id": "decision_step301",
        "decision_stage": "review_only",
        "final_decision": "REVIEW_ONLY_LONG_CANDIDATE",
        "direction": "LONG",
        "entry": 100.0,
        "stop_loss": 99.0,
        "take_profit": 103.0,
        "risk_reward": 3.0,
        "invalidation": "close below stop",
        "allow_new_position": True,
        "allow_order_intent": False,
        "order_intent_created": False,
        "pre_order_risk_gate_required": True,
        "pre_order_risk_gate_approved": False,
        "order_intent_block_reason": "PRE_ORDER_RISK_GATE_REQUIRED_BEFORE_ORDER_INTENT",
        "risk_gate_id": "risk_gate_step301",
        "risk_gate_status": "PASS_REVIEW_ONLY",
        "research_signal_id": "research_signal_step301",
    }
    return {
        "research_signal.json": signal,
        "research_signal_registry_record.json": {
            "research_signal_id": signal["research_signal_id"],
            "research_signal_registry_record_sha256": "registry_hash_step301",
        },
        "signal_qa_report.json": {
            "research_signal_id": signal["research_signal_id"],
            "signal_qa_result": "PASS_REVIEW_ONLY",
        },
        "market_thesis_note.json": {
            "market_thesis_note_id": "market_thesis_step301",
            "core_thesis": "Review-only thesis",
            "long_arguments": ["price structure supports review"],
            "short_arguments": [],
            "neutral_arguments": ["optional source missing"],
            "counterarguments": ["missing optional data"],
            "invalidation_conditions": ["invalid lineage"],
        },
        "trade_decision.json": decision,
        "performance_report.json": {
            "performance_report_id": "performance_report_step301",
            "status": "PERFORMANCE_REPORT_REVIEW_ONLY_INSUFFICIENT_SAMPLE",
            "recommendation": "repeat_in_paper",
            "sample_size": 0,
        },
        "candidate_profile.json": {
            "candidate_profile_id": "candidate_profile_step301",
            "candidate_profile_created": False,
            "creation_status": "CANDIDATE_PROFILE_BLOCKED_PERFORMANCE_REPORT_NOT_READY",
            "status": "rejected",
            "profile_candidate_hash": "profile_candidate_hash_step301",
        },
        "approval_registry_record.json": {
            "approval_registry_record_id": "approval_registry_step301",
            "validation_status": "blocked_fail_closed",
            "blocked_reasons": ["APPROVAL_REGISTRY_BLOCKED_MISSING_APPROVAL_PACKET"],
        },
    }


def _seed_latest(tmp_path: Path) -> None:
    latest = tmp_path / "storage" / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    for name, payload in _latest_payloads().items():
        atomic_write_json(latest / name, payload)


def test_step301_builds_review_only_export_packet_with_required_files(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _seed_latest(tmp_path)

    manifest = build_and_persist_review_only_export_packet(cfg=cfg)
    packet_dir = Path(manifest["packet_dir"])

    assert manifest["review_only_export_packet_version"] == REVIEW_ONLY_EXPORT_PACKET_VERSION
    assert manifest["status"] == STATUS_REVIEW_ONLY_EXPORT_PACKET_CREATED
    assert manifest["review_only"] is True
    assert manifest["runtime_settings_mutated"] is False
    assert manifest["score_weights_mutated"] is False
    assert manifest["approval_packet_created_by_this_module"] is False
    assert manifest["testnet_order_submission_allowed_by_this_module"] is False
    assert manifest["external_order_submission_performed"] is False
    assert manifest["live_trading_allowed_by_this_module"] is False

    for filename in [
        "human_review_summary.md",
        "feature_lineage.json",
        "research_signal_debug.json",
        "market_thesis_note.json",
        "paper_decision_preview.json",
        "risk_gate_report.json",
        "approval_packet_candidate.json",
        "disabled_settings_write_preview.diff",
        "review_only_export_packet_manifest.json",
    ]:
        assert (packet_dir / filename).exists(), filename

    diff = (packet_dir / "disabled_settings_write_preview.diff").read_text(encoding="utf-8")
    assert "Runtime settings mutation: disabled" in diff
    assert "Automatic apply: disabled" in diff


def test_step301_export_packet_contains_lineage_and_approval_candidate(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _seed_latest(tmp_path)

    manifest = build_and_persist_review_only_export_packet(cfg=cfg)
    packet_dir = Path(manifest["packet_dir"])
    lineage = json.loads((packet_dir / "feature_lineage.json").read_text(encoding="utf-8"))
    approval_candidate = json.loads((packet_dir / "approval_packet_candidate.json").read_text(encoding="utf-8"))
    decision_preview = json.loads((packet_dir / "paper_decision_preview.json").read_text(encoding="utf-8"))

    assert lineage["data_snapshot_id"] == "data_snapshot_step301"
    assert lineage["feature_snapshot_id"] == "feature_snapshot_step301"
    assert lineage["feature_matrix_sha256"] == "feature_matrix_hash_step301"
    assert lineage["source_bundle_sha256"] == "source_bundle_hash_step301"
    assert approval_candidate["manual_approval_required"] is True
    assert approval_candidate["approval_packet_created_by_this_module"] is False
    assert approval_candidate["runtime_settings_mutated"] is False
    assert decision_preview["allow_order_intent"] is False
    assert decision_preview["order_submission_allowed"] is False


def test_step301_persists_registry_and_latest_mirrors(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _seed_latest(tmp_path)

    manifest = run_review_only_export_packet_latest(cfg=cfg)
    registry = registry_path(cfg, REVIEW_ONLY_EXPORT_PACKET_REGISTRY_NAME)
    rows = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines()]

    assert len(rows) == 1
    assert rows[0]["registry_name"] == REVIEW_ONLY_EXPORT_PACKET_REGISTRY_NAME
    assert rows[0]["review_only_export_packet_id"] == manifest["review_only_export_packet_id"]
    assert rows[0]["runtime_settings_mutated"] is False
    assert (tmp_path / "storage" / "latest" / "review_only_export_packet_manifest.json").exists()
    assert (tmp_path / "storage" / "latest" / "review_only_export_packet_registry_record.json").exists()


def test_step301_missing_latest_artifacts_still_review_only_and_fail_safe(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    latest = tmp_path / "storage" / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    atomic_write_json(latest / "research_signal.json", _latest_payloads()["research_signal.json"])

    manifest = build_and_persist_review_only_export_packet(cfg=cfg)
    summary = Path(manifest["packet_dir"]) / "human_review_summary.md"

    assert manifest["status"] == "REVIEW_ONLY_EXPORT_PACKET_CREATED_WITH_MISSING_ARTIFACTS"
    assert manifest["runtime_settings_mutated"] is False
    assert manifest["auto_promotion_allowed"] is False
    assert manifest["missing_source_artifacts"]
    assert "Missing Source Artifacts" in summary.read_text(encoding="utf-8")

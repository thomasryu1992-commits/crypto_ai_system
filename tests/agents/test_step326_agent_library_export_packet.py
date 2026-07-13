from __future__ import annotations

import json
from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.agents.agent_library_export import AGENT_LIBRARY_EXPORT_FILE_NAMES
from crypto_ai_system.config import load_config
from crypto_ai_system.reports.review_only_export_packet import build_and_persist_review_only_export_packet


def _cfg(tmp_path: Path):
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "storage" / "registries")
    cfg.settings.setdefault("storage", {})["latest_dir"] = str(tmp_path / "storage" / "latest")
    cfg.settings.setdefault("storage", {})["review_export_dir"] = str(tmp_path / "storage" / "review_packets")
    return cfg


def _seed_core_latest(tmp_path: Path) -> None:
    latest = tmp_path / "storage" / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    signal = {
        "research_signal_id": "research_signal_step326",
        "signal_version": "v2",
        "profile_id": "default_review_profile",
        "data_snapshot_id": "data_snapshot_step326",
        "data_snapshot_manifest_sha256": "data_snapshot_hash_step326",
        "feature_snapshot_id": "feature_snapshot_step326",
        "feature_matrix_sha256": "feature_matrix_hash_step326",
        "source_bundle_sha256": "source_bundle_hash_step326",
        "permission_result": "review_only",
        "optional_data_health": {"status": "valid_with_optional_missing"},
        "missing_optional_source_count": 4,
        "live_candidate_eligible": False,
        "feature_snapshot_manifest": {
            "feature_snapshot_id": "feature_snapshot_step326",
            "feature_matrix_sha256": "feature_matrix_hash_step326",
            "source_bundle_sha256": "source_bundle_hash_step326",
        },
    }
    decision = {
        "decision_id": "decision_step326",
        "decision_stage": "review_only",
        "final_decision": "REVIEW_ONLY_LONG_CANDIDATE",
        "direction": "LONG",
        "entry": 100.0,
        "stop_loss": 99.0,
        "take_profit": 103.0,
        "risk_reward": 3.0,
        "allow_order_intent": False,
        "pre_order_risk_gate_approved": False,
        "risk_gate_id": "risk_gate_step326",
        "research_signal_id": "research_signal_step326",
    }
    payloads = {
        "research_signal.json": signal,
        "research_signal_registry_record.json": {"research_signal_id": signal["research_signal_id"]},
        "signal_qa_report.json": {"signal_qa_result": "PASS_REVIEW_ONLY"},
        "market_thesis_note.json": {"market_thesis_note_id": "market_thesis_step326"},
        "trade_decision.json": decision,
        "performance_report.json": {"performance_report_id": "performance_report_step326"},
        "candidate_profile.json": {
            "candidate_profile_id": "candidate_profile_step326",
            "status": "rejected",
            "profile_candidate_hash": "profile_hash_step326",
        },
        "approval_registry_record.json": {
            "approval_registry_record_id": "approval_registry_step326",
            "validation_status": "blocked_fail_closed",
            "blocked_reasons": ["APPROVAL_REGISTRY_BLOCKED_MISSING_APPROVAL_PACKET"],
        },
    }
    for filename, payload in payloads.items():
        atomic_write_json(latest / filename, payload)


def _seed_agent_latest(tmp_path: Path) -> None:
    latest = tmp_path / "storage" / "latest"
    payloads = {
        "agent_contract_index.json": {"status": "AGENT_CONTRACT_INDEX_REVIEW_ONLY_RECORDED", "agent_count": 5},
        "agent_lint_report.json": {"status": "AGENT_LINT_PASSED", "passed": True},
        "agent_eval_report.json": {"status": "AGENT_EVALS_PASSED", "passed": True, "eval_case_count": 9},
        "agent_library_contract_review_report.json": {
            "status": "AGENT_LIBRARY_CONTRACT_REVIEW_RECORDED",
            "passed": True,
            "agent_library_contract_review_report_id": "agent_library_review_step326",
            "agent_library_contract_review_report_sha256": "agent_library_review_hash_step326",
            "runtime_permission_source": False,
        },
        "agent_permission_policy_report.json": {"status": "AGENT_PERMISSION_POLICY_REVIEW_RECORDED", "passed": True},
        "agent_prohibited_action_scan.json": {"status": "AGENT_PROHIBITED_ACTION_SCAN_PASSED", "passed": True},
    }
    for filename, payload in payloads.items():
        atomic_write_json(latest / filename, payload)


def test_step326_export_packet_includes_agent_library_evidence(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _seed_core_latest(tmp_path)
    _seed_agent_latest(tmp_path)

    manifest = build_and_persist_review_only_export_packet(cfg=cfg)
    packet_dir = Path(manifest["packet_dir"])

    assert manifest["agent_library_evidence_status"] == "AGENT_LIBRARY_EVIDENCE_INCLUDED"
    assert manifest["missing_agent_library_artifacts"] == []
    assert manifest["agent_library_contract_review_status"] == "AGENT_LIBRARY_CONTRACT_REVIEW_RECORDED"
    assert manifest["runtime_settings_mutated"] is False
    assert manifest["external_order_submission_performed"] is False
    assert manifest["live_trading_allowed_by_this_module"] is False

    for filename in AGENT_LIBRARY_EXPORT_FILE_NAMES:
        assert (packet_dir / filename).exists(), filename
        assert filename in manifest["exported_file_hashes"], filename

    review = json.loads((packet_dir / "agent_contract_review_report.json").read_text(encoding="utf-8"))
    assert review["runtime_permission_source"] is False


def test_step326_missing_agent_artifacts_are_placeholder_blocked_not_runtime_unlock(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _seed_core_latest(tmp_path)

    manifest = build_and_persist_review_only_export_packet(cfg=cfg)
    packet_dir = Path(manifest["packet_dir"])

    assert manifest["agent_library_evidence_status"] == "AGENT_LIBRARY_EVIDENCE_BLOCKED_MISSING_ARTIFACTS"
    assert set(manifest["missing_agent_library_artifacts"]) == set(AGENT_LIBRARY_EXPORT_FILE_NAMES)
    assert manifest["runtime_settings_mutated"] is False
    assert manifest["auto_promotion_allowed"] is False
    assert manifest["testnet_order_submission_allowed_by_this_module"] is False

    placeholder = json.loads((packet_dir / "agent_contract_review_report.json").read_text(encoding="utf-8"))
    assert placeholder["missing"] is True
    assert placeholder["blocked"] is True
    assert placeholder["fail_closed"] is True
    assert placeholder["order_submission_performed"] is False

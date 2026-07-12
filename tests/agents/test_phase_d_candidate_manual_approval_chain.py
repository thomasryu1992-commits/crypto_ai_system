from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase_d_candidate_manual_approval_chain import (
    STATUS_PHASE_D_BLOCKED_REVIEW_ONLY,
    STATUS_PHASE_D_VALID_REVIEW_ONLY,
    build_phase_d_manual_approval_intake_fixture,
    build_phase_d_approval_packet_candidate,
    build_manual_approval_candidate_profile_accepted_draft,
    persist_phase_d_candidate_manual_approval_chain_report,
)


def _write_min_project(root: Path) -> None:
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  name: tmp-crypto-ai-system\n  version: test\n"
        "storage:\n  latest_dir: storage/latest\n  registry_dir: storage/registries\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text("[project]\nname='tmp-crypto-ai-system'\nversion='0.286.0'\n", encoding="utf-8")


def _write_phase_d_ready_artifacts(root: Path) -> None:
    latest = root / "storage" / "latest"
    phase_c = {
        "phase_c_paper_operation_validation_id": "phase_c_1",
        "phase_c_paper_operation_validation_registry_record_id": "phase_c_registry_1",
        "phase_c_paper_operation_validation_registry_record_sha256": "phase_c_registry_hash_1",
        "phase_c_report_sha256": "phase_c_embedded_hash",
        "status": "PHASE_C_PAPER_OPERATION_VALIDATION_RECORDED_REVIEW_ONLY",
        "paper_operation_loop_validated": True,
        "candidate_profile_ready_for_manual_review": True,
        "runtime_permission_source": False,
        "closed_paper_outcome_sample_count": 50,
        "performance_metrics": {
            "score_bucket_alignment_drift_rate": 0.0,
            "reconciliation_mismatch_count": 0,
        },
        "canonical_id_chain": {
            "data_snapshot_id": "ds1",
            "feature_snapshot_id": "fs1",
            "research_signal_id": "rs1",
            "decision_id": "decision1",
            "risk_gate_id": "risk1",
            "order_intent_id": "intent1",
            "execution_id": "execution1",
            "reconciliation_id": "recon1",
            "outcome_id": "outcome1",
            "feedback_cycle_id": "feedback1",
        },
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
    }
    atomic_write_json(latest / "phase_c_paper_operation_validation_report.json", phase_c)
    candidate_review_packet = {
        "candidate_profile_review_packet_id": "review_packet_1",
        "candidate_profile_review_packet_sha256": "review_packet_hash_1",
        "status": "CANDIDATE_PROFILE_REVIEW_PACKET_DRAFT_REVIEW_ONLY",
        "candidate_profile_id": "candidate_1",
        "profile_version": "candidate_profile_v1",
        "target_timeframe": "1h",
        "allowed_direction": "long_short",
        "profile_candidate_hash": "profile_hash_1",
        "profile_candidate_hash_valid": True,
        "feature_matrix_sha256": "feature_hash_1",
        "source_bundle_sha256": "source_bundle_hash_1",
        "data_snapshot_id": "ds1",
        "feature_snapshot_id": "fs1",
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
    }
    atomic_write_json(latest / "candidate_profile_review_packet.json", candidate_review_packet)
    phase4_4 = {
        "status": "PHASE4_4_CANDIDATE_PROFILE_REVIEW_PACKET_RECORDED_REVIEW_ONLY",
        "candidate_review_packet_created": True,
        "approval_packet_draft_created": True,
        "candidate_profile_review_packet_sha256": "review_packet_hash_1",
        "phase4_4_report_sha256": "phase4_4_hash_1",
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
    }
    atomic_write_json(latest / "phase4_4_candidate_profile_review_packet_report.json", phase4_4)
    approval_draft = {
        "approval_packet_draft_id": "approval_draft_1",
        "approval_packet_draft_sha256": "approval_draft_hash_1",
        "approval_packet_id": None,
        "approval_intake_id": None,
        "status": "APPROVAL_PACKET_DRAFT_REVIEW_ONLY_NOT_APPROVED",
        "validation_status": "NOT_SUBMITTED_REVIEW_ONLY",
        "approval_packet_created": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
    }
    atomic_write_json(latest / "approval_packet_draft_review_only.json", approval_draft)


def test_phase_d_records_valid_manual_approval_chain_without_runtime_permission(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_phase_d_ready_artifacts(tmp_path)
    cfg = load_config(tmp_path)

    report = persist_phase_d_candidate_manual_approval_chain_report(cfg=cfg, create_manual_fixture=True)

    assert report["status"] == STATUS_PHASE_D_VALID_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["candidate_profile_accepted_draft_created"] is True
    assert report["candidate_profile_approval_review_status"] == "accepted_for_review"
    assert report["approval_packet_candidate_created"] is True
    assert report["approval_intake_submitted"] is True
    assert report["manual_fixture_used"] is True
    assert report["manual_intake_required_fields_present"] is True
    assert report["approval_registry_valid_review_outcome"] is True
    assert report["approval_registry_status"] == "APPROVAL_REGISTRY_VALID_REVIEW_ONLY"
    assert report["approval_registry_validation_status"] == "valid_review_only_staging_approval"
    assert report["hash_chain_validation"]["source_report_hash_matches"] is True
    assert report["hash_chain_validation"]["approval_packet_hash_matches"] is True
    assert report["hash_chain_validation"]["approval_intake_hash_matches"] is True
    assert report["hash_chain_validation"]["profile_candidate_hash_matches"] is True
    assert report["phase_d_canonical_id_chain_complete"] is True
    assert report["block_reasons"] == []
    assert report["runtime_permission_source"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["signed_testnet_unlock_authority"] is False
    assert report["live_trading_allowed_by_this_module"] is False
    assert report["external_order_submission_performed"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["candidate_profile_applied"] is False
    assert report["auto_promotion_allowed"] is False

    latest = tmp_path / "storage" / "latest"
    assert (latest / "manual_approval_candidate_profile_accepted_draft.json").exists()
    assert (latest / "approval_packet_candidate.json").exists()
    assert (latest / "approval_intake_record.json").exists()
    assert (latest / "approval_registry_record.json").exists()
    assert (latest / "phase_d_candidate_manual_approval_chain_report.json").exists()
    summary = read_json(latest / "p3_candidate_manual_approval_chain_summary.json", default={})
    assert summary["testnet_order_submission_allowed"] is False
    assert summary["external_order_submission_performed"] is False


def test_phase_d_blocks_without_manual_intake(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_phase_d_ready_artifacts(tmp_path)
    cfg = load_config(tmp_path)

    report = persist_phase_d_candidate_manual_approval_chain_report(cfg=cfg, create_manual_fixture=False)

    assert report["status"] == STATUS_PHASE_D_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["candidate_profile_accepted_draft_created"] is True
    assert report["approval_packet_candidate_created"] is True
    assert report["approval_intake_submitted"] is False
    assert report["approval_registry_valid_review_outcome"] is False
    assert "MANUAL_APPROVAL_INTAKE_MISSING" in report["block_reasons"]
    assert "APPROVAL_REGISTRY_BLOCKED_MISSING_APPROVAL_INTAKE" in report["block_reasons"]
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["external_order_submission_performed"] is False


def test_phase_d_blocks_tampered_profile_candidate_hash(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_phase_d_ready_artifacts(tmp_path)
    cfg = load_config(tmp_path)
    latest = tmp_path / "storage" / "latest"
    phase_c = read_json(latest / "phase_c_paper_operation_validation_report.json", default={})
    candidate_review_packet = read_json(latest / "candidate_profile_review_packet.json", default={})
    approval_draft = read_json(latest / "approval_packet_draft_review_only.json", default={})
    accepted_candidate = build_manual_approval_candidate_profile_accepted_draft(
        cfg=cfg,
        phase_c=phase_c,
        candidate_review_packet=candidate_review_packet,
    )
    approval_packet = build_phase_d_approval_packet_candidate(
        cfg=cfg,
        accepted_candidate=accepted_candidate,
        phase_c=phase_c,
        candidate_review_packet=candidate_review_packet,
        approval_draft=approval_draft,
    )
    intake = build_phase_d_manual_approval_intake_fixture(approval_packet=approval_packet)
    intake["profile_candidate_hash"] = "tampered_profile_hash"

    report = persist_phase_d_candidate_manual_approval_chain_report(cfg=cfg, create_manual_fixture=False, approval_intake=intake)

    assert report["status"] == STATUS_PHASE_D_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["approval_registry_valid_review_outcome"] is False
    assert "APPROVAL_REGISTRY_BLOCKED_PROFILE_CANDIDATE_HASH_MISMATCH" in report["block_reasons"]
    assert report["hash_chain_validation"]["profile_candidate_hash_matches"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["external_order_submission_performed"] is False

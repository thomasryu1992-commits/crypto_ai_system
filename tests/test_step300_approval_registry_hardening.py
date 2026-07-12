from __future__ import annotations

import json
from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from crypto_ai_system.registry.approval_registry import (
    APPROVAL_REGISTRY_NAME,
    APPROVAL_REGISTRY_VERSION,
    STATUS_APPROVAL_VALID_REVIEW_ONLY,
    STATUS_BLOCKED_APPROVER_MISSING,
    STATUS_BLOCKED_AUTO_REGENERATED_APPROVAL,
    STATUS_BLOCKED_CANDIDATE_PROFILE_NOT_READY,
    STATUS_BLOCKED_HASH_MISMATCH,
    STATUS_BLOCKED_MISSING_APPROVAL_INTAKE,
    STATUS_BLOCKED_MISSING_APPROVAL_PACKET,
    STATUS_BLOCKED_PROFILE_CANDIDATE_HASH_MISMATCH,
    STATUS_BLOCKED_SOURCE_REPORT_HASH_MISMATCH,
    STATUS_BLOCKED_TICKET_OR_SIGNATURE_MISSING,
    STATUS_BLOCKED_TIMESTAMP_INVALID,
    VALIDATION_STATUS_BLOCKED,
    VALIDATION_STATUS_VALID,
    build_approval_registry_record,
    build_and_persist_approval_registry_record,
    run_approval_registry_latest,
)
from crypto_ai_system.registry.base_registry import registry_path
from crypto_ai_system.utils.audit import sha256_file, sha256_json, stable_id


def _cfg(tmp_path: Path):
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "storage" / "registries")
    cfg.settings.setdefault("storage", {})["latest_dir"] = str(tmp_path / "storage" / "latest")
    return cfg


def _candidate(**overrides):
    payload = {
        "candidate_profile_id": "candidate_profile_step300",
        "candidate_profile_created": True,
        "creation_status": "CANDIDATE_PROFILE_DRAFT_CREATED_REVIEW_ONLY",
        "status": "review_only",
        "source_report_id": "performance_report_step300",
        "source_report_hash": "report_hash_step300",
        "source_report_registry_record_id": "performance_report_registry_step300",
        "source_report_registry_record_sha256": "performance_report_registry_hash_step300",
        "feature_matrix_sha256": "feature_matrix_hash_step300",
        "profile_candidate_hash": "profile_candidate_hash_step300",
        "candidate_profile_registry_record_id": "candidate_profile_registry_step300",
        "candidate_profile_registry_record_sha256": "candidate_profile_registry_hash_step300",
        "candidate_profile_applied": False,
        "settings_write_preview_created": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "live_trading_allowed_by_this_module": False,
    }
    payload.update(overrides)
    return payload


def _packet(candidate=None, **overrides):
    candidate = candidate or _candidate()
    payload = {
        "approval_packet_id": "approval_packet_step300",
        "candidate_profile_id": candidate["candidate_profile_id"],
        "source_report_hash": candidate["source_report_hash"],
        "feature_matrix_sha256": candidate["feature_matrix_sha256"],
        "profile_candidate_hash": candidate["profile_candidate_hash"],
        "created_at_utc": "2026-06-30T00:00:00Z",
        "approval_file_auto_regenerated": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }
    payload.update(overrides)
    payload["approval_packet_hash"] = sha256_json({k: v for k, v in payload.items() if k != "approval_packet_hash"})
    return payload


def _intake(packet=None, **overrides):
    packet = packet or _packet()
    payload = {
        "approval_intake_id": "approval_intake_step300",
        "approval_packet_id": packet["approval_packet_id"],
        "approver_info": "manual_reviewer_thomas",
        "ticket_or_signature": "ticket-or-signature-step300",
        "canonical_utc_timestamp": "2026-06-30T00:01:00Z",
        "profile_candidate_hash": packet["profile_candidate_hash"],
        "approval_decision": "APPROVE_FOR_REVIEW_ONLY_STAGING",
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }
    payload.update(overrides)
    payload["approval_intake_hash"] = sha256_json({k: v for k, v in payload.items() if k != "approval_intake_hash"})
    return payload


def test_step300_builds_valid_review_only_approval_registry_record() -> None:
    candidate = _candidate()
    packet = _packet(candidate)
    intake = _intake(packet)
    record = build_approval_registry_record(candidate, packet, intake)

    assert record["approval_registry_version"] == APPROVAL_REGISTRY_VERSION
    assert record["approval_registry_status"] == STATUS_APPROVAL_VALID_REVIEW_ONLY
    assert record["validation_status"] == VALIDATION_STATUS_VALID
    assert record["approval_recorded"] is True
    assert record["review_only"] is True
    assert record["approval_packet_id"] == "approval_packet_step300"
    assert record["approval_intake_id"] == "approval_intake_step300"
    assert record["approver_info"] == "manual_reviewer_thomas"
    assert record["ticket_or_signature"] == "ticket-or-signature-step300"
    assert record["profile_candidate_hash"] == candidate["profile_candidate_hash"]
    assert record["hash_chain_validation"]["approval_packet_hash_matches"] is True
    assert record["hash_chain_validation"]["approval_intake_hash_matches"] is True
    assert record["candidate_profile_applied"] is False
    assert record["runtime_settings_mutated"] is False
    assert record["score_weights_mutated"] is False
    assert record["auto_promotion_allowed"] is False
    assert record["live_trading_allowed_by_this_module"] is False
    assert record["approval_registry_record_sha256"]


def test_step300_missing_packet_and_intake_fail_closed() -> None:
    record = build_approval_registry_record(_candidate(), {}, {})

    assert record["validation_status"] == VALIDATION_STATUS_BLOCKED
    assert STATUS_BLOCKED_MISSING_APPROVAL_PACKET in record["blocked_reasons"]
    assert STATUS_BLOCKED_MISSING_APPROVAL_INTAKE in record["blocked_reasons"]
    assert record["approval_recorded"] is False
    assert record["runtime_settings_mutated"] is False
    assert record["auto_promotion_allowed"] is False


def test_step300_blocks_unready_candidate_profile() -> None:
    record = build_approval_registry_record(_candidate(candidate_profile_created=False), _packet(), _intake())

    assert record["validation_status"] == VALIDATION_STATUS_BLOCKED
    assert STATUS_BLOCKED_CANDIDATE_PROFILE_NOT_READY in record["blocked_reasons"]


def test_step300_blocks_hash_mismatch_without_regeneration() -> None:
    candidate = _candidate()
    packet = _packet(candidate)
    packet["approval_packet_hash"] = "wrong_hash"
    intake = _intake(_packet(candidate))
    record = build_approval_registry_record(candidate, packet, intake)

    assert record["validation_status"] == VALIDATION_STATUS_BLOCKED
    assert STATUS_BLOCKED_HASH_MISMATCH in record["blocked_reasons"]
    assert record["approval_file_auto_regenerated_by_this_module"] is False


def test_step300_blocks_profile_candidate_hash_mismatch() -> None:
    candidate = _candidate()
    packet = _packet(candidate, profile_candidate_hash="different_profile_hash")
    intake = _intake(packet)
    record = build_approval_registry_record(candidate, packet, intake)

    assert record["validation_status"] == VALIDATION_STATUS_BLOCKED
    assert STATUS_BLOCKED_PROFILE_CANDIDATE_HASH_MISMATCH in record["blocked_reasons"]


def test_step300_blocks_source_report_hash_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "performance_report.json"
    source.write_text(json.dumps({"report": "real"}), encoding="utf-8")
    candidate = _candidate(source_report_hash="declared_wrong_hash")
    packet = _packet(candidate, source_report_path=str(source), source_report_hash="declared_wrong_hash")
    intake = _intake(packet)
    record = build_approval_registry_record(candidate, packet, intake, source_report_path=source)

    assert sha256_file(source) != "declared_wrong_hash"
    assert record["validation_status"] == VALIDATION_STATUS_BLOCKED
    assert STATUS_BLOCKED_SOURCE_REPORT_HASH_MISMATCH in record["blocked_reasons"]


def test_step300_blocks_missing_approver_ticket_and_invalid_timestamp() -> None:
    candidate = _candidate()
    packet = _packet(candidate)
    intake = _intake(packet, approver_info="", ticket_or_signature="", canonical_utc_timestamp="2026-06-30 00:01:00")
    record = build_approval_registry_record(candidate, packet, intake)

    assert record["validation_status"] == VALIDATION_STATUS_BLOCKED
    assert STATUS_BLOCKED_APPROVER_MISSING in record["blocked_reasons"]
    assert STATUS_BLOCKED_TICKET_OR_SIGNATURE_MISSING in record["blocked_reasons"]
    assert STATUS_BLOCKED_TIMESTAMP_INVALID in record["blocked_reasons"]


def test_step300_blocks_auto_regenerated_approval_file() -> None:
    candidate = _candidate()
    packet = _packet(candidate, approval_file_auto_regenerated=True)
    intake = _intake(packet)
    record = build_approval_registry_record(candidate, packet, intake)

    assert record["validation_status"] == VALIDATION_STATUS_BLOCKED
    assert STATUS_BLOCKED_AUTO_REGENERATED_APPROVAL in record["blocked_reasons"]
    assert record["approval_file_auto_regenerated"] is True


def test_step300_persists_approval_registry_append_only(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    candidate = _candidate()
    record = build_and_persist_approval_registry_record(candidate, _packet(candidate), _intake(_packet(candidate)), cfg=cfg)
    registry = registry_path(cfg, APPROVAL_REGISTRY_NAME)
    rows = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines()]

    assert len(rows) == 1
    assert rows[0]["registry_name"] == APPROVAL_REGISTRY_NAME
    assert rows[0]["approval_registry_record_id"] == record["approval_registry_record_id"]
    assert (tmp_path / "storage" / "latest" / "approval_registry_record.json").exists()


def test_step300_run_latest_fails_closed_when_approval_evidence_missing(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    latest_dir = tmp_path / "storage" / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(latest_dir / "candidate_profile.json", _candidate())

    result = run_approval_registry_latest(cfg=cfg)

    assert result["validation_status"] == VALIDATION_STATUS_BLOCKED
    assert STATUS_BLOCKED_MISSING_APPROVAL_PACKET in result["blocked_reasons"]
    assert STATUS_BLOCKED_MISSING_APPROVAL_INTAKE in result["blocked_reasons"]
    assert result["approval_recorded"] is False
    assert result["runtime_settings_mutated"] is False

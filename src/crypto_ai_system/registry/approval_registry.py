from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_file, sha256_json, stable_id, utc_now_canonical

APPROVAL_REGISTRY_VERSION = "step300_approval_registry_hardening_v1"
APPROVAL_REGISTRY_NAME = "approval_registry"

STATUS_APPROVAL_VALID_REVIEW_ONLY = "APPROVAL_REGISTRY_VALID_REVIEW_ONLY"
STATUS_BLOCKED_MISSING_APPROVAL_PACKET = "APPROVAL_REGISTRY_BLOCKED_MISSING_APPROVAL_PACKET"
STATUS_BLOCKED_MISSING_APPROVAL_INTAKE = "APPROVAL_REGISTRY_BLOCKED_MISSING_APPROVAL_INTAKE"
STATUS_BLOCKED_DAMAGED_APPROVAL_ARTIFACT = "APPROVAL_REGISTRY_BLOCKED_DAMAGED_APPROVAL_ARTIFACT"
STATUS_BLOCKED_HASH_MISMATCH = "APPROVAL_REGISTRY_BLOCKED_HASH_MISMATCH"
STATUS_BLOCKED_APPROVER_MISSING = "APPROVAL_REGISTRY_BLOCKED_APPROVER_MISSING"
STATUS_BLOCKED_TICKET_OR_SIGNATURE_MISSING = "APPROVAL_REGISTRY_BLOCKED_TICKET_OR_SIGNATURE_MISSING"
STATUS_BLOCKED_TIMESTAMP_INVALID = "APPROVAL_REGISTRY_BLOCKED_TIMESTAMP_INVALID"
STATUS_BLOCKED_AUTO_REGENERATED_APPROVAL = "APPROVAL_REGISTRY_BLOCKED_AUTO_REGENERATED_APPROVAL"
STATUS_BLOCKED_CANDIDATE_PROFILE_NOT_READY = "APPROVAL_REGISTRY_BLOCKED_CANDIDATE_PROFILE_NOT_READY"
STATUS_BLOCKED_SOURCE_REPORT_HASH_MISMATCH = "APPROVAL_REGISTRY_BLOCKED_SOURCE_REPORT_HASH_MISMATCH"
STATUS_BLOCKED_PROFILE_CANDIDATE_HASH_MISMATCH = "APPROVAL_REGISTRY_BLOCKED_PROFILE_CANDIDATE_HASH_MISMATCH"

VALIDATION_STATUS_VALID = "valid_review_only_staging_approval"
VALIDATION_STATUS_BLOCKED = "blocked_fail_closed"

LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE = False
SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE = False
AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE = False
CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE = False
SETTINGS_WRITE_PREVIEW_CREATED_BY_THIS_MODULE = False
APPROVAL_PACKET_CREATED_BY_THIS_MODULE = False
APPROVAL_FILE_AUTO_REGENERATED_BY_THIS_MODULE = False


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _latest_path(cfg: AppConfig, name: str) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    base = Path(raw)
    if not base.is_absolute():
        base = cfg.root / base
    base.mkdir(parents=True, exist_ok=True)
    return base / name


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_read_json(path: str | Path | None) -> tuple[dict[str, Any], str | None]:
    if not path:
        return {}, None
    p = Path(path)
    try:
        payload = read_json(p, default={})
    except Exception as exc:
        return {}, f"{exc.__class__.__name__}: {exc}"
    if not isinstance(payload, Mapping):
        return {}, "approval artifact is not a JSON object"
    return dict(payload), None


def _payload_hash(payload: Mapping[str, Any], hash_fields: set[str]) -> str:
    return sha256_json({k: v for k, v in payload.items() if k not in hash_fields})


def _approval_packet_hash(packet: Mapping[str, Any]) -> str:
    return _payload_hash(packet, {"approval_packet_hash", "approval_packet_sha256"})


def _approval_intake_hash(intake: Mapping[str, Any]) -> str:
    return _payload_hash(intake, {"approval_intake_hash", "approval_intake_sha256"})


def _candidate_ready(candidate: Mapping[str, Any]) -> bool:
    return (
        _bool(candidate.get("candidate_profile_created"))
        and candidate.get("status") in {"review_only", "paper_candidate", "approval_packet_ready"}
        and bool(_text(candidate.get("candidate_profile_id")))
        and bool(_text(candidate.get("profile_candidate_hash")))
    )


def _source_report_hash_from_path(path: str | Path | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists() or p.is_dir():
        return None
    return sha256_file(p)


def _normalize_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(packet or {})
    if data.get("approval_packet_sha256") and not data.get("approval_packet_hash"):
        data["approval_packet_hash"] = data.get("approval_packet_sha256")
    if data.get("source_report_sha256") and not data.get("source_report_hash"):
        data["source_report_hash"] = data.get("source_report_sha256")
    if data.get("profile_candidate_sha256") and not data.get("profile_candidate_hash"):
        data["profile_candidate_hash"] = data.get("profile_candidate_sha256")
    return data


def _normalize_intake(intake: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(intake or {})
    if data.get("approval_signature") and not data.get("ticket_or_signature"):
        data["ticket_or_signature"] = data.get("approval_signature")
    if data.get("approval_ticket_id") and not data.get("ticket_or_signature"):
        data["ticket_or_signature"] = data.get("approval_ticket_id")
    if data.get("timestamp_utc") and not data.get("canonical_utc_timestamp"):
        data["canonical_utc_timestamp"] = data.get("timestamp_utc")
    if data.get("approver") and not data.get("approver_info"):
        data["approver_info"] = data.get("approver")
    if data.get("approver_id") and not data.get("approver_info"):
        data["approver_info"] = data.get("approver_id")
    if data.get("approval_intake_sha256") and not data.get("approval_intake_hash"):
        data["approval_intake_hash"] = data.get("approval_intake_sha256")
    return data


def _unsafe_side_effects(*payloads: Mapping[str, Any]) -> list[str]:
    unsafe_names = [
        "live_trading_allowed_by_this_module",
        "runtime_settings_mutated",
        "score_weights_mutated",
        "auto_promotion_allowed",
        "candidate_profile_applied",
        "settings_write_preview_created",
        "live_order_executed",
        "external_order_submission_performed",
        "external_order_submission_allowed",
        "testnet_order_submission_allowed",
        "place_order_enabled",
        "cancel_order_enabled",
        "signed_order_executor_enabled",
    ]
    found: list[str] = []
    for payload in payloads:
        for name in unsafe_names:
            if _bool(payload.get(name)):
                found.append(name)
    return sorted(dict.fromkeys(found))


def build_approval_registry_record(
    candidate_profile: Mapping[str, Any] | None,
    approval_packet: Mapping[str, Any] | None = None,
    approval_intake: Mapping[str, Any] | None = None,
    *,
    source_report_path: str | Path | None = None,
    approval_packet_path: str | Path | None = None,
    approval_intake_path: str | Path | None = None,
    damaged_artifact_error: str | None = None,
) -> dict[str, Any]:
    candidate = _as_mapping(candidate_profile)
    packet = _normalize_packet(_as_mapping(approval_packet))
    intake = _normalize_intake(_as_mapping(approval_intake))
    created_at = utc_now_canonical()

    blockers: list[str] = []
    checks: dict[str, bool] = {}

    checks["candidate_profile_ready"] = _candidate_ready(candidate)
    if not checks["candidate_profile_ready"]:
        blockers.append(STATUS_BLOCKED_CANDIDATE_PROFILE_NOT_READY)

    checks["approval_packet_present"] = bool(packet)
    if not packet:
        blockers.append(STATUS_BLOCKED_MISSING_APPROVAL_PACKET)

    checks["approval_intake_present"] = bool(intake)
    if not intake:
        blockers.append(STATUS_BLOCKED_MISSING_APPROVAL_INTAKE)

    if damaged_artifact_error:
        checks["approval_artifacts_parseable"] = False
        blockers.append(STATUS_BLOCKED_DAMAGED_APPROVAL_ARTIFACT)
    else:
        checks["approval_artifacts_parseable"] = True

    packet_hash = _approval_packet_hash(packet) if packet else None
    intake_hash = _approval_intake_hash(intake) if intake else None
    declared_packet_hash = packet.get("approval_packet_hash") if packet else None
    declared_intake_hash = intake.get("approval_intake_hash") if intake else None

    checks["approval_packet_hash_matches"] = (not packet) or (not declared_packet_hash) or declared_packet_hash == packet_hash
    if not checks["approval_packet_hash_matches"]:
        blockers.append(STATUS_BLOCKED_HASH_MISMATCH)

    checks["approval_intake_hash_matches"] = (not intake) or (not declared_intake_hash) or declared_intake_hash == intake_hash
    if not checks["approval_intake_hash_matches"]:
        blockers.append(STATUS_BLOCKED_HASH_MISMATCH)

    source_path = source_report_path or packet.get("source_report_path") or packet.get("source_step_report_path")
    actual_source_hash = _source_report_hash_from_path(source_path)
    packet_source_hash = _text(packet.get("source_report_hash") or packet.get("source_step_report_sha256")) or None
    candidate_source_hash = _text(candidate.get("source_report_hash")) or None
    source_hash_expected = packet_source_hash or candidate_source_hash
    checks["source_report_hash_matches"] = True
    if actual_source_hash and source_hash_expected and actual_source_hash != source_hash_expected:
        checks["source_report_hash_matches"] = False
    if packet_source_hash and candidate_source_hash and packet_source_hash != candidate_source_hash:
        checks["source_report_hash_matches"] = False
    if not checks["source_report_hash_matches"]:
        blockers.append(STATUS_BLOCKED_SOURCE_REPORT_HASH_MISMATCH)

    packet_profile_hash = _text(packet.get("profile_candidate_hash") or packet.get("profile_candidate_sha256"))
    candidate_profile_hash = _text(candidate.get("profile_candidate_hash"))
    intake_profile_hash = _text(intake.get("profile_candidate_hash") or intake.get("profile_candidate_sha256"))
    checks["profile_candidate_hash_matches"] = True
    for value in [packet_profile_hash, intake_profile_hash]:
        if value and candidate_profile_hash and value != candidate_profile_hash:
            checks["profile_candidate_hash_matches"] = False
    if not checks["profile_candidate_hash_matches"]:
        blockers.append(STATUS_BLOCKED_PROFILE_CANDIDATE_HASH_MISMATCH)

    packet_id = _text(packet.get("approval_packet_id"))
    intake_packet_id = _text(intake.get("approval_packet_id"))
    checks["approval_packet_id_matches_intake"] = (not packet or not intake) or (packet_id and intake_packet_id and packet_id == intake_packet_id)
    if not checks["approval_packet_id_matches_intake"]:
        blockers.append(STATUS_BLOCKED_HASH_MISMATCH)

    approver_info = _text(intake.get("approver_info") or packet.get("approver_info"))
    checks["approver_info_present"] = bool(approver_info) if intake else False
    if intake and not checks["approver_info_present"]:
        blockers.append(STATUS_BLOCKED_APPROVER_MISSING)

    ticket_or_signature = _text(intake.get("ticket_or_signature") or intake.get("approval_signature") or intake.get("approval_ticket_id") or packet.get("ticket_or_signature") or packet.get("approval_signature"))
    checks["ticket_or_signature_present"] = bool(ticket_or_signature) if intake else False
    if intake and not checks["ticket_or_signature_present"]:
        blockers.append(STATUS_BLOCKED_TICKET_OR_SIGNATURE_MISSING)

    timestamp = _text(intake.get("canonical_utc_timestamp") or packet.get("canonical_utc_timestamp") or intake.get("timestamp_utc"))
    checks["canonical_utc_timestamp_present_and_valid"] = bool(timestamp) and is_canonical_utc_timestamp(timestamp) if intake else False
    if intake and not checks["canonical_utc_timestamp_present_and_valid"]:
        blockers.append(STATUS_BLOCKED_TIMESTAMP_INVALID)

    auto_regenerated = any(
        _bool(payload.get(name))
        for payload in [packet, intake]
        for name in ["approval_file_auto_regenerated", "auto_regenerated", "regenerated_missing_approval_file"]
    )
    checks["approval_files_not_auto_regenerated"] = not auto_regenerated
    if auto_regenerated:
        blockers.append(STATUS_BLOCKED_AUTO_REGENERATED_APPROVAL)

    unsafe = _unsafe_side_effects(candidate, packet, intake)
    checks["no_unsafe_side_effect_flags"] = not unsafe
    if unsafe:
        blockers.append(STATUS_BLOCKED_AUTO_REGENERATED_APPROVAL)

    blockers = sorted(dict.fromkeys(blockers))
    valid = not blockers and bool(packet) and bool(intake)

    validation_status = VALIDATION_STATUS_VALID if valid else VALIDATION_STATUS_BLOCKED
    approval_registry_status = STATUS_APPROVAL_VALID_REVIEW_ONLY if valid else blockers[0]

    record = {
        "approval_registry_version": APPROVAL_REGISTRY_VERSION,
        "approval_registry_status": approval_registry_status,
        "validation_status": validation_status,
        "blocked_reason": None if valid else approval_registry_status,
        "blocked_reasons": blockers,
        "approval_packet_id": packet.get("approval_packet_id"),
        "approval_intake_id": intake.get("approval_intake_id"),
        "approver_info": approver_info,
        "ticket_or_signature": ticket_or_signature,
        "source_report_path": str(source_path) if source_path else None,
        "source_report_hash": actual_source_hash or packet_source_hash or candidate_source_hash,
        "source_report_declared_hash": source_hash_expected,
        "approval_packet_path": str(approval_packet_path) if approval_packet_path else None,
        "approval_intake_path": str(approval_intake_path) if approval_intake_path else None,
        "approval_packet_hash": packet_hash,
        "approval_packet_declared_hash": declared_packet_hash,
        "approval_intake_hash": intake_hash,
        "approval_intake_declared_hash": declared_intake_hash,
        "feature_matrix_hash": packet.get("feature_matrix_hash") or packet.get("feature_matrix_sha256") or candidate.get("feature_matrix_sha256"),
        "profile_candidate_hash": candidate_profile_hash or packet_profile_hash or intake_profile_hash,
        "candidate_profile_id": candidate.get("candidate_profile_id"),
        "candidate_profile_registry_record_id": candidate.get("candidate_profile_registry_record_id"),
        "candidate_profile_registry_record_sha256": candidate.get("candidate_profile_registry_record_sha256"),
        "canonical_utc_timestamp": timestamp or None,
        "created_at_utc": created_at,
        "validation_checks": checks,
        "failed_checks": [name for name, ok in checks.items() if not ok],
        "hash_chain_validation": {
            "source_report_hash_matches": checks["source_report_hash_matches"],
            "approval_packet_hash_matches": checks["approval_packet_hash_matches"],
            "approval_intake_hash_matches": checks["approval_intake_hash_matches"],
            "profile_candidate_hash_matches": checks["profile_candidate_hash_matches"],
            "approval_packet_id_matches_intake": checks["approval_packet_id_matches_intake"],
        },
        "damaged_artifact_error": damaged_artifact_error,
        "approval_file_auto_regenerated": auto_regenerated,
        "approval_recorded": valid,
        "review_only": True,
        "manual_approval_required": True,
        "candidate_profile_applied": CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE,
        "settings_write_preview_created": SETTINGS_WRITE_PREVIEW_CREATED_BY_THIS_MODULE,
        "runtime_settings_mutated": RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE,
        "score_weights_mutated": SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE,
        "auto_promotion_allowed": AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE,
        "approval_packet_created_by_this_module": APPROVAL_PACKET_CREATED_BY_THIS_MODULE,
        "approval_file_auto_regenerated_by_this_module": APPROVAL_FILE_AUTO_REGENERATED_BY_THIS_MODULE,
        "live_trading_allowed_by_this_module": LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        "external_order_submission_performed": False,
        "testnet_order_submission_allowed": False,
        "live_candidate_eligible": False,
    }
    record["approval_registry_record_id"] = stable_id("approval_registry", record, 24)
    record["approval_registry_record_sha256"] = sha256_json(record)
    return record


def persist_approval_registry_record(cfg: AppConfig, record: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(record or {})
    persisted = append_registry_record(
        registry_path(cfg, APPROVAL_REGISTRY_NAME),
        payload,
        registry_name=APPROVAL_REGISTRY_NAME,
        id_field="approval_registry_record_id",
        hash_field="approval_registry_record_sha256",
        id_prefix="approval_registry",
    )
    atomic_write_json(_latest_path(cfg, "approval_registry_record.json"), persisted)
    return persisted


def build_and_persist_approval_registry_record(
    candidate_profile: Mapping[str, Any] | None,
    approval_packet: Mapping[str, Any] | None = None,
    approval_intake: Mapping[str, Any] | None = None,
    *,
    cfg: AppConfig | None = None,
    source_report_path: str | Path | None = None,
    approval_packet_path: str | Path | None = None,
    approval_intake_path: str | Path | None = None,
    damaged_artifact_error: str | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(".")
    record = build_approval_registry_record(
        candidate_profile,
        approval_packet,
        approval_intake,
        source_report_path=source_report_path,
        approval_packet_path=approval_packet_path,
        approval_intake_path=approval_intake_path,
        damaged_artifact_error=damaged_artifact_error,
    )
    return persist_approval_registry_record(cfg, record)


def run_approval_registry_latest(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(".")
    latest_candidate = _latest_path(cfg, "candidate_profile.json")
    candidate = read_json(latest_candidate, default={}) if latest_candidate.exists() else {}
    if not isinstance(candidate, Mapping):
        candidate = {}

    packet_path = _latest_path(cfg, "approval_packet_candidate.json")
    intake_path = _latest_path(cfg, "approval_intake_record.json")
    packet, packet_error = _safe_read_json(packet_path) if packet_path.exists() else ({}, None)
    intake, intake_error = _safe_read_json(intake_path) if intake_path.exists() else ({}, None)
    damaged_error = "; ".join(error for error in [packet_error, intake_error] if error) or None

    source_report_path = candidate.get("source_report_path") or candidate.get("source_report_id")
    return build_and_persist_approval_registry_record(
        candidate,
        packet,
        intake,
        cfg=cfg,
        source_report_path=source_report_path,
        approval_packet_path=packet_path if packet_path.exists() else None,
        approval_intake_path=intake_path if intake_path.exists() else None,
        damaged_artifact_error=damaged_error,
    )

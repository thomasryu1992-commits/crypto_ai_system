from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.execution.signed_testnet_read_only_venue_probe_session import (
    validate_read_only_venue_probe_evidence,
    validate_signed_testnet_read_only_venue_probe_session,
)
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical

SIGNED_TESTNET_PROBE_RESULT_VALIDATOR_VERSION = "step279_read_only_venue_probe_result_validator_v1"
SIGNED_TESTNET_EXECUTION_ALLOWED_BY_STEP279 = False
TESTNET_ORDER_SUBMISSION_ALLOWED_BY_STEP279 = False
SIGNED_TESTNET_PROMOTION_ALLOWED_BY_STEP279 = False
EXTERNAL_ORDER_SUBMISSION_ALLOWED_BY_STEP279 = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_STEP279 = False
PLACE_ORDER_ENABLED_BY_STEP279 = False
CANCEL_ORDER_ENABLED_BY_STEP279 = False
SIGNED_ORDER_EXECUTOR_ENABLED_BY_STEP279 = False

_REQUIRED_READ_PROBES = [
    "balance_read_probe",
    "positions_read_probe",
    "open_orders_read_probe",
    "orderbook_read_probe",
    "fee_estimate_probe",
    "slippage_estimate_probe",
    "min_order_size_probe",
    "fetch_order_probe",
]


def _payload_without_hash(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in dict(payload).items()
        if k
        not in {
            "probe_result_summary_sha256",
            "signed_testnet_promotion_blocker_sha256",
            "created_at_utc",
            "probe_result_summary_path",
        }
    }


def _parse_canonical_utc(value: Any) -> datetime | None:
    if not is_canonical_utc_timestamp(value):
        return None
    return datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _age_sec(value: Any) -> int | None:
    parsed = _parse_canonical_utc(value)
    if parsed is None:
        return None
    return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))


def _hash_close_report(close_report: Mapping[str, Any]) -> str:
    return sha256_json(
        {k: v for k, v in dict(close_report).items() if k not in {"read_only_probe_close_report_sha256", "created_at_utc"}}
    )


def _build_signed_testnet_promotion_blocker(
    *,
    summary_payload: Mapping[str, Any],
    inherited_blockers: list[str],
) -> dict[str, Any]:
    blockers = set(inherited_blockers)
    blockers.add("STEP279_SIGNED_TESTNET_PROMOTION_BLOCKED_PENDING_EXPLICIT_EXECUTION_STEP")
    blockers.add("STEP279_TESTNET_ORDER_SUBMISSION_REMAINS_DISABLED_BY_DESIGN")
    payload = {
        "version": SIGNED_TESTNET_PROBE_RESULT_VALIDATOR_VERSION,
        "read_only_venue_probe_result_summary_id": summary_payload.get("read_only_venue_probe_result_summary_id"),
        "signed_testnet_read_only_venue_probe_session_id": summary_payload.get("signed_testnet_read_only_venue_probe_session_id"),
        "read_only_venue_probe_session_sha256": summary_payload.get("read_only_venue_probe_session_sha256"),
        "promotion_stage": "signed_testnet_promotion_review_only_step279",
        "promotion_status": "BLOCKED_BY_DESIGN_STEP279",
        "signed_testnet_execution_allowed": SIGNED_TESTNET_EXECUTION_ALLOWED_BY_STEP279,
        "testnet_order_submission_allowed": TESTNET_ORDER_SUBMISSION_ALLOWED_BY_STEP279,
        "signed_testnet_promotion_allowed": SIGNED_TESTNET_PROMOTION_ALLOWED_BY_STEP279,
        "external_order_submission_allowed": EXTERNAL_ORDER_SUBMISSION_ALLOWED_BY_STEP279,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_STEP279,
        "place_order_enabled": PLACE_ORDER_ENABLED_BY_STEP279,
        "cancel_order_enabled": CANCEL_ORDER_ENABLED_BY_STEP279,
        "signed_order_executor_enabled": SIGNED_ORDER_EXECUTOR_ENABLED_BY_STEP279,
        "promotion_block_reasons": sorted(blockers),
    }
    blocker = {
        "signed_testnet_promotion_blocker_id": stable_id("step279_signed_testnet_promotion_blocker", payload),
        **payload,
        "valid": True,
        "created_at_utc": utc_now_canonical(),
    }
    blocker["signed_testnet_promotion_blocker_sha256"] = sha256_json(
        {k: v for k, v in blocker.items() if k not in {"signed_testnet_promotion_blocker_sha256", "created_at_utc"}}
    )
    return blocker


def build_read_only_venue_probe_result_summary(
    *,
    read_only_probe_session: Mapping[str, Any],
    max_probe_age_sec: int = 600,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    session = dict(read_only_probe_session or {})
    blockers: list[str] = []

    session_validation = validate_signed_testnet_read_only_venue_probe_session(session)
    if session_validation.get("valid") is not True:
        blockers.append("STEP279_STEP278_READ_ONLY_PROBE_SESSION_INVALID")
        blockers.extend(session_validation.get("block_reasons", []))

    evidence = session.get("read_only_venue_probe_evidence") or {}
    evidence_validation = validate_read_only_venue_probe_evidence(evidence)
    if evidence_validation.get("valid") is not True:
        blockers.append("STEP279_PROBE_EVIDENCE_INVALID")
        blockers.extend(evidence_validation.get("block_reasons", []))

    probe_age = _age_sec(evidence.get("created_at_utc") if isinstance(evidence, Mapping) else None)
    probe_evidence_fresh = False
    if probe_age is None:
        blockers.append("STEP279_PROBE_EVIDENCE_TIMESTAMP_NOT_CANONICAL_UTC")
    elif probe_age > max_probe_age_sec:
        blockers.append("STEP279_PROBE_EVIDENCE_STALE_BLOCKED")
    else:
        probe_evidence_fresh = True

    read_probe_results: dict[str, dict[str, Any]] = {}
    all_read_probes_valid = True
    if not isinstance(evidence, Mapping):
        blockers.append("STEP279_PROBE_EVIDENCE_MISSING")
        all_read_probes_valid = False
    else:
        for name in _REQUIRED_READ_PROBES:
            probe = evidence.get(name)
            if not isinstance(probe, Mapping):
                blockers.append(f"STEP279_{name.upper()}_MISSING")
                read_probe_results[name] = {"valid": False, "missing": True}
                all_read_probes_valid = False
                continue
            valid = probe.get("valid") is True and not probe.get("block_reasons")
            read_probe_results[name] = {
                "probe_hash": probe.get("probe_hash"),
                "status": probe.get("status"),
                "valid": valid,
                "block_reasons": list(probe.get("block_reasons") or []),
            }
            if not valid:
                blockers.append(f"STEP279_{name.upper()}_INVALID")
                all_read_probes_valid = False

    place_probe = evidence.get("place_order_block_probe") if isinstance(evidence, Mapping) else None
    cancel_probe = evidence.get("cancel_order_block_probe") if isinstance(evidence, Mapping) else None
    place_cancel_disabled_evidence_valid = True
    for name, probe in [("PLACE_ORDER", place_probe), ("CANCEL_ORDER", cancel_probe)]:
        if not isinstance(probe, Mapping):
            blockers.append(f"STEP279_{name}_BLOCK_PROBE_MISSING")
            place_cancel_disabled_evidence_valid = False
            continue
        if probe.get("adapter_method_called") is not False:
            blockers.append(f"STEP279_{name}_ADAPTER_METHOD_CALLED_BLOCKED")
            place_cancel_disabled_evidence_valid = False
        if probe.get("capability_enabled") is True:
            blockers.append(f"STEP279_{name}_CAPABILITY_ENABLED_BLOCKED")
            place_cancel_disabled_evidence_valid = False
        if probe.get("valid") is not True:
            blockers.append(f"STEP279_{name}_BLOCK_PROBE_INVALID")
            place_cancel_disabled_evidence_valid = False

    close_report = session.get("read_only_probe_close_report") or {}
    close_report_hash_valid = False
    if not isinstance(close_report, Mapping):
        blockers.append("STEP279_PROBE_CLOSE_REPORT_MISSING")
    else:
        expected_close_hash = _hash_close_report(close_report)
        close_report_hash_valid = close_report.get("read_only_probe_close_report_sha256") == expected_close_hash
        if not close_report_hash_valid:
            blockers.append("STEP279_PROBE_CLOSE_REPORT_HASH_INVALID")
        if close_report.get("valid") is not True:
            blockers.append("STEP279_PROBE_CLOSE_REPORT_INVALID")
        if close_report.get("external_order_submission_performed") is not False:
            blockers.append("STEP279_PROBE_CLOSE_REPORT_EXTERNAL_SUBMISSION_PERFORMED")
        if close_report.get("adapter_place_order_called") is not False:
            blockers.append("STEP279_PROBE_CLOSE_REPORT_ADAPTER_PLACE_ORDER_CALLED")
        if close_report.get("adapter_cancel_order_called") is not False:
            blockers.append("STEP279_PROBE_CLOSE_REPORT_ADAPTER_CANCEL_ORDER_CALLED")

    operator_ack_validation = session.get("operator_probe_acknowledgement_validation") or {}
    operator_acknowledgement_valid = isinstance(operator_ack_validation, Mapping) and operator_ack_validation.get("valid") is True
    if not operator_acknowledgement_valid:
        blockers.append("STEP279_OPERATOR_PROBE_ACK_VALIDATION_INVALID")
        if isinstance(operator_ack_validation, Mapping):
            blockers.extend(operator_ack_validation.get("block_reasons", []))

    for field in [
        "ready_for_signed_testnet_execution",
        "testnet_order_submission_allowed",
        "external_order_submission_performed",
        "place_order_enabled",
        "cancel_order_enabled",
        "signed_order_executor_enabled",
        "adapter_place_order_called",
        "adapter_cancel_order_called",
    ]:
        if session.get(field) is not False:
            blockers.append(f"STEP279_SESSION_{field.upper()}_INVARIANT_FAILED")

    if session.get("probe_session_review_ready") is not True:
        blockers.append("STEP279_STEP278_PROBE_SESSION_NOT_REVIEW_READY")

    summary_ready = not blockers
    summary_id_payload = {
        "version": SIGNED_TESTNET_PROBE_RESULT_VALIDATOR_VERSION,
        "session_id": session.get("signed_testnet_read_only_venue_probe_session_id"),
        "session_hash": session.get("read_only_venue_probe_session_sha256"),
        "evidence_hash": evidence.get("read_only_venue_probe_evidence_sha256") if isinstance(evidence, Mapping) else None,
        "blockers": sorted(set(blockers)),
    }
    summary = {
        "read_only_venue_probe_result_summary_id": stable_id("step279_read_only_venue_probe_result_summary", summary_id_payload),
        "version": SIGNED_TESTNET_PROBE_RESULT_VALIDATOR_VERSION,
        "signed_testnet_read_only_venue_probe_session_id": session.get("signed_testnet_read_only_venue_probe_session_id"),
        "read_only_venue_probe_session_sha256": session.get("read_only_venue_probe_session_sha256"),
        "testnet_execution_session_id": session.get("testnet_execution_session_id"),
        "step278_session_validation": session_validation,
        "probe_evidence_validation": evidence_validation,
        "read_probe_results": read_probe_results,
        "all_read_probes_valid": all_read_probes_valid,
        "operator_acknowledgement_valid": operator_acknowledgement_valid,
        "place_cancel_disabled_evidence_valid": place_cancel_disabled_evidence_valid,
        "probe_close_report_hash_valid": close_report_hash_valid,
        "probe_evidence_fresh": probe_evidence_fresh,
        "probe_evidence_age_sec": probe_age,
        "probe_evidence_max_age_sec": max_probe_age_sec,
        "probe_result_summary_review_ready": summary_ready,
        "signed_testnet_execution_allowed": SIGNED_TESTNET_EXECUTION_ALLOWED_BY_STEP279,
        "testnet_order_submission_allowed": TESTNET_ORDER_SUBMISSION_ALLOWED_BY_STEP279,
        "signed_testnet_promotion_allowed": SIGNED_TESTNET_PROMOTION_ALLOWED_BY_STEP279,
        "external_order_submission_allowed": EXTERNAL_ORDER_SUBMISSION_ALLOWED_BY_STEP279,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_STEP279,
        "place_order_enabled": PLACE_ORDER_ENABLED_BY_STEP279,
        "cancel_order_enabled": CANCEL_ORDER_ENABLED_BY_STEP279,
        "signed_order_executor_enabled": SIGNED_ORDER_EXECUTOR_ENABLED_BY_STEP279,
        "promotion_remains_blocked": True,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }
    promotion_blocker = _build_signed_testnet_promotion_blocker(
        summary_payload=summary,
        inherited_blockers=sorted(set(blockers)),
    )
    summary["signed_testnet_promotion_blocker"] = promotion_blocker
    summary["probe_result_summary_sha256"] = sha256_json(_payload_without_hash(summary))
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        summary["probe_result_summary_path"] = str(path)
        summary["probe_result_summary_sha256"] = sha256_json(_payload_without_hash(summary))
        path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def validate_read_only_venue_probe_result_summary(summary: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(summary or {})
    blockers: list[str] = []
    if data.get("version") != SIGNED_TESTNET_PROBE_RESULT_VALIDATOR_VERSION:
        blockers.append("STEP279_PROBE_RESULT_SUMMARY_VERSION_INVALID")
    for field in [
        "read_only_venue_probe_result_summary_id",
        "signed_testnet_read_only_venue_probe_session_id",
        "read_only_venue_probe_session_sha256",
        "testnet_execution_session_id",
        "probe_result_summary_sha256",
    ]:
        if not data.get(field):
            blockers.append(f"STEP279_{field.upper()}_MISSING")
    if data.get("all_read_probes_valid") is not True:
        blockers.append("STEP279_ALL_READ_PROBES_NOT_VALID")
    if data.get("operator_acknowledgement_valid") is not True:
        blockers.append("STEP279_OPERATOR_ACKNOWLEDGEMENT_NOT_VALID")
    if data.get("place_cancel_disabled_evidence_valid") is not True:
        blockers.append("STEP279_PLACE_CANCEL_DISABLED_EVIDENCE_NOT_VALID")
    if data.get("probe_close_report_hash_valid") is not True:
        blockers.append("STEP279_PROBE_CLOSE_REPORT_HASH_NOT_VALID")
    if data.get("probe_evidence_fresh") is not True:
        blockers.append("STEP279_PROBE_EVIDENCE_NOT_FRESH")
    for field in [
        "signed_testnet_execution_allowed",
        "testnet_order_submission_allowed",
        "signed_testnet_promotion_allowed",
        "external_order_submission_allowed",
        "external_order_submission_performed",
        "place_order_enabled",
        "cancel_order_enabled",
        "signed_order_executor_enabled",
    ]:
        if data.get(field) is not False:
            blockers.append(f"STEP279_{field.upper()}_INVARIANT_FAILED")
    if data.get("promotion_remains_blocked") is not True:
        blockers.append("STEP279_PROMOTION_BLOCKER_INVARIANT_MISSING")

    promotion_blocker = data.get("signed_testnet_promotion_blocker") or {}
    if not isinstance(promotion_blocker, Mapping):
        blockers.append("STEP279_PROMOTION_BLOCKER_MISSING")
    else:
        if promotion_blocker.get("promotion_status") != "BLOCKED_BY_DESIGN_STEP279":
            blockers.append("STEP279_PROMOTION_BLOCKER_STATUS_INVALID")
        for field in [
            "signed_testnet_execution_allowed",
            "testnet_order_submission_allowed",
            "signed_testnet_promotion_allowed",
            "external_order_submission_allowed",
            "external_order_submission_performed",
            "place_order_enabled",
            "cancel_order_enabled",
            "signed_order_executor_enabled",
        ]:
            if promotion_blocker.get(field) is not False:
                blockers.append(f"STEP279_PROMOTION_BLOCKER_{field.upper()}_INVARIANT_FAILED")
        expected_blocker_hash = sha256_json(
            {k: v for k, v in dict(promotion_blocker).items() if k not in {"signed_testnet_promotion_blocker_sha256", "created_at_utc"}}
        )
        if promotion_blocker.get("signed_testnet_promotion_blocker_sha256") != expected_blocker_hash:
            blockers.append("STEP279_PROMOTION_BLOCKER_HASH_INVALID")
        if "STEP279_SIGNED_TESTNET_PROMOTION_BLOCKED_PENDING_EXPLICIT_EXECUTION_STEP" not in set(
            promotion_blocker.get("promotion_block_reasons") or []
        ):
            blockers.append("STEP279_PROMOTION_BLOCKER_REQUIRED_REASON_MISSING")

    if data.get("created_at_utc") and not is_canonical_utc_timestamp(data.get("created_at_utc")):
        blockers.append("STEP279_PROBE_RESULT_SUMMARY_TIMESTAMP_NOT_CANONICAL_UTC")
    expected_hash = sha256_json(_payload_without_hash(data))
    if data.get("probe_result_summary_sha256") != expected_hash:
        blockers.append("STEP279_PROBE_RESULT_SUMMARY_HASH_INVALID")
    for reason in data.get("block_reasons") or []:
        blockers.append(str(reason))
    payload = {
        "summary_id": data.get("read_only_venue_probe_result_summary_id"),
        "summary_hash": data.get("probe_result_summary_sha256"),
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_PROBE_RESULT_VALIDATOR_VERSION,
    }
    return {
        "read_only_venue_probe_result_summary_validation_id": stable_id("step279_probe_result_summary_validation", payload),
        "valid": not blockers,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.execution.signed_testnet_execution_readiness_packet import (
    validate_signed_testnet_execution_readiness_packet,
)
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical

SIGNED_TESTNET_DRY_RUN_SESSION_RECORDER_VERSION = "step277_signed_testnet_dry_run_session_recorder_v1"
SIGNED_TESTNET_EXECUTION_ALLOWED_BY_STEP277 = False
TESTNET_ORDER_SUBMISSION_ALLOWED_BY_STEP277 = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_STEP277 = False
PLACE_ORDER_ENABLED_BY_STEP277 = False
SIGNED_ORDER_EXECUTOR_ENABLED_BY_STEP277 = False
ADAPTER_PLACE_ORDER_CALLED_BY_STEP277 = False

_REQUIRED_OPERATOR_ACK_FIELDS = [
    "operator_id",
    "operator_role",
    "execution_ticket_id",
    "operator_signature",
    "timestamp_utc",
    "signed_testnet_execution_readiness_packet_id",
    "execution_readiness_packet_sha256",
    "testnet_execution_session_id",
]

_REQUIRED_ORDER_INTENT_FIELDS = [
    "order_intent_id",
    "symbol",
    "side",
    "order_type",
    "quantity",
    "notional_usdt",
]


def _as_bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _payload_without_hash(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in dict(payload).items()
        if k
        not in {
            "dry_run_session_sha256",
            "created_at_utc",
            "session_recorder_path",
        }
    }


def _event_without_hash(event: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in dict(event).items() if k not in {"event_hash"}}


def _make_event(
    *,
    session_id: str,
    sequence: int,
    event_type: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "event_id": stable_id(
            "step277_session_event",
            {
                "version": SIGNED_TESTNET_DRY_RUN_SESSION_RECORDER_VERSION,
                "session_id": session_id,
                "sequence": sequence,
                "event_type": event_type,
                "details": dict(details or {}),
            },
        ),
        "session_id": session_id,
        "sequence": sequence,
        "event_type": event_type,
        "details": dict(details or {}),
        "created_at_utc": utc_now_canonical(),
    }
    event["event_hash"] = sha256_json(_event_without_hash(event))
    return event


def validate_operator_session_acknowledgement(
    operator_acknowledgement: Mapping[str, Any] | None,
    *,
    readiness_packet: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    data = dict(operator_acknowledgement or {})
    packet = dict(readiness_packet or {})
    blockers: list[str] = []
    for field in _REQUIRED_OPERATOR_ACK_FIELDS:
        if not data.get(field):
            blockers.append(f"STEP277_OPERATOR_ACK_{field.upper()}_MISSING")
    if data.get("timestamp_utc") and not is_canonical_utc_timestamp(data.get("timestamp_utc")):
        blockers.append("STEP277_OPERATOR_ACK_TIMESTAMP_NOT_CANONICAL_UTC")
    if packet:
        if data.get("signed_testnet_execution_readiness_packet_id") != packet.get("signed_testnet_execution_readiness_packet_id"):
            blockers.append("STEP277_OPERATOR_ACK_PACKET_ID_MISMATCH")
        if data.get("execution_readiness_packet_sha256") != packet.get("execution_readiness_packet_sha256"):
            blockers.append("STEP277_OPERATOR_ACK_PACKET_HASH_MISMATCH")
        if data.get("testnet_execution_session_id") != packet.get("testnet_execution_session_id"):
            blockers.append("STEP277_OPERATOR_ACK_SESSION_ID_MISMATCH")
    if data.get("operator_acknowledges_dry_run_only") is not True:
        blockers.append("STEP277_OPERATOR_DRY_RUN_ONLY_ACK_MISSING")
    if data.get("operator_acknowledges_no_external_submission") is not True:
        blockers.append("STEP277_OPERATOR_NO_EXTERNAL_SUBMISSION_ACK_MISSING")
    if data.get("operator_acknowledges_place_order_disabled") is not True:
        blockers.append("STEP277_OPERATOR_PLACE_ORDER_DISABLED_ACK_MISSING")
    if _as_bool(data.get("operator_confirms_order_submission_enabled")):
        blockers.append("STEP277_OPERATOR_CONFIRMS_ORDER_SUBMISSION_ENABLED_BLOCKED")
    if _as_bool(data.get("operator_confirms_place_order_enabled")):
        blockers.append("STEP277_OPERATOR_CONFIRMS_PLACE_ORDER_ENABLED_BLOCKED")
    payload = {
        "operator_acknowledgement": data,
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_DRY_RUN_SESSION_RECORDER_VERSION,
    }
    return {
        "operator_session_ack_validation_id": stable_id("step277_operator_session_ack_validation", payload),
        "valid": not blockers,
        "operator_acknowledgement_sha256": sha256_json(data),
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }


def build_would_submit_order_payload(
    *,
    readiness_packet: Mapping[str, Any],
    order_intent: Mapping[str, Any],
) -> dict[str, Any]:
    intent = dict(order_intent or {})
    missing_fields = [field for field in _REQUIRED_ORDER_INTENT_FIELDS if not intent.get(field)]
    blockers: list[str] = []
    for field in missing_fields:
        blockers.append(f"STEP277_ORDER_INTENT_{field.upper()}_MISSING")
    try:
        quantity = float(intent.get("quantity", 0.0) or 0.0)
    except (TypeError, ValueError):
        quantity = -1.0
    try:
        notional = float(intent.get("notional_usdt", 0.0) or 0.0)
    except (TypeError, ValueError):
        notional = -1.0
    try:
        max_notional = float(intent.get("max_order_notional_usdt") or intent.get("notional_cap_usdt") or 5.0)
    except (TypeError, ValueError):
        max_notional = 5.0
    if quantity <= 0:
        blockers.append("STEP277_ORDER_QUANTITY_NOT_POSITIVE")
    if notional <= 0:
        blockers.append("STEP277_ORDER_NOTIONAL_NOT_POSITIVE")
    if notional > max_notional:
        blockers.append("STEP277_ORDER_NOTIONAL_EXCEEDS_CAP")
    if _as_bool(intent.get("place_order_enabled")):
        blockers.append("STEP277_ORDER_INTENT_PLACE_ORDER_ENABLED_BLOCKED")
    if _as_bool(intent.get("testnet_order_submission_allowed")):
        blockers.append("STEP277_ORDER_INTENT_SUBMISSION_ALLOWED_BLOCKED")
    payload_core = {
        "readiness_packet_id": readiness_packet.get("signed_testnet_execution_readiness_packet_id"),
        "execution_readiness_packet_sha256": readiness_packet.get("execution_readiness_packet_sha256"),
        "testnet_execution_session_id": readiness_packet.get("testnet_execution_session_id"),
        "order_intent_id": intent.get("order_intent_id"),
        "symbol": intent.get("symbol"),
        "side": intent.get("side"),
        "order_type": intent.get("order_type"),
        "quantity": intent.get("quantity"),
        "notional_usdt": intent.get("notional_usdt"),
        "time_in_force": intent.get("time_in_force", "GTC"),
        "reduce_only": bool(intent.get("reduce_only", False)),
        "client_order_id": stable_id(
            "would_submit_client_order",
            {
                "session_id": readiness_packet.get("testnet_execution_session_id"),
                "order_intent_id": intent.get("order_intent_id"),
                "symbol": intent.get("symbol"),
                "side": intent.get("side"),
                "quantity": intent.get("quantity"),
                "notional_usdt": intent.get("notional_usdt"),
            },
        ),
        "dry_run_only": True,
        "would_submit_only": True,
        "place_order_enabled": PLACE_ORDER_ENABLED_BY_STEP277,
        "testnet_order_submission_allowed": TESTNET_ORDER_SUBMISSION_ALLOWED_BY_STEP277,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_STEP277,
        "adapter_place_order_called": ADAPTER_PLACE_ORDER_CALLED_BY_STEP277,
        "block_reasons": sorted(set(blockers)),
    }
    payload = {
        "would_submit_order_payload_id": stable_id("would_submit_order_payload", payload_core),
        "version": SIGNED_TESTNET_DRY_RUN_SESSION_RECORDER_VERSION,
        **payload_core,
        "valid": not blockers,
        "created_at_utc": utc_now_canonical(),
    }
    payload["would_submit_order_payload_sha256"] = sha256_json(
        {k: v for k, v in payload.items() if k not in {"would_submit_order_payload_sha256", "created_at_utc"}}
    )
    return payload


def build_pre_submit_checklist(
    *,
    readiness_packet: Mapping[str, Any],
    would_submit_order_payload: Mapping[str, Any],
    operator_acknowledgement_validation: Mapping[str, Any],
) -> dict[str, Any]:
    packet_validation = validate_signed_testnet_execution_readiness_packet(readiness_packet)
    blockers: list[str] = []
    blockers.extend(packet_validation.get("block_reasons", []))
    for field, expected in {
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "signed_order_executor_enabled": False,
        "order_submission_remains_disabled": True,
    }.items():
        if readiness_packet.get(field) is not expected:
            blockers.append(f"STEP277_READINESS_PACKET_{field.upper()}_INVARIANT_FAILED")
    if readiness_packet.get("packet_review_ready") is not True:
        blockers.append("STEP277_READINESS_PACKET_NOT_REVIEW_READY")
    if would_submit_order_payload.get("valid") is not True:
        blockers.append("STEP277_WOULD_SUBMIT_PAYLOAD_NOT_VALID")
    if would_submit_order_payload.get("dry_run_only") is not True:
        blockers.append("STEP277_WOULD_SUBMIT_PAYLOAD_DRY_RUN_ONLY_MISSING")
    if would_submit_order_payload.get("place_order_enabled") is not False:
        blockers.append("STEP277_WOULD_SUBMIT_PLACE_ORDER_ENABLED_BLOCKED")
    if would_submit_order_payload.get("testnet_order_submission_allowed") is not False:
        blockers.append("STEP277_WOULD_SUBMIT_ORDER_SUBMISSION_ALLOWED_BLOCKED")
    if would_submit_order_payload.get("external_order_submission_performed") is not False:
        blockers.append("STEP277_WOULD_SUBMIT_EXTERNAL_SUBMISSION_PERFORMED")
    if would_submit_order_payload.get("adapter_place_order_called") is not False:
        blockers.append("STEP277_ADAPTER_PLACE_ORDER_WAS_CALLED_BLOCKED")
    if operator_acknowledgement_validation.get("valid") is not True:
        blockers.extend(operator_acknowledgement_validation.get("block_reasons", []))
    checks = {
        "readiness_packet_valid": packet_validation.get("valid") is True,
        "readiness_packet_review_ready": readiness_packet.get("packet_review_ready") is True,
        "would_submit_payload_valid": would_submit_order_payload.get("valid") is True,
        "operator_acknowledgement_valid": operator_acknowledgement_validation.get("valid") is True,
        "place_order_disabled": readiness_packet.get("place_order_enabled") is False
        and would_submit_order_payload.get("place_order_enabled") is False,
        "testnet_submission_disabled": readiness_packet.get("testnet_order_submission_allowed") is False
        and would_submit_order_payload.get("testnet_order_submission_allowed") is False,
        "external_submission_not_performed": readiness_packet.get("external_order_submission_performed") is False
        and would_submit_order_payload.get("external_order_submission_performed") is False,
        "adapter_place_order_not_called": would_submit_order_payload.get("adapter_place_order_called") is False,
    }
    payload = {
        "version": SIGNED_TESTNET_DRY_RUN_SESSION_RECORDER_VERSION,
        "testnet_execution_session_id": readiness_packet.get("testnet_execution_session_id"),
        "would_submit_order_payload_id": would_submit_order_payload.get("would_submit_order_payload_id"),
        "operator_session_ack_validation_id": operator_acknowledgement_validation.get("operator_session_ack_validation_id"),
        "checks": checks,
        "blockers": sorted(set(blockers)),
    }
    checklist = {
        "pre_submit_checklist_id": stable_id("step277_pre_submit_checklist", payload),
        **payload,
        "valid": not blockers and all(checks.values()),
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }
    checklist["pre_submit_checklist_sha256"] = sha256_json(
        {k: v for k, v in checklist.items() if k not in {"pre_submit_checklist_sha256", "created_at_utc"}}
    )
    return checklist


def _build_session_close_report(
    *,
    session_id: str,
    event_log: list[dict[str, Any]],
    pre_submit_checklist: Mapping[str, Any],
    would_submit_order_payload: Mapping[str, Any],
    operator_ack_validation: Mapping[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    if pre_submit_checklist.get("valid") is not True:
        blockers.extend(pre_submit_checklist.get("block_reasons", []))
    if would_submit_order_payload.get("external_order_submission_performed") is not False:
        blockers.append("STEP277_CLOSE_REPORT_EXTERNAL_SUBMISSION_PERFORMED")
    if would_submit_order_payload.get("adapter_place_order_called") is not False:
        blockers.append("STEP277_CLOSE_REPORT_ADAPTER_PLACE_ORDER_CALLED")
    if operator_ack_validation.get("valid") is not True:
        blockers.extend(operator_ack_validation.get("block_reasons", []))
    event_hashes = [event.get("event_hash") for event in event_log]
    event_log_sha256 = sha256_json(event_log)
    payload = {
        "version": SIGNED_TESTNET_DRY_RUN_SESSION_RECORDER_VERSION,
        "testnet_execution_session_id": session_id,
        "event_count": len(event_log),
        "event_hashes": event_hashes,
        "event_log_sha256": event_log_sha256,
        "pre_submit_checklist_id": pre_submit_checklist.get("pre_submit_checklist_id"),
        "would_submit_order_payload_id": would_submit_order_payload.get("would_submit_order_payload_id"),
        "operator_session_ack_validation_id": operator_ack_validation.get("operator_session_ack_validation_id"),
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_STEP277,
        "adapter_place_order_called": ADAPTER_PLACE_ORDER_CALLED_BY_STEP277,
        "session_closed": True,
        "blockers": sorted(set(blockers)),
    }
    report = {
        "session_close_report_id": stable_id("step277_session_close_report", payload),
        **payload,
        "valid": not blockers,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }
    report["session_close_report_sha256"] = sha256_json(
        {k: v for k, v in report.items() if k not in {"session_close_report_sha256", "created_at_utc"}}
    )
    return report


def build_signed_testnet_dry_run_session_recorder(
    *,
    execution_readiness_packet: Mapping[str, Any],
    operator_acknowledgement: Mapping[str, Any],
    order_intent: Mapping[str, Any],
    session_reason: str = "signed_testnet_dry_run_session_review_only",
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    packet = dict(execution_readiness_packet or {})
    session_id = packet.get("testnet_execution_session_id") or stable_id("testnet_execution_session", packet)
    packet_validation = validate_signed_testnet_execution_readiness_packet(packet)
    operator_ack_validation = validate_operator_session_acknowledgement(
        operator_acknowledgement,
        readiness_packet=packet,
    )
    would_submit_payload = build_would_submit_order_payload(
        readiness_packet=packet,
        order_intent=order_intent,
    )
    pre_submit_checklist = build_pre_submit_checklist(
        readiness_packet=packet,
        would_submit_order_payload=would_submit_payload,
        operator_acknowledgement_validation=operator_ack_validation,
    )

    event_log = [
        _make_event(
            session_id=session_id,
            sequence=1,
            event_type="SESSION_CREATED",
            details={"session_reason": session_reason},
        ),
        _make_event(
            session_id=session_id,
            sequence=2,
            event_type="READINESS_PACKET_VALIDATED",
            details={
                "validation_id": packet_validation.get("signed_testnet_execution_readiness_packet_validation_id"),
                "valid": packet_validation.get("valid"),
            },
        ),
        _make_event(
            session_id=session_id,
            sequence=3,
            event_type="WOULD_SUBMIT_PAYLOAD_RENDERED",
            details={
                "would_submit_order_payload_id": would_submit_payload.get("would_submit_order_payload_id"),
                "place_order_enabled": False,
                "adapter_place_order_called": False,
            },
        ),
        _make_event(
            session_id=session_id,
            sequence=4,
            event_type="PRE_SUBMIT_CHECKLIST_COMPLETED",
            details={
                "pre_submit_checklist_id": pre_submit_checklist.get("pre_submit_checklist_id"),
                "valid": pre_submit_checklist.get("valid"),
            },
        ),
        _make_event(
            session_id=session_id,
            sequence=5,
            event_type="OPERATOR_ACKNOWLEDGED_DRY_RUN_ONLY",
            details={
                "operator_session_ack_validation_id": operator_ack_validation.get("operator_session_ack_validation_id"),
                "valid": operator_ack_validation.get("valid"),
            },
        ),
        _make_event(
            session_id=session_id,
            sequence=6,
            event_type="EXTERNAL_SUBMISSION_SKIPPED_BY_DESIGN",
            details={
                "external_order_submission_performed": False,
                "place_order_enabled": False,
                "adapter_place_order_called": False,
            },
        ),
        _make_event(
            session_id=session_id,
            sequence=7,
            event_type="SESSION_CLOSED_REVIEW_ONLY",
            details={"session_closed": True},
        ),
    ]
    close_report = _build_session_close_report(
        session_id=session_id,
        event_log=event_log,
        pre_submit_checklist=pre_submit_checklist,
        would_submit_order_payload=would_submit_payload,
        operator_ack_validation=operator_ack_validation,
    )

    blockers: list[str] = []
    blockers.extend(packet_validation.get("block_reasons", []))
    blockers.extend(operator_ack_validation.get("block_reasons", []))
    blockers.extend(would_submit_payload.get("block_reasons", []))
    blockers.extend(pre_submit_checklist.get("block_reasons", []))
    blockers.extend(close_report.get("block_reasons", []))
    if packet.get("packet_review_ready") is not True:
        blockers.append("STEP277_EXECUTION_READINESS_PACKET_NOT_REVIEW_READY")
    if packet.get("ready_for_signed_testnet_execution") is not False:
        blockers.append("STEP277_PACKET_EXECUTION_READY_NOT_FALSE")
    if packet.get("testnet_order_submission_allowed") is not False:
        blockers.append("STEP277_PACKET_ORDER_SUBMISSION_ALLOWED_NOT_FALSE")
    if packet.get("place_order_enabled") is not False:
        blockers.append("STEP277_PACKET_PLACE_ORDER_ENABLED_BLOCKED")

    session_review_ready = not blockers
    recorder = {
        "signed_testnet_dry_run_session_recorder_id": stable_id(
            "signed_testnet_dry_run_session_recorder",
            {
                "version": SIGNED_TESTNET_DRY_RUN_SESSION_RECORDER_VERSION,
                "session_id": session_id,
                "readiness_packet_sha256": packet.get("execution_readiness_packet_sha256"),
                "would_submit_order_payload_sha256": would_submit_payload.get("would_submit_order_payload_sha256"),
                "pre_submit_checklist_sha256": pre_submit_checklist.get("pre_submit_checklist_sha256"),
                "session_close_report_sha256": close_report.get("session_close_report_sha256"),
                "blockers": sorted(set(blockers)),
            },
        ),
        "version": SIGNED_TESTNET_DRY_RUN_SESSION_RECORDER_VERSION,
        "signed_testnet_execution_readiness_packet_id": packet.get("signed_testnet_execution_readiness_packet_id"),
        "execution_readiness_packet_sha256": packet.get("execution_readiness_packet_sha256"),
        "testnet_execution_session_id": session_id,
        "operator_acknowledgement_validation": operator_ack_validation,
        "would_submit_order_payload": would_submit_payload,
        "pre_submit_checklist": pre_submit_checklist,
        "session_event_log": event_log,
        "session_event_log_sha256": sha256_json(event_log),
        "session_close_report": close_report,
        "session_review_ready": session_review_ready,
        "ready_for_signed_testnet_execution": SIGNED_TESTNET_EXECUTION_ALLOWED_BY_STEP277,
        "testnet_order_submission_allowed": TESTNET_ORDER_SUBMISSION_ALLOWED_BY_STEP277,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_STEP277,
        "place_order_enabled": PLACE_ORDER_ENABLED_BY_STEP277,
        "signed_order_executor_enabled": SIGNED_ORDER_EXECUTOR_ENABLED_BY_STEP277,
        "adapter_place_order_called": ADAPTER_PLACE_ORDER_CALLED_BY_STEP277,
        "order_submission_remains_disabled": True,
        "block_reasons": sorted(set(blockers)),
        "session_reason": session_reason,
        "created_at_utc": utc_now_canonical(),
    }
    recorder["dry_run_session_sha256"] = sha256_json(_payload_without_hash(recorder))
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        recorder["session_recorder_path"] = str(path)
        recorder["dry_run_session_sha256"] = sha256_json(_payload_without_hash(recorder))
        path.write_text(json.dumps(recorder, indent=2, sort_keys=True), encoding="utf-8")
    return recorder


def validate_signed_testnet_dry_run_session_recorder(recorder: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(recorder or {})
    blockers: list[str] = []
    if data.get("version") != SIGNED_TESTNET_DRY_RUN_SESSION_RECORDER_VERSION:
        blockers.append("STEP277_DRY_RUN_SESSION_RECORDER_VERSION_INVALID")
    for field in [
        "signed_testnet_dry_run_session_recorder_id",
        "signed_testnet_execution_readiness_packet_id",
        "execution_readiness_packet_sha256",
        "testnet_execution_session_id",
        "dry_run_session_sha256",
    ]:
        if not data.get(field):
            blockers.append(f"STEP277_{field.upper()}_MISSING")
    if data.get("ready_for_signed_testnet_execution") is not False:
        blockers.append("STEP277_RECORDER_EXECUTION_READY_NOT_FALSE")
    if data.get("testnet_order_submission_allowed") is not False:
        blockers.append("STEP277_RECORDER_ORDER_SUBMISSION_ALLOWED_NOT_FALSE")
    if data.get("external_order_submission_performed") is not False:
        blockers.append("STEP277_RECORDER_EXTERNAL_SUBMISSION_PERFORMED")
    if data.get("place_order_enabled") is not False:
        blockers.append("STEP277_RECORDER_PLACE_ORDER_ENABLED")
    if data.get("signed_order_executor_enabled") is not False:
        blockers.append("STEP277_RECORDER_SIGNED_EXECUTOR_ENABLED")
    if data.get("adapter_place_order_called") is not False:
        blockers.append("STEP277_RECORDER_ADAPTER_PLACE_ORDER_CALLED")
    if data.get("order_submission_remains_disabled") is not True:
        blockers.append("STEP277_RECORDER_ORDER_SUBMISSION_DISABLED_INVARIANT_MISSING")
    if not isinstance(data.get("would_submit_order_payload"), Mapping):
        blockers.append("STEP277_WOULD_SUBMIT_ORDER_PAYLOAD_MISSING")
    if not isinstance(data.get("pre_submit_checklist"), Mapping):
        blockers.append("STEP277_PRE_SUBMIT_CHECKLIST_MISSING")
    if not isinstance(data.get("session_close_report"), Mapping):
        blockers.append("STEP277_SESSION_CLOSE_REPORT_MISSING")
    event_log = data.get("session_event_log")
    if not isinstance(event_log, list) or len(event_log) < 7:
        blockers.append("STEP277_SESSION_EVENT_LOG_INCOMPLETE")
    else:
        expected_sequence = list(range(1, len(event_log) + 1))
        actual_sequence = [event.get("sequence") for event in event_log]
        if actual_sequence != expected_sequence:
            blockers.append("STEP277_SESSION_EVENT_LOG_SEQUENCE_INVALID")
        for event in event_log:
            if event.get("event_hash") != sha256_json(_event_without_hash(event)):
                blockers.append("STEP277_SESSION_EVENT_HASH_INVALID")
                break
        if data.get("session_event_log_sha256") != sha256_json(event_log):
            blockers.append("STEP277_SESSION_EVENT_LOG_HASH_INVALID")
    close_report = data.get("session_close_report") or {}
    if isinstance(close_report, Mapping):
        if close_report.get("external_order_submission_performed") is not False:
            blockers.append("STEP277_CLOSE_REPORT_EXTERNAL_SUBMISSION_PERFORMED")
        if close_report.get("adapter_place_order_called") is not False:
            blockers.append("STEP277_CLOSE_REPORT_ADAPTER_PLACE_ORDER_CALLED")
        expected_close_hash = sha256_json({k: v for k, v in dict(close_report).items() if k not in {"session_close_report_sha256", "created_at_utc"}})
        if close_report.get("session_close_report_sha256") != expected_close_hash:
            blockers.append("STEP277_SESSION_CLOSE_REPORT_HASH_INVALID")
    expected_hash = sha256_json(_payload_without_hash(data))
    if data.get("dry_run_session_sha256") != expected_hash:
        blockers.append("STEP277_DRY_RUN_SESSION_HASH_INVALID")
    for reason in data.get("block_reasons") or []:
        blockers.append(str(reason))
    payload = {
        "recorder_id": data.get("signed_testnet_dry_run_session_recorder_id"),
        "session_id": data.get("testnet_execution_session_id"),
        "dry_run_session_sha256": data.get("dry_run_session_sha256"),
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_DRY_RUN_SESSION_RECORDER_VERSION,
    }
    return {
        "signed_testnet_dry_run_session_recorder_validation_id": stable_id("step277_dry_run_session_recorder_validation", payload),
        "valid": not blockers,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }

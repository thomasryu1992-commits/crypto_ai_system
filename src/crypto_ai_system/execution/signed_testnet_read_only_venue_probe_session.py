from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.execution.exchange_adapter_contract import (
    DisabledExchangeAdapter,
    validate_adapter_capabilities,
)
from crypto_ai_system.execution.signed_testnet_dry_run_session_recorder import (
    validate_signed_testnet_dry_run_session_recorder,
)
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical

SIGNED_TESTNET_READ_ONLY_VENUE_PROBE_SESSION_VERSION = "step278_signed_testnet_read_only_venue_probe_session_v1"
SIGNED_TESTNET_EXECUTION_ALLOWED_BY_STEP278 = False
TESTNET_ORDER_SUBMISSION_ALLOWED_BY_STEP278 = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_STEP278 = False
PLACE_ORDER_ENABLED_BY_STEP278 = False
CANCEL_ORDER_ENABLED_BY_STEP278 = False
SIGNED_ORDER_EXECUTOR_ENABLED_BY_STEP278 = False
ADAPTER_PLACE_ORDER_CALLED_BY_STEP278 = False
ADAPTER_CANCEL_ORDER_CALLED_BY_STEP278 = False

_REQUIRED_OPERATOR_PROBE_ACK_FIELDS = [
    "operator_id",
    "operator_role",
    "probe_ticket_id",
    "operator_signature",
    "timestamp_utc",
    "signed_testnet_dry_run_session_recorder_id",
    "dry_run_session_sha256",
    "testnet_execution_session_id",
]

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


def _as_bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _payload_without_hash(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in dict(payload).items()
        if k
        not in {
            "read_only_venue_probe_session_sha256",
            "created_at_utc",
            "probe_session_path",
        }
    }


def _event_without_hash(event: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in dict(event).items() if k not in {"event_hash"}}


def _parse_canonical_utc(value: Any) -> datetime | None:
    if not is_canonical_utc_timestamp(value):
        return None
    return datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _age_sec(value: Any) -> int | None:
    parsed = _parse_canonical_utc(value)
    if parsed is None:
        return None
    return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))


def _hash_probe(probe: Mapping[str, Any]) -> str:
    return sha256_json({k: v for k, v in dict(probe).items() if k not in {"probe_hash"}})


def _make_event(
    *,
    session_id: str,
    sequence: int,
    event_type: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "event_id": stable_id(
            "step278_read_only_probe_event",
            {
                "version": SIGNED_TESTNET_READ_ONLY_VENUE_PROBE_SESSION_VERSION,
                "session_id": session_id,
                "sequence": sequence,
                "event_type": event_type,
                "details": dict(details or {}),
            },
        ),
        "testnet_execution_session_id": session_id,
        "sequence": sequence,
        "event_type": event_type,
        "details": dict(details or {}),
        "created_at_utc": utc_now_canonical(),
    }
    event["event_hash"] = sha256_json(_event_without_hash(event))
    return event


def validate_operator_read_only_probe_acknowledgement(
    operator_acknowledgement: Mapping[str, Any] | None,
    *,
    dry_run_session_recorder: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    data = dict(operator_acknowledgement or {})
    recorder = dict(dry_run_session_recorder or {})
    blockers: list[str] = []
    for field in _REQUIRED_OPERATOR_PROBE_ACK_FIELDS:
        if not data.get(field):
            blockers.append(f"STEP278_OPERATOR_PROBE_ACK_{field.upper()}_MISSING")
    if data.get("timestamp_utc") and not is_canonical_utc_timestamp(data.get("timestamp_utc")):
        blockers.append("STEP278_OPERATOR_PROBE_ACK_TIMESTAMP_NOT_CANONICAL_UTC")
    if recorder:
        if data.get("signed_testnet_dry_run_session_recorder_id") != recorder.get("signed_testnet_dry_run_session_recorder_id"):
            blockers.append("STEP278_OPERATOR_PROBE_ACK_DRY_RUN_RECORDER_ID_MISMATCH")
        if data.get("dry_run_session_sha256") != recorder.get("dry_run_session_sha256"):
            blockers.append("STEP278_OPERATOR_PROBE_ACK_DRY_RUN_HASH_MISMATCH")
        if data.get("testnet_execution_session_id") != recorder.get("testnet_execution_session_id"):
            blockers.append("STEP278_OPERATOR_PROBE_ACK_SESSION_ID_MISMATCH")
    if data.get("operator_acknowledges_read_only_probe_only") is not True:
        blockers.append("STEP278_OPERATOR_READ_ONLY_PROBE_ONLY_ACK_MISSING")
    if data.get("operator_acknowledges_no_order_submission") is not True:
        blockers.append("STEP278_OPERATOR_NO_ORDER_SUBMISSION_ACK_MISSING")
    if data.get("operator_acknowledges_place_order_disabled") is not True:
        blockers.append("STEP278_OPERATOR_PLACE_ORDER_DISABLED_ACK_MISSING")
    if data.get("operator_acknowledges_cancel_order_disabled") is not True:
        blockers.append("STEP278_OPERATOR_CANCEL_ORDER_DISABLED_ACK_MISSING")
    if _as_bool(data.get("operator_confirms_order_submission_enabled")):
        blockers.append("STEP278_OPERATOR_CONFIRMS_ORDER_SUBMISSION_ENABLED_BLOCKED")
    if _as_bool(data.get("operator_confirms_place_order_enabled")):
        blockers.append("STEP278_OPERATOR_CONFIRMS_PLACE_ORDER_ENABLED_BLOCKED")
    if _as_bool(data.get("operator_confirms_cancel_order_enabled")):
        blockers.append("STEP278_OPERATOR_CONFIRMS_CANCEL_ORDER_ENABLED_BLOCKED")
    payload = {
        "operator_acknowledgement": data,
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_READ_ONLY_VENUE_PROBE_SESSION_VERSION,
    }
    return {
        "operator_read_only_probe_ack_validation_id": stable_id("step278_operator_probe_ack_validation", payload),
        "valid": not blockers,
        "operator_probe_acknowledgement_sha256": sha256_json(data),
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }


def _build_read_probe(
    *,
    probe_name: str,
    adapter_response: Mapping[str, Any],
    required_status: str,
) -> dict[str, Any]:
    response = dict(adapter_response or {})
    blockers: list[str] = []
    if response.get("status") != required_status:
        blockers.append(f"STEP278_{probe_name.upper()}_STATUS_INVALID")
    if response.get("external_order_submission_performed") is not False:
        blockers.append(f"STEP278_{probe_name.upper()}_EXTERNAL_SUBMISSION_PERFORMED")
    if response.get("order_submission_enabled_by_contract") is not False:
        blockers.append(f"STEP278_{probe_name.upper()}_ORDER_SUBMISSION_ENABLED")
    if response.get("created_at_utc") and not is_canonical_utc_timestamp(response.get("created_at_utc")):
        blockers.append(f"STEP278_{probe_name.upper()}_TIMESTAMP_NOT_CANONICAL_UTC")
    probe = {
        "probe_name": probe_name,
        "status": response.get("status"),
        "adapter_response": response,
        "external_order_submission_performed": False,
        "order_submission_enabled_by_contract": False,
        "valid": not blockers,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }
    probe["probe_hash"] = _hash_probe(probe)
    return probe


def _build_blocked_submission_contract_probe(
    *,
    probe_name: str,
    capabilities: Mapping[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    capability_flag = "supports_place_order" if probe_name == "place_order_block_probe" else "supports_cancel_order"
    if capabilities.get(capability_flag) is True:
        blockers.append(f"STEP278_{probe_name.upper()}_CAPABILITY_ENABLED_BLOCKED")
    probe = {
        "probe_name": probe_name,
        "probe_method": "capability_contract_inspection_only",
        "adapter_method_called": False,
        "status": f"{probe_name.upper()}_DISABLED_BY_CONTRACT_STEP278",
        "capability_flag": capability_flag,
        "capability_enabled": capabilities.get(capability_flag) is True,
        "external_order_submission_performed": False,
        "order_submission_enabled_by_contract": False,
        "valid": not blockers,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }
    probe["probe_hash"] = _hash_probe(probe)
    return probe


def build_read_only_venue_probe_evidence(
    *,
    adapter: DisabledExchangeAdapter,
    order_intent: Mapping[str, Any],
    symbol: str = "BTCUSDT",
    fetch_order_id: str | None = None,
) -> dict[str, Any]:
    capabilities = adapter.get_capabilities()
    adapter_validation = validate_adapter_capabilities(capabilities)
    fetch_id = fetch_order_id or str(order_intent.get("exchange_order_id") or "fetch_order_probe_review_only")
    probes = {
        "balance_read_probe": _build_read_probe(
            probe_name="balance_read_probe",
            adapter_response=adapter.get_balance(),
            required_status="BALANCE_READ_CONTRACT_ONLY",
        ),
        "positions_read_probe": _build_read_probe(
            probe_name="positions_read_probe",
            adapter_response=adapter.get_positions(),
            required_status="POSITIONS_READ_CONTRACT_ONLY",
        ),
        "open_orders_read_probe": _build_read_probe(
            probe_name="open_orders_read_probe",
            adapter_response=adapter.get_open_orders(),
            required_status="OPEN_ORDERS_READ_CONTRACT_ONLY",
        ),
        "orderbook_read_probe": _build_read_probe(
            probe_name="orderbook_read_probe",
            adapter_response=adapter.get_orderbook(symbol),
            required_status="ORDERBOOK_READ_CONTRACT_ONLY",
        ),
        "fee_estimate_probe": _build_read_probe(
            probe_name="fee_estimate_probe",
            adapter_response=adapter.estimate_fee(order_intent),
            required_status="FEE_ESTIMATE_CONTRACT_ONLY",
        ),
        "slippage_estimate_probe": _build_read_probe(
            probe_name="slippage_estimate_probe",
            adapter_response=adapter.estimate_slippage(order_intent),
            required_status="SLIPPAGE_ESTIMATE_CONTRACT_ONLY",
        ),
        "min_order_size_probe": _build_read_probe(
            probe_name="min_order_size_probe",
            adapter_response=adapter.validate_min_order_size(order_intent),
            required_status="MIN_ORDER_SIZE_VALIDATION_CONTRACT_ONLY",
        ),
        "fetch_order_probe": _build_read_probe(
            probe_name="fetch_order_probe",
            adapter_response=adapter.fetch_order(fetch_id),
            required_status="FETCH_ORDER_CONTRACT_ONLY",
        ),
        "place_order_block_probe": _build_blocked_submission_contract_probe(
            probe_name="place_order_block_probe",
            capabilities=capabilities,
        ),
        "cancel_order_block_probe": _build_blocked_submission_contract_probe(
            probe_name="cancel_order_block_probe",
            capabilities=capabilities,
        ),
    }
    blockers: list[str] = []
    blockers.extend(adapter_validation.get("block_reasons", []))
    for name, probe in probes.items():
        if probe.get("valid") is not True:
            blockers.extend(probe.get("block_reasons", []))
            blockers.append(f"STEP278_{name.upper()}_INVALID")
    if probes["min_order_size_probe"].get("adapter_response", {}).get("min_order_size_valid") is not True:
        blockers.append("STEP278_MIN_ORDER_SIZE_PROBE_INVALID")

    evidence_payload = {
        "version": SIGNED_TESTNET_READ_ONLY_VENUE_PROBE_SESSION_VERSION,
        "adapter_contract_validation_id": adapter_validation.get("adapter_contract_validation_id"),
        "adapter_contract_validation": adapter_validation,
        "order_intent_id": order_intent.get("order_intent_id"),
        "symbol": symbol,
        **probes,
        "probe_names": list(probes.keys()),
        "external_order_submission_performed": False,
        "adapter_place_order_called": False,
        "adapter_cancel_order_called": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "blockers": sorted(set(blockers)),
    }
    evidence = {
        "read_only_venue_probe_evidence_id": stable_id("step278_read_only_venue_probe_evidence", evidence_payload),
        **evidence_payload,
        "valid": not blockers,
        "created_at_utc": utc_now_canonical(),
    }
    evidence["read_only_venue_probe_evidence_sha256"] = sha256_json(
        {k: v for k, v in evidence.items() if k not in {"read_only_venue_probe_evidence_sha256", "created_at_utc"}}
    )
    return evidence


def _build_probe_close_report(
    *,
    session_id: str,
    event_log: list[dict[str, Any]],
    probe_evidence: Mapping[str, Any],
    operator_ack_validation: Mapping[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    if probe_evidence.get("valid") is not True:
        blockers.extend(probe_evidence.get("blockers", []))
    if operator_ack_validation.get("valid") is not True:
        blockers.extend(operator_ack_validation.get("block_reasons", []))
    if probe_evidence.get("external_order_submission_performed") is not False:
        blockers.append("STEP278_CLOSE_REPORT_EXTERNAL_SUBMISSION_PERFORMED")
    if probe_evidence.get("adapter_place_order_called") is not False:
        blockers.append("STEP278_CLOSE_REPORT_ADAPTER_PLACE_ORDER_CALLED")
    if probe_evidence.get("adapter_cancel_order_called") is not False:
        blockers.append("STEP278_CLOSE_REPORT_ADAPTER_CANCEL_ORDER_CALLED")
    event_hashes = [event.get("event_hash") for event in event_log]
    event_log_sha256 = sha256_json(event_log)
    payload = {
        "version": SIGNED_TESTNET_READ_ONLY_VENUE_PROBE_SESSION_VERSION,
        "testnet_execution_session_id": session_id,
        "event_count": len(event_log),
        "event_hashes": event_hashes,
        "event_log_sha256": event_log_sha256,
        "read_only_venue_probe_evidence_id": probe_evidence.get("read_only_venue_probe_evidence_id"),
        "read_only_venue_probe_evidence_sha256": probe_evidence.get("read_only_venue_probe_evidence_sha256"),
        "operator_read_only_probe_ack_validation_id": operator_ack_validation.get("operator_read_only_probe_ack_validation_id"),
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_STEP278,
        "adapter_place_order_called": ADAPTER_PLACE_ORDER_CALLED_BY_STEP278,
        "adapter_cancel_order_called": ADAPTER_CANCEL_ORDER_CALLED_BY_STEP278,
        "probe_session_closed": True,
        "blockers": sorted(set(blockers)),
    }
    report = {
        "read_only_probe_close_report_id": stable_id("step278_read_only_probe_close_report", payload),
        **payload,
        "valid": not blockers,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }
    report["read_only_probe_close_report_sha256"] = sha256_json(
        {k: v for k, v in report.items() if k not in {"read_only_probe_close_report_sha256", "created_at_utc"}}
    )
    return report


def build_signed_testnet_read_only_venue_probe_session(
    *,
    dry_run_session_recorder: Mapping[str, Any],
    operator_acknowledgement: Mapping[str, Any],
    order_intent: Mapping[str, Any],
    adapter: DisabledExchangeAdapter | None = None,
    symbol: str = "BTCUSDT",
    fetch_order_id: str | None = None,
    max_probe_age_sec: int = 600,
    session_reason: str = "signed_testnet_read_only_venue_probe_review_only",
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    adapter = adapter or DisabledExchangeAdapter()
    recorder = dict(dry_run_session_recorder or {})
    session_id = recorder.get("testnet_execution_session_id") or stable_id("testnet_execution_session", recorder)
    dry_run_validation = validate_signed_testnet_dry_run_session_recorder(recorder)
    operator_ack_validation = validate_operator_read_only_probe_acknowledgement(
        operator_acknowledgement,
        dry_run_session_recorder=recorder,
    )
    probe_evidence = build_read_only_venue_probe_evidence(
        adapter=adapter,
        order_intent=order_intent,
        symbol=symbol,
        fetch_order_id=fetch_order_id,
    )

    event_log = [
        _make_event(session_id=session_id, sequence=1, event_type="READ_ONLY_PROBE_SESSION_CREATED", details={"session_reason": session_reason}),
        _make_event(session_id=session_id, sequence=2, event_type="STEP277_DRY_RUN_SESSION_VALIDATED", details={"valid": dry_run_validation.get("valid"), "validation_id": dry_run_validation.get("signed_testnet_dry_run_session_recorder_validation_id")}),
        _make_event(session_id=session_id, sequence=3, event_type="BALANCE_READ_PROBED", details={"probe_hash": probe_evidence["balance_read_probe"].get("probe_hash")}),
        _make_event(session_id=session_id, sequence=4, event_type="POSITIONS_READ_PROBED", details={"probe_hash": probe_evidence["positions_read_probe"].get("probe_hash")}),
        _make_event(session_id=session_id, sequence=5, event_type="OPEN_ORDERS_READ_PROBED", details={"probe_hash": probe_evidence["open_orders_read_probe"].get("probe_hash")}),
        _make_event(session_id=session_id, sequence=6, event_type="ORDERBOOK_READ_PROBED", details={"probe_hash": probe_evidence["orderbook_read_probe"].get("probe_hash")}),
        _make_event(session_id=session_id, sequence=7, event_type="FEE_SLIPPAGE_MIN_ORDER_PROBED", details={"fee_probe_hash": probe_evidence["fee_estimate_probe"].get("probe_hash"), "slippage_probe_hash": probe_evidence["slippage_estimate_probe"].get("probe_hash"), "min_order_probe_hash": probe_evidence["min_order_size_probe"].get("probe_hash")}),
        _make_event(session_id=session_id, sequence=8, event_type="FETCH_ORDER_READ_ONLY_PROBED", details={"probe_hash": probe_evidence["fetch_order_probe"].get("probe_hash")}),
        _make_event(session_id=session_id, sequence=9, event_type="PLACE_CANCEL_ORDER_SKIPPED_BY_DESIGN", details={"place_order_called": False, "cancel_order_called": False}),
        _make_event(session_id=session_id, sequence=10, event_type="READ_ONLY_PROBE_SESSION_CLOSED", details={"probe_session_closed": True}),
    ]
    close_report = _build_probe_close_report(
        session_id=session_id,
        event_log=event_log,
        probe_evidence=probe_evidence,
        operator_ack_validation=operator_ack_validation,
    )

    blockers: list[str] = []
    blockers.extend(dry_run_validation.get("block_reasons", []))
    blockers.extend(operator_ack_validation.get("block_reasons", []))
    blockers.extend(probe_evidence.get("blockers", []))
    blockers.extend(close_report.get("block_reasons", []))
    if recorder.get("session_review_ready") is not True:
        blockers.append("STEP278_DRY_RUN_SESSION_NOT_REVIEW_READY")
    if recorder.get("ready_for_signed_testnet_execution") is not False:
        blockers.append("STEP278_DRY_RUN_EXECUTION_READY_NOT_FALSE")
    if recorder.get("testnet_order_submission_allowed") is not False:
        blockers.append("STEP278_DRY_RUN_ORDER_SUBMISSION_ALLOWED_NOT_FALSE")
    if recorder.get("external_order_submission_performed") is not False:
        blockers.append("STEP278_DRY_RUN_EXTERNAL_SUBMISSION_PERFORMED")
    if recorder.get("adapter_place_order_called") is not False:
        blockers.append("STEP278_DRY_RUN_ADAPTER_PLACE_ORDER_CALLED")
    probe_age = _age_sec(probe_evidence.get("created_at_utc"))
    if probe_age is None:
        blockers.append("STEP278_PROBE_EVIDENCE_TIMESTAMP_NOT_CANONICAL_UTC")
    elif probe_age > max_probe_age_sec:
        blockers.append("STEP278_PROBE_EVIDENCE_STALE_BLOCKED")

    session_review_ready = not blockers
    session = {
        "signed_testnet_read_only_venue_probe_session_id": stable_id(
            "step278_read_only_venue_probe_session",
            {
                "version": SIGNED_TESTNET_READ_ONLY_VENUE_PROBE_SESSION_VERSION,
                "session_id": session_id,
                "dry_run_session_sha256": recorder.get("dry_run_session_sha256"),
                "probe_evidence_sha256": probe_evidence.get("read_only_venue_probe_evidence_sha256"),
                "close_report_sha256": close_report.get("read_only_probe_close_report_sha256"),
                "blockers": sorted(set(blockers)),
            },
        ),
        "version": SIGNED_TESTNET_READ_ONLY_VENUE_PROBE_SESSION_VERSION,
        "signed_testnet_dry_run_session_recorder_id": recorder.get("signed_testnet_dry_run_session_recorder_id"),
        "dry_run_session_sha256": recorder.get("dry_run_session_sha256"),
        "testnet_execution_session_id": session_id,
        "operator_probe_acknowledgement_validation": operator_ack_validation,
        "read_only_venue_probe_evidence": probe_evidence,
        "probe_event_log": event_log,
        "probe_event_log_sha256": sha256_json(event_log),
        "read_only_probe_close_report": close_report,
        "probe_evidence_age_sec": probe_age,
        "probe_evidence_max_age_sec": max_probe_age_sec,
        "probe_session_review_ready": session_review_ready,
        "ready_for_signed_testnet_execution": SIGNED_TESTNET_EXECUTION_ALLOWED_BY_STEP278,
        "testnet_order_submission_allowed": TESTNET_ORDER_SUBMISSION_ALLOWED_BY_STEP278,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_STEP278,
        "place_order_enabled": PLACE_ORDER_ENABLED_BY_STEP278,
        "cancel_order_enabled": CANCEL_ORDER_ENABLED_BY_STEP278,
        "signed_order_executor_enabled": SIGNED_ORDER_EXECUTOR_ENABLED_BY_STEP278,
        "adapter_place_order_called": ADAPTER_PLACE_ORDER_CALLED_BY_STEP278,
        "adapter_cancel_order_called": ADAPTER_CANCEL_ORDER_CALLED_BY_STEP278,
        "order_submission_remains_disabled": True,
        "read_only_probe_only": True,
        "block_reasons": sorted(set(blockers)),
        "session_reason": session_reason,
        "created_at_utc": utc_now_canonical(),
    }
    session["read_only_venue_probe_session_sha256"] = sha256_json(_payload_without_hash(session))
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        session["probe_session_path"] = str(path)
        session["read_only_venue_probe_session_sha256"] = sha256_json(_payload_without_hash(session))
        path.write_text(json.dumps(session, indent=2, sort_keys=True), encoding="utf-8")
    return session


def validate_read_only_venue_probe_evidence(evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(evidence or {})
    blockers: list[str] = []
    if data.get("version") != SIGNED_TESTNET_READ_ONLY_VENUE_PROBE_SESSION_VERSION:
        blockers.append("STEP278_PROBE_EVIDENCE_VERSION_INVALID")
    if data.get("valid") is not True:
        blockers.append("STEP278_PROBE_EVIDENCE_NOT_VALID")
    for section in _REQUIRED_READ_PROBES:
        probe = data.get(section)
        if not isinstance(probe, Mapping):
            blockers.append(f"STEP278_{section.upper()}_MISSING")
            continue
        if probe.get("valid") is not True:
            blockers.append(f"STEP278_{section.upper()}_INVALID")
        if probe.get("probe_hash") != _hash_probe(probe):
            blockers.append(f"STEP278_{section.upper()}_HASH_INVALID")
    for section in ["place_order_block_probe", "cancel_order_block_probe"]:
        probe = data.get(section)
        if not isinstance(probe, Mapping):
            blockers.append(f"STEP278_{section.upper()}_MISSING")
            continue
        if probe.get("adapter_method_called") is not False:
            blockers.append(f"STEP278_{section.upper()}_ADAPTER_METHOD_CALLED")
        if probe.get("valid") is not True:
            blockers.append(f"STEP278_{section.upper()}_INVALID")
        if probe.get("probe_hash") != _hash_probe(probe):
            blockers.append(f"STEP278_{section.upper()}_HASH_INVALID")
    if data.get("external_order_submission_performed") is not False:
        blockers.append("STEP278_PROBE_EVIDENCE_EXTERNAL_SUBMISSION_PERFORMED")
    if data.get("adapter_place_order_called") is not False:
        blockers.append("STEP278_PROBE_EVIDENCE_ADAPTER_PLACE_ORDER_CALLED")
    if data.get("adapter_cancel_order_called") is not False:
        blockers.append("STEP278_PROBE_EVIDENCE_ADAPTER_CANCEL_ORDER_CALLED")
    if data.get("place_order_enabled") is not False:
        blockers.append("STEP278_PROBE_EVIDENCE_PLACE_ORDER_ENABLED")
    if data.get("cancel_order_enabled") is not False:
        blockers.append("STEP278_PROBE_EVIDENCE_CANCEL_ORDER_ENABLED")
    if data.get("created_at_utc") and not is_canonical_utc_timestamp(data.get("created_at_utc")):
        blockers.append("STEP278_PROBE_EVIDENCE_TIMESTAMP_NOT_CANONICAL_UTC")
    expected_hash = sha256_json({k: v for k, v in data.items() if k not in {"read_only_venue_probe_evidence_sha256", "created_at_utc"}})
    if data.get("read_only_venue_probe_evidence_sha256") != expected_hash:
        blockers.append("STEP278_PROBE_EVIDENCE_HASH_INVALID")
    for reason in data.get("blockers") or []:
        blockers.append(str(reason))
    payload = {
        "evidence_id": data.get("read_only_venue_probe_evidence_id"),
        "hash": data.get("read_only_venue_probe_evidence_sha256"),
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_READ_ONLY_VENUE_PROBE_SESSION_VERSION,
    }
    return {
        "read_only_venue_probe_evidence_validation_id": stable_id("step278_probe_evidence_validation", payload),
        "valid": not blockers,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }


def validate_signed_testnet_read_only_venue_probe_session(session: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(session or {})
    blockers: list[str] = []
    if data.get("version") != SIGNED_TESTNET_READ_ONLY_VENUE_PROBE_SESSION_VERSION:
        blockers.append("STEP278_READ_ONLY_PROBE_SESSION_VERSION_INVALID")
    for field in [
        "signed_testnet_read_only_venue_probe_session_id",
        "signed_testnet_dry_run_session_recorder_id",
        "dry_run_session_sha256",
        "testnet_execution_session_id",
        "read_only_venue_probe_session_sha256",
    ]:
        if not data.get(field):
            blockers.append(f"STEP278_{field.upper()}_MISSING")
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
        if data.get(field) is not False:
            blockers.append(f"STEP278_{field.upper()}_INVARIANT_FAILED")
    if data.get("order_submission_remains_disabled") is not True:
        blockers.append("STEP278_ORDER_SUBMISSION_DISABLED_INVARIANT_MISSING")
    if data.get("read_only_probe_only") is not True:
        blockers.append("STEP278_READ_ONLY_PROBE_ONLY_INVARIANT_MISSING")
    ack_validation = data.get("operator_probe_acknowledgement_validation") or {}
    if not isinstance(ack_validation, Mapping) or ack_validation.get("valid") is not True:
        blockers.append("STEP278_OPERATOR_PROBE_ACK_VALIDATION_INVALID")
        if isinstance(ack_validation, Mapping):
            blockers.extend(ack_validation.get("block_reasons", []))
    evidence_validation = validate_read_only_venue_probe_evidence(data.get("read_only_venue_probe_evidence"))
    if evidence_validation.get("valid") is not True:
        blockers.extend(evidence_validation.get("block_reasons", []))
    event_log = data.get("probe_event_log")
    if not isinstance(event_log, list) or len(event_log) < 10:
        blockers.append("STEP278_PROBE_EVENT_LOG_INCOMPLETE")
    else:
        expected_sequence = list(range(1, len(event_log) + 1))
        actual_sequence = [event.get("sequence") for event in event_log]
        if actual_sequence != expected_sequence:
            blockers.append("STEP278_PROBE_EVENT_LOG_SEQUENCE_INVALID")
        for event in event_log:
            if event.get("event_hash") != sha256_json(_event_without_hash(event)):
                blockers.append("STEP278_PROBE_EVENT_HASH_INVALID")
                break
        if data.get("probe_event_log_sha256") != sha256_json(event_log):
            blockers.append("STEP278_PROBE_EVENT_LOG_HASH_INVALID")
    close_report = data.get("read_only_probe_close_report") or {}
    if isinstance(close_report, Mapping):
        if close_report.get("external_order_submission_performed") is not False:
            blockers.append("STEP278_CLOSE_REPORT_EXTERNAL_SUBMISSION_PERFORMED")
        if close_report.get("adapter_place_order_called") is not False:
            blockers.append("STEP278_CLOSE_REPORT_ADAPTER_PLACE_ORDER_CALLED")
        if close_report.get("adapter_cancel_order_called") is not False:
            blockers.append("STEP278_CLOSE_REPORT_ADAPTER_CANCEL_ORDER_CALLED")
        expected_close_hash = sha256_json({k: v for k, v in dict(close_report).items() if k not in {"read_only_probe_close_report_sha256", "created_at_utc"}})
        if close_report.get("read_only_probe_close_report_sha256") != expected_close_hash:
            blockers.append("STEP278_CLOSE_REPORT_HASH_INVALID")
    else:
        blockers.append("STEP278_CLOSE_REPORT_MISSING")
    if data.get("created_at_utc") and not is_canonical_utc_timestamp(data.get("created_at_utc")):
        blockers.append("STEP278_SESSION_TIMESTAMP_NOT_CANONICAL_UTC")
    expected_hash = sha256_json(_payload_without_hash(data))
    if data.get("read_only_venue_probe_session_sha256") != expected_hash:
        blockers.append("STEP278_READ_ONLY_PROBE_SESSION_HASH_INVALID")
    for reason in data.get("block_reasons") or []:
        blockers.append(str(reason))
    payload = {
        "session_id": data.get("signed_testnet_read_only_venue_probe_session_id"),
        "testnet_execution_session_id": data.get("testnet_execution_session_id"),
        "hash": data.get("read_only_venue_probe_session_sha256"),
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_READ_ONLY_VENUE_PROBE_SESSION_VERSION,
    }
    return {
        "signed_testnet_read_only_venue_probe_session_validation_id": stable_id("step278_read_only_probe_session_validation", payload),
        "valid": not blockers,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }

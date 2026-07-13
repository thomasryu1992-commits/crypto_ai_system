from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.config import AppConfig
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from core.json_io import atomic_write_json

STEP308_ORDER_LIFECYCLE_TRACKER_VERSION = "step308_order_lifecycle_tracker_v1"
ORDER_LIFECYCLE_TRACKER_REGISTRY_NAME = "signed_testnet_order_lifecycle_registry"

STATE_INTENT_RECEIVED = "SIGNED_TESTNET_ORDER_INTENT_RECEIVED"
STATE_PRE_SUBMIT_VALIDATED = "SIGNED_TESTNET_PRE_SUBMIT_VALIDATED"
STATE_ENABLEMENT_CHECKED = "SIGNED_TESTNET_ENABLEMENT_CHECKED"
STATE_SUBMISSION_BLOCKED_DISABLED = "SIGNED_TESTNET_SUBMISSION_BLOCKED_DISABLED"
STATE_SUBMISSION_BLOCKED_POLICY = "SIGNED_TESTNET_SUBMISSION_BLOCKED_POLICY"
STATE_SUBMITTED = "SIGNED_TESTNET_SUBMITTED"
STATE_FETCHED_STATUS = "SIGNED_TESTNET_FETCHED_STATUS"
STATE_RECONCILIATION_REQUIRED = "SIGNED_TESTNET_RECONCILIATION_REQUIRED"


def build_lifecycle_event(
    *,
    execution_id: str | None,
    order_intent_id: str | None,
    state: str,
    status: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "version": STEP308_ORDER_LIFECYCLE_TRACKER_VERSION,
        "execution_id": execution_id,
        "order_intent_id": order_intent_id,
        "state": state,
        "status": status,
        "details": dict(details or {}),
        "created_at_utc": utc_now_canonical(),
    }
    event["signed_testnet_order_lifecycle_event_id"] = stable_id("step308_signed_testnet_order_lifecycle_event", event, 24)
    event["signed_testnet_order_lifecycle_event_sha256"] = sha256_json(event)
    return event


def build_order_lifecycle_record(
    *,
    execution_record: Mapping[str, Any],
    lifecycle_events: list[Mapping[str, Any]],
) -> dict[str, Any]:
    record = {
        "version": STEP308_ORDER_LIFECYCLE_TRACKER_VERSION,
        "execution_id": execution_record.get("execution_id"),
        "signed_testnet_execution_id": execution_record.get("signed_testnet_execution_id"),
        "order_intent_id": execution_record.get("order_intent_id"),
        "decision_id": execution_record.get("decision_id"),
        "risk_gate_id": execution_record.get("risk_gate_id"),
        "research_signal_id": execution_record.get("research_signal_id"),
        "profile_id": execution_record.get("profile_id"),
        "status": execution_record.get("status"),
        "state": execution_record.get("state"),
        "exchange_order_id": execution_record.get("exchange_order_id"),
        "submitted_to_exchange": execution_record.get("submitted_to_exchange") is True,
        "external_order_submission_performed": execution_record.get("external_order_submission_performed") is True,
        "actual_submission_performed": execution_record.get("actual_submission_performed") is True,
        "lifecycle_state_count": len(lifecycle_events),
        "lifecycle_states": [event.get("state") for event in lifecycle_events],
        "lifecycle_event_hashes": [event.get("signed_testnet_order_lifecycle_event_sha256") for event in lifecycle_events],
        "reconciliation_required": execution_record.get("reconciliation_required") is True,
        "created_at_utc": utc_now_canonical(),
    }
    record["signed_testnet_order_lifecycle_record_id"] = stable_id("step308_signed_testnet_order_lifecycle_record", record, 24)
    record["signed_testnet_order_lifecycle_record_sha256"] = sha256_json(record)
    return record


def persist_order_lifecycle_record(
    cfg: AppConfig,
    *,
    execution_record: Mapping[str, Any],
    lifecycle_events: list[Mapping[str, Any]],
) -> dict[str, Any]:
    latest_dir = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    latest_dir.mkdir(parents=True, exist_ok=True)
    record = build_order_lifecycle_record(execution_record=execution_record, lifecycle_events=lifecycle_events)
    persisted = append_registry_record(
        registry_path(cfg, ORDER_LIFECYCLE_TRACKER_REGISTRY_NAME),
        record,
        registry_name=ORDER_LIFECYCLE_TRACKER_REGISTRY_NAME,
        id_field="signed_testnet_order_lifecycle_record_id",
        hash_field="signed_testnet_order_lifecycle_record_sha256",
        id_prefix="step308_signed_testnet_order_lifecycle_record",
    )
    atomic_write_json(latest_dir / "signed_testnet_order_lifecycle_events.json", list(lifecycle_events))
    atomic_write_json(latest_dir / "signed_testnet_order_lifecycle_registry_record.json", persisted)
    return persisted

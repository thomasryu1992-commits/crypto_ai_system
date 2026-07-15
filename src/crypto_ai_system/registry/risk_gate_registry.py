"""Registry-backed PreOrderRiskGate records (directive P0-2).

The signed-testnet path previously accepted a bare ``pre_order_risk_gate_approved:
true`` boolean plus a free-form ``risk_gate_id`` string on the intent dict. No
persisted RiskGate evaluation had to exist, so a synthetic id would pass the
final guard. This module persists real :class:`PreOrderRiskGateResult` records
and verifies a *strategy* testnet order against the stored record: it must
exist, be approved, match the execution stage and profile, be unexpired, and be
tamper-free.

Connectivity-harness orders (``connectivity_test: true``) intentionally bypass
this — they validate auth/signing/submission/reconciliation only and must never
be aggregated as strategy performance. That split lives in the final guard.

This module never submits orders, reads secrets, or mutates runtime settings.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json
from core.time_utils import parse_time, utc_now
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import (
    append_registry_record,
    load_registry_records,
    registry_path,
)
from crypto_ai_system.utils.audit import sha256_json

RISK_GATE_REGISTRY_NAME = "risk_gate_registry"

# A risk-gate approval is a hot-path artifact: it reflects account/exposure/venue
# state at evaluation time and must not authorise an order minutes later.
DEFAULT_RISK_GATE_TTL_SECONDS = 300

# Stages that a signed-testnet strategy order may have been gated under.
_SIGNED_TESTNET_STAGES = {"signed_testnet", "testnet"}

REASON_RECORD_MISSING = "RISK_GATE_RECORD_MISSING"
REASON_NOT_APPROVED = "RISK_GATE_NOT_APPROVED"
REASON_STAGE_MISMATCH = "RISK_GATE_STAGE_MISMATCH"
REASON_PROFILE_MISMATCH = "RISK_GATE_PROFILE_MISMATCH"
REASON_EXPIRED = "RISK_GATE_EXPIRED"
REASON_INTEGRITY = "RISK_GATE_INTEGRITY_MISMATCH"
REASON_INTENT_HASH_MISMATCH = "RISK_GATE_ORDER_INTENT_HASH_MISMATCH"

_HASH_FIELD = "risk_gate_registry_record_sha256"
_ID_FIELD = "risk_gate_registry_record_id"


def _latest_path(cfg: AppConfig, name: str) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    base = Path(raw)
    if not base.is_absolute():
        base = cfg.root / base
    base.mkdir(parents=True, exist_ok=True)
    return base / name


def _expires_at(ttl_seconds: int) -> str:
    return (utc_now() + timedelta(seconds=int(ttl_seconds))).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def persist_risk_gate_record(
    result: Mapping[str, Any],
    *,
    cfg: AppConfig | None = None,
    order_intent_hash: str | None = None,
    ttl_seconds: int = DEFAULT_RISK_GATE_TTL_SECONDS,
) -> dict[str, Any]:
    """Persist a ``PreOrderRiskGateResult.to_dict()`` payload to the registry.

    Adds an ``expires_at_utc`` (TTL from now) and, when supplied, binds the
    record to a specific ``order_intent_hash`` so it can only authorise that
    intent. Returns the persisted record (with registry id + integrity hash).
    """
    cfg = cfg or load_config(".")
    payload = dict(result)
    payload.setdefault("expires_at_utc", _expires_at(ttl_seconds))
    if order_intent_hash is not None:
        payload["order_intent_hash"] = order_intent_hash
    persisted = append_registry_record(
        registry_path(cfg, RISK_GATE_REGISTRY_NAME),
        payload,
        registry_name=RISK_GATE_REGISTRY_NAME,
        id_field=_ID_FIELD,
        hash_field=_HASH_FIELD,
        id_prefix="risk_gate_registry",
    )
    atomic_write_json(_latest_path(cfg, "risk_gate_record.json"), persisted)
    return persisted


def get_risk_gate_record(risk_gate_id: str | None, *, cfg: AppConfig | None = None) -> dict[str, Any] | None:
    """Return the most recent persisted record for ``risk_gate_id`` or None."""
    if not risk_gate_id:
        return None
    cfg = cfg or load_config(".")
    records = load_registry_records(registry_path(cfg, RISK_GATE_REGISTRY_NAME))
    matches = [r for r in records if r.get("risk_gate_id") == risk_gate_id]
    return matches[-1] if matches else None


def verify_strategy_risk_gate(
    record: Mapping[str, Any] | None,
    intent: Mapping[str, Any],
    *,
    execution_stage: str,
    now: Any = None,
) -> dict[str, Any]:
    """Verify a persisted RiskGate record authorises this strategy intent.

    Pure: no IO. Returns ``{"approved": bool, "reasons": [...], "risk_gate_id": ...}``.
    Fails closed — a missing record, or any single failed check, denies approval.
    """
    if not record:
        return {"approved": False, "reasons": [REASON_RECORD_MISSING], "risk_gate_id": intent.get("risk_gate_id")}

    reasons: list[str] = []

    if record.get("approved") is not True:
        reasons.append(REASON_NOT_APPROVED)

    rec_stage = str(record.get("stage") or "").strip().lower()
    want = str(execution_stage or "").strip().lower()
    if want in _SIGNED_TESTNET_STAGES:
        if rec_stage not in _SIGNED_TESTNET_STAGES:
            reasons.append(REASON_STAGE_MISMATCH)
    elif rec_stage != want:
        reasons.append(REASON_STAGE_MISMATCH)

    rec_profile = str(record.get("profile_id") or "").strip()
    intent_profile = str(intent.get("profile_id") or "").strip()
    # A strategy intent must name the profile its gate was evaluated for.
    if rec_profile != intent_profile:
        reasons.append(REASON_PROFILE_MISMATCH)

    expires = parse_time(record.get("expires_at_utc"))
    now_dt = now or utc_now()
    if expires is None or now_dt > expires:
        reasons.append(REASON_EXPIRED)

    stored_hash = record.get(_HASH_FIELD)
    recomputed = sha256_json({k: v for k, v in record.items() if k != _HASH_FIELD})
    if not stored_hash or stored_hash != recomputed:
        reasons.append(REASON_INTEGRITY)

    bound_hash = record.get("order_intent_hash")
    if bound_hash:
        intent_hash = intent.get("order_intent_hash") or intent.get("order_intent_record_sha256")
        if intent_hash != bound_hash:
            reasons.append(REASON_INTENT_HASH_MISMATCH)

    return {"approved": not reasons, "reasons": reasons, "risk_gate_id": record.get("risk_gate_id")}

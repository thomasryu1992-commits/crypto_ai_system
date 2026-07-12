from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.execution.exchange_adapter_contract import DisabledExchangeAdapter, validate_adapter_capabilities
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

VENUE_CAPABILITY_EVIDENCE_VERSION = "step274_venue_capability_evidence_v1"

_REQUIRED_EVIDENCE_SECTIONS = [
    "balance_read_evidence",
    "positions_read_evidence",
    "open_orders_read_evidence",
    "orderbook_read_evidence",
    "fee_estimate_evidence",
    "slippage_estimate_evidence",
    "min_order_size_evidence",
]


def _evidence_payload_without_hash(evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in evidence.items() if k not in {"venue_capability_evidence_hash", "created_at_utc", "evidence_path"}}


def build_venue_capability_evidence(
    *,
    adapter: DisabledExchangeAdapter,
    order_intent: Mapping[str, Any],
    symbol: str = "BTCUSDT",
    evidence_path: str | Path | None = None,
) -> dict[str, Any]:
    capabilities = adapter.get_capabilities()
    adapter_validation = validate_adapter_capabilities(capabilities)
    balance = adapter.get_balance()
    positions = adapter.get_positions()
    open_orders = adapter.get_open_orders()
    orderbook = adapter.get_orderbook(symbol)
    fee = adapter.estimate_fee(order_intent)
    slippage = adapter.estimate_slippage(order_intent)
    min_order = adapter.validate_min_order_size(order_intent)
    blocked_submission_probe = adapter.place_order({
        "order_intent_id": order_intent.get("order_intent_id"),
        "symbol": symbol,
        "probe_only": True,
    })

    blockers: list[str] = []
    blockers.extend(adapter_validation.get("block_reasons", []))
    if min_order.get("min_order_size_valid") is not True:
        blockers.append("VENUE_MIN_ORDER_SIZE_INVALID")
    if blocked_submission_probe.get("submitted") is not False:
        blockers.append("VENUE_PLACE_ORDER_PROBE_SUBMITTED_BLOCKED")
    if blocked_submission_probe.get("external_order_submission_performed") is not False:
        blockers.append("VENUE_EXTERNAL_ORDER_SUBMISSION_PERFORMED_BLOCKED")
    if blocked_submission_probe.get("order_submission_enabled_by_contract") is not False:
        blockers.append("VENUE_ORDER_SUBMISSION_CONTRACT_ENABLED_BLOCKED")

    payload = {
        "version": VENUE_CAPABILITY_EVIDENCE_VERSION,
        "adapter_contract_validation_id": adapter_validation.get("adapter_contract_validation_id"),
        "order_intent_id": order_intent.get("order_intent_id"),
        "symbol": symbol,
        "balance_read_evidence": balance,
        "positions_read_evidence": positions,
        "open_orders_read_evidence": open_orders,
        "orderbook_read_evidence": orderbook,
        "fee_estimate_evidence": fee,
        "slippage_estimate_evidence": slippage,
        "min_order_size_evidence": min_order,
        "blocked_submission_probe": blocked_submission_probe,
        "blockers": sorted(set(blockers)),
    }
    evidence_id = stable_id("venue_capability_evidence", payload)
    evidence = {
        "venue_capability_evidence_id": evidence_id,
        **payload,
        "valid": not blockers,
        "external_order_submission_performed": False,
        "order_submission_enabled_by_contract": False,
        "place_order_probe_submitted": False,
        "created_at_utc": utc_now_canonical(),
    }
    evidence["venue_capability_evidence_hash"] = sha256_json(_evidence_payload_without_hash(evidence))
    if evidence_path is not None:
        path = Path(evidence_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(__import__("json").dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
        evidence["evidence_path"] = str(path)
    return evidence


def validate_venue_capability_evidence(evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(evidence or {})
    blockers: list[str] = []
    if data.get("version") != VENUE_CAPABILITY_EVIDENCE_VERSION:
        blockers.append("VENUE_CAPABILITY_EVIDENCE_VERSION_INVALID")
    if data.get("valid") is not True:
        blockers.append("VENUE_CAPABILITY_EVIDENCE_NOT_VALID")
    for section in _REQUIRED_EVIDENCE_SECTIONS:
        if not isinstance(data.get(section), Mapping):
            blockers.append(f"{section.upper()}_MISSING")
    if data.get("external_order_submission_performed") is not False:
        blockers.append("VENUE_EVIDENCE_EXTERNAL_ORDER_SUBMISSION_PERFORMED")
    if data.get("order_submission_enabled_by_contract") is not False:
        blockers.append("VENUE_EVIDENCE_ORDER_SUBMISSION_ENABLED")
    if data.get("place_order_probe_submitted") is not False:
        blockers.append("VENUE_EVIDENCE_PLACE_ORDER_PROBE_SUBMITTED")
    blocked_probe = data.get("blocked_submission_probe") or {}
    if blocked_probe.get("submitted") is not False:
        blockers.append("VENUE_EVIDENCE_BLOCKED_SUBMISSION_PROBE_NOT_BLOCKED")
    if (data.get("min_order_size_evidence") or {}).get("min_order_size_valid") is not True:
        blockers.append("VENUE_EVIDENCE_MIN_ORDER_SIZE_INVALID")
    expected_hash = sha256_json(_evidence_payload_without_hash(data))
    if data.get("venue_capability_evidence_hash") != expected_hash:
        blockers.append("VENUE_CAPABILITY_EVIDENCE_HASH_INVALID")
    for reason in data.get("blockers") or []:
        blockers.append(str(reason))
    payload = {
        "evidence_id": data.get("venue_capability_evidence_id"),
        "hash": data.get("venue_capability_evidence_hash"),
        "blockers": sorted(set(blockers)),
        "version": VENUE_CAPABILITY_EVIDENCE_VERSION,
    }
    return {
        "venue_capability_evidence_validation_id": stable_id("venue_capability_evidence_validation", payload),
        "valid": not blockers,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }

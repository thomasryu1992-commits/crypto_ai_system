from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.execution.exchange_adapter_contract import EXCHANGE_ADAPTER_CONTRACT_VERSION
from crypto_ai_system.execution.signed_testnet_readiness import evaluate_signed_testnet_preflight
from crypto_ai_system.execution.testnet_secret_intake import (
    TESTNET_KEY_METADATA_INTAKE_VERSION,
    validate_testnet_key_metadata_intake,
)
from crypto_ai_system.execution.venue_capability_evidence import (
    VENUE_CAPABILITY_EVIDENCE_VERSION,
    validate_venue_capability_evidence,
)
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

SIGNED_TESTNET_PREFLIGHT_ARTIFACT_VERSION = "step274_signed_testnet_preflight_artifact_v1"
SIGNED_TESTNET_EXECUTION_ALLOWED_BY_STEP274 = False
TESTNET_ORDER_SUBMISSION_ALLOWED_BY_STEP274 = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_STEP274 = False


def _artifact_payload_without_hash(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in artifact.items() if k not in {"preflight_artifact_sha256", "created_at_utc", "preflight_artifact_path"}}


def _venue_state_from_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "balance_read_contract_available": isinstance(evidence.get("balance_read_evidence"), Mapping),
        "position_read_contract_available": isinstance(evidence.get("positions_read_evidence"), Mapping),
        "open_orders_read_contract_available": isinstance(evidence.get("open_orders_read_evidence"), Mapping),
        "orderbook_read_contract_available": isinstance(evidence.get("orderbook_read_evidence"), Mapping),
        "fee_model_available": isinstance(evidence.get("fee_estimate_evidence"), Mapping),
        "slippage_estimate_available": isinstance(evidence.get("slippage_estimate_evidence"), Mapping),
        "min_order_size_valid": (evidence.get("min_order_size_evidence") or {}).get("min_order_size_valid") is True,
        "venue_capability_evidence_id": evidence.get("venue_capability_evidence_id"),
        "venue_capability_evidence_hash": evidence.get("venue_capability_evidence_hash"),
    }


def build_signed_testnet_preflight_artifact(
    *,
    adapter_capabilities: Mapping[str, Any],
    testnet_key_intake: Mapping[str, Any],
    venue_capability_evidence: Mapping[str, Any],
    manual_approval: Mapping[str, Any],
    risk_limits: Mapping[str, Any],
    runtime_flags: Mapping[str, Any],
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    key_validation = validate_testnet_key_metadata_intake(testnet_key_intake)
    venue_validation = validate_venue_capability_evidence(venue_capability_evidence)
    secret_status = {
        "has_api_key": True,
        "has_api_secret": True,
        "key_scope": testnet_key_intake.get("key_scope"),
        "base_url": testnet_key_intake.get("base_url"),
        "secret_file_loaded": False,
        "secret_file_created": False,
        "secret_bytes_read": False,
        "live_key_detected": False,
    }
    preflight = evaluate_signed_testnet_preflight(
        adapter_capabilities=adapter_capabilities,
        secret_status=secret_status,
        manual_approval=manual_approval,
        venue_state=_venue_state_from_evidence(venue_capability_evidence),
        risk_limits=risk_limits,
        runtime_flags=runtime_flags,
    )
    blockers: list[str] = []
    blockers.extend(key_validation.get("block_reasons", []))
    blockers.extend(venue_validation.get("block_reasons", []))
    blockers.extend(preflight.get("block_reasons", []))
    if preflight.get("external_order_submission_performed") is not False:
        blockers.append("PREFLIGHT_EXTERNAL_ORDER_SUBMISSION_PERFORMED_BLOCKED")
    if preflight.get("testnet_order_submission_allowed") is not False:
        blockers.append("PREFLIGHT_TESTNET_ORDER_SUBMISSION_ALLOWED_BLOCKED")
    if preflight.get("ready_for_signed_testnet_execution") is not False:
        blockers.append("PREFLIGHT_SIGNED_TESTNET_EXECUTION_READY_MUST_REMAIN_FALSE_STEP274")

    payload = {
        "version": SIGNED_TESTNET_PREFLIGHT_ARTIFACT_VERSION,
        "adapter_contract_version": EXCHANGE_ADAPTER_CONTRACT_VERSION,
        "testnet_key_intake_id": testnet_key_intake.get("testnet_key_intake_id"),
        "testnet_key_intake_sha256": sha256_json(testnet_key_intake),
        "venue_capability_evidence_id": venue_capability_evidence.get("venue_capability_evidence_id"),
        "venue_capability_evidence_hash": venue_capability_evidence.get("venue_capability_evidence_hash"),
        "approval_sha256": preflight.get("approval_validation", {}).get("approval_sha256"),
        "signed_testnet_preflight_id": preflight.get("signed_testnet_preflight_id"),
        "blockers": sorted(set(blockers)),
    }
    artifact = {
        "signed_testnet_preflight_artifact_id": stable_id("signed_testnet_preflight_artifact", payload),
        **payload,
        "testnet_key_metadata_intake_version": TESTNET_KEY_METADATA_INTAKE_VERSION,
        "venue_capability_evidence_version": VENUE_CAPABILITY_EVIDENCE_VERSION,
        "contract_review_ready": preflight.get("contract_review_ready") is True and not key_validation.get("block_reasons") and not venue_validation.get("block_reasons"),
        "ready_for_signed_testnet_execution": SIGNED_TESTNET_EXECUTION_ALLOWED_BY_STEP274,
        "testnet_order_submission_allowed": TESTNET_ORDER_SUBMISSION_ALLOWED_BY_STEP274,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_STEP274,
        "key_intake_validation": key_validation,
        "venue_evidence_validation": venue_validation,
        "signed_testnet_preflight": preflight,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }
    artifact["preflight_artifact_sha256"] = sha256_json(_artifact_payload_without_hash(artifact))
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        artifact["preflight_artifact_path"] = str(path)
        artifact["preflight_artifact_sha256"] = sha256_json(_artifact_payload_without_hash(artifact))
        path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    return artifact


def validate_signed_testnet_preflight_artifact(artifact: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(artifact or {})
    blockers: list[str] = []
    if data.get("version") != SIGNED_TESTNET_PREFLIGHT_ARTIFACT_VERSION:
        blockers.append("SIGNED_TESTNET_PREFLIGHT_ARTIFACT_VERSION_INVALID")
    if data.get("ready_for_signed_testnet_execution") is not False:
        blockers.append("SIGNED_TESTNET_PREFLIGHT_ARTIFACT_EXECUTION_READY_NOT_FALSE")
    if data.get("testnet_order_submission_allowed") is not False:
        blockers.append("SIGNED_TESTNET_PREFLIGHT_ARTIFACT_ORDER_ALLOWED_NOT_FALSE")
    if data.get("external_order_submission_performed") is not False:
        blockers.append("SIGNED_TESTNET_PREFLIGHT_ARTIFACT_EXTERNAL_SUBMISSION_PERFORMED")
    if not data.get("testnet_key_intake_id"):
        blockers.append("SIGNED_TESTNET_PREFLIGHT_ARTIFACT_KEY_INTAKE_ID_MISSING")
    if not data.get("venue_capability_evidence_id"):
        blockers.append("SIGNED_TESTNET_PREFLIGHT_ARTIFACT_VENUE_EVIDENCE_ID_MISSING")
    if not data.get("approval_sha256"):
        blockers.append("SIGNED_TESTNET_PREFLIGHT_ARTIFACT_APPROVAL_HASH_MISSING")
    if data.get("preflight_artifact_sha256") != sha256_json(_artifact_payload_without_hash(data)):
        blockers.append("SIGNED_TESTNET_PREFLIGHT_ARTIFACT_HASH_INVALID")
    for reason in data.get("block_reasons") or []:
        blockers.append(str(reason))
    payload = {
        "artifact_id": data.get("signed_testnet_preflight_artifact_id"),
        "artifact_hash": data.get("preflight_artifact_sha256"),
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_PREFLIGHT_ARTIFACT_VERSION,
    }
    return {
        "signed_testnet_preflight_artifact_validation_id": stable_id("signed_testnet_preflight_artifact_validation", payload),
        "valid": not blockers,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }

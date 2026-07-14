from __future__ import annotations

from datetime import datetime, timezone

from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.exchange_adapter_contract import (
    DisabledExchangeAdapter,
)
from crypto_ai_system.execution.testnet_secret_metadata_intake_v2 import (
    validate_testnet_secret_metadata_intake_v2,
)
from crypto_ai_system.governance.common import (
    DEFAULT_UNSAFE_APPROVAL_FIELDS,
    forbidden_secret_fields,
    artifact_summary,
    persist_report,
    read_latest_json,
    review_only_permission_state,
    unsafe_flags_by_artifact,
)
from crypto_ai_system.utils.audit import (
    sha256_json,
    stable_id,
    utc_now_canonical,
)

PHASE8_M1_VERSION = (
    "phase8_m1_signed_testnet_execution_preparation_v1"
)

STATE_WAITING_FOR_PHASE7_OPERATOR_DECISION = (
    "WAITING_FOR_PHASE7_OPERATOR_DECISION"
)

STATE_PREPARATION_DESIGN_RECORDED_REVIEW_ONLY = (
    "PHASE8_PREPARATION_DESIGN_RECORDED_REVIEW_ONLY"
)

STATE_PREPARATION_EVIDENCE_REPAIR_REQUIRED = (
    "PHASE8_PREPARATION_EVIDENCE_REPAIR_REQUIRED"
)

STATE_BLOCKED = "BLOCKED"

STATUS_WAITING_REVIEW_ONLY = (
    "PHASE8_M1_WAITING_FOR_PHASE7_OPERATOR_DECISION_REVIEW_ONLY"
)

STATUS_RECORDED_REVIEW_ONLY = (
    "PHASE8_M1_EXECUTION_PREPARATION_DESIGN_RECORDED_REVIEW_ONLY"
)

STATUS_REPAIR_REQUIRED_REVIEW_ONLY = (
    "PHASE8_M1_EXECUTION_PREPARATION_EVIDENCE_REPAIR_REQUIRED_REVIEW_ONLY"
)

STATUS_BLOCKED_REVIEW_ONLY = (
    "PHASE8_M1_EXECUTION_PREPARATION_BLOCKED_REVIEW_ONLY"
)

APPROVED_PHASE7_STATE = (
    "OPERATOR_APPROVED_PHASE8_PREPARATION_REVIEW_ONLY"
)

WAITING_PHASE7_STATE = (
    "WAITING_FOR_OPERATOR_DECISION"
)

PHASE8_M1_ARTIFACT_FILES: dict[str, str] = {
    "secret_metadata_intake": (
        "testnet_secret_metadata_intake_v2.json"
    ),
    "read_only_venue_probe": (
        "real_read_only_venue_probe.json"
    ),
    "pre_submit_validation": (
        "signed_testnet_pre_submit_validation_report.json"
    ),
    "enablement_packet": (
        "signed_testnet_execution_enablement_packet.json"
    ),
    "disabled_executor_evidence": (
        "signed_testnet_order_execution_record.json"
    ),
    "final_order_intent": (
        "phase8_final_order_intent_review_only.json"
    ),
    "hot_path_risk_gate_evidence": (
        "phase8_hot_path_risk_gate_evidence_review_only.json"
    ),
    "executor_final_guard_evidence": (
        "phase8_executor_final_guard_evidence_review_only.json"
    ),
}

SECRET_VALUE_FIELD_NAMES: tuple[str, ...] = (
    "api_key",
    "api_secret",
    "api_key_value",
    "api_secret_value",
    "private_key",
    "secret",
    "secret_value",
    "passphrase",
    "password",
    "seed_phrase",
    "mnemonic",
)

HOT_PATH_REQUIRED_CHECKS: tuple[str, ...] = (
    "approved_profile_present",
    "approved_profile_hash_matches",
    "data_freshness_valid",
    "optional_data_health_valid",
    "fallback_synthetic_mock_sample_absent",
    "position_limits_valid",
    "daily_loss_limit_valid",
    "max_consecutive_loss_valid",
    "spread_limit_valid",
    "slippage_limit_valid",
    "api_error_rate_valid",
    "reconciliation_mismatch_absent",
    "kill_switch_inactive",
    "hard_caps_valid",
    "min_max_notional_valid",
    "fee_slippage_evidence_present",
    "venue_readiness_valid",
    "canonical_id_chain_complete",
)

FINAL_GUARD_REQUIRED_EVIDENCE: tuple[str, ...] = (
    "phase7_final_pre_executor_review_approved",
    "metadata_only_key_reference_valid",
    "testnet_key_scope_valid",
    "mainnet_live_key_scope_absent",
    "write_path_dry_validation_passed",
    "real_order_endpoint_not_called_during_dry_validation",
    "fresh_pre_submit_validation_passed",
    "fresh_hot_path_pre_order_risk_gate_passed",
    "kill_switch_rechecked_and_inactive",
    "hard_caps_rechecked",
    "idempotency_key_valid",
    "monitoring_and_alerting_ready",
    "clock_sync_valid",
    "reconciliation_plan_ready",
    "rollback_plan_ready",
)




PHASE8_M2_VERSION = (
    "phase8_m2_lean_in_place_validation_v1"
)

PHASE8_M2_APPROVED_METADATA_VENUES: tuple[str, ...] = (
    "extended_testnet",
)

PHASE8_M2_ALLOWED_SCOPES: tuple[str, ...] = (
    "read_only",
    "market_data_read",
    "account_read",
    "balance_read",
    "position_read",
    "positions_read",
    "open_orders_read",
    "signed_testnet_preparation",
    "testnet_trade",
    "testnet_order_write",
)

PHASE8_M2_BLOCKED_SCOPE_TOKENS: tuple[str, ...] = (
    "live",
    "mainnet",
    "prod",
    "withdraw",
    "transfer",
    "admin",
    "unrestricted",
    "margin_mutation",
    "leverage_mutation",
)


def _phase8_m2_scope_values(value: Any) -> list[str]:
    if value is None:
        return []

    values = (
        value.replace(";", ",").split(",")
        if isinstance(value, str)
        else list(value)
        if isinstance(value, (list, tuple, set))
        else [value]
    )

    return [
        str(item).strip().lower().replace("-", "_").replace(" ", "_")
        for item in values
        if str(item).strip()
    ]


def validate_metadata_only_key_scope(
    metadata_intake: Mapping[str, Any] | None,
    *,
    approved_venues: tuple[str, ...] = PHASE8_M2_APPROVED_METADATA_VENUES,
    known_live_key_fingerprints_sha256: tuple[str, ...] = (),
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Validate existing metadata intake without reading any secret value."""

    created = created_at_utc or utc_now_canonical()
    intake = dict(metadata_intake or {})
    base = validate_testnet_secret_metadata_intake_v2(intake)
    blockers: list[str] = []

    if base.get("valid") is not True:
        blockers.append("PHASE8_M2_BASE_METADATA_INTAKE_INVALID")
        blockers.extend(
            f"BASE:{reason}"
            for reason in (base.get("block_reasons") or [])
        )

    if intake.get("metadata_only") is not True:
        blockers.append("PHASE8_M2_METADATA_ONLY_REQUIRED")

    environment = str(intake.get("environment") or "").strip().lower()
    if environment not in {"testnet", "signed_testnet"}:
        blockers.append("PHASE8_M2_ENVIRONMENT_NOT_TESTNET")

    venue = str(intake.get("venue") or "").strip().lower()
    approved = {str(item).strip().lower() for item in approved_venues}
    if venue not in approved:
        blockers.append("PHASE8_M2_PRIMARY_TESTNET_VENUE_NOT_APPROVED")

    fingerprint = str(
        intake.get("key_fingerprint_sha256")
        or intake.get("api_key_fingerprint_sha256")
        or ""
    ).strip().lower()
    if len(fingerprint) != 64 or any(
        character not in "0123456789abcdef"
        for character in fingerprint
    ):
        blockers.append("PHASE8_M2_KEY_FINGERPRINT_INVALID")

    live_fingerprints = {
        str(item).strip().lower()
        for item in known_live_key_fingerprints_sha256
        if str(item).strip()
    }
    if fingerprint and fingerprint in live_fingerprints:
        blockers.append("PHASE8_M2_LIVE_KEY_FINGERPRINT_MATCH_BLOCKED")

    scope = _phase8_m2_scope_values(intake.get("scope"))
    if not scope:
        blockers.append("PHASE8_M2_KEY_SCOPE_MISSING")

    unknown_scope = sorted(
        item
        for item in scope
        if item not in PHASE8_M2_ALLOWED_SCOPES
    )
    if unknown_scope:
        blockers.append(
            "PHASE8_M2_UNKNOWN_KEY_SCOPE:"
            + ",".join(unknown_scope)
        )

    high_risk_scope = sorted(
        item
        for item in scope
        if any(
            token in item
            for token in PHASE8_M2_BLOCKED_SCOPE_TOKENS
        )
    )
    if high_risk_scope:
        blockers.append(
            "PHASE8_M2_HIGH_RISK_KEY_SCOPE_BLOCKED:"
            + ",".join(high_risk_scope)
        )

    for field in (
        "api_key_value_access_allowed",
        "api_secret_value_access_allowed",
        "secret_file_access_allowed",
        "secret_file_creation_allowed",
        "secret_value_read",
        "secret_file_created",
        "testnet_order_submission_allowed",
        "external_order_submission_allowed",
        "external_order_submission_performed",
        "place_order_enabled",
        "cancel_order_enabled",
        "signed_order_executor_enabled",
        "ready_for_signed_testnet_execution",
    ):
        if intake.get(field) is not False:
            blockers.append(
                "PHASE8_M2_METADATA_UNSAFE_FLAG:" + field
            )

    blockers = sorted(set(blockers))
    valid = not blockers

    report: dict[str, Any] = {
        "metadata_only_key_scope_validation_id": stable_id(
            "phase8_m2_metadata_key_scope",
            {
                "source_id": intake.get(
                    "testnet_secret_metadata_intake_id"
                ),
                "source_hash": intake.get(
                    "testnet_secret_metadata_intake_sha256"
                ),
                "venue": venue,
                "environment": environment,
                "scope": scope,
                "blockers": blockers,
                "created_at_utc": created,
            },
            24,
        ),
        "version": PHASE8_M2_VERSION,
        "status": (
            "PHASE8_M2_METADATA_KEY_SCOPE_VALIDATED_REVIEW_ONLY"
            if valid
            else "PHASE8_M2_METADATA_KEY_SCOPE_BLOCKED_REVIEW_ONLY"
        ),
        "valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "review_only": True,
        "metadata_only": True,
        "source_testnet_secret_metadata_intake_id": intake.get(
            "testnet_secret_metadata_intake_id"
        ),
        "source_testnet_secret_metadata_intake_sha256": intake.get(
            "testnet_secret_metadata_intake_sha256"
        ),
        "environment": environment or None,
        "venue": venue or None,
        "scope": scope,
        "approved_metadata_venues": sorted(approved),
        "unknown_scope": unknown_scope,
        "high_risk_scope": high_risk_scope,
        "metadata_only_key_scope_runtime_validated": valid,
        "declared_testnet_trade_scope_does_not_grant_permission": True,
        "secret_value_access_performed": False,
        "secret_file_read": False,
        "secret_file_created": False,
        "request_signing_performed": False,
        "exchange_endpoint_called": False,
        "blockers": blockers,
        **review_only_permission_state(),
        "request_signing_allowed": False,
        "adapter_write_routing_enabled": False,
        "created_at_utc": created,
    }
    report["metadata_only_key_scope_validation_sha256"] = sha256_json(report)
    return report


def validate_write_path_dry(
    *,
    adapter_capabilities: Mapping[str, Any] | None,
    request_preview: Mapping[str, Any] | None,
    routing_policy: Mapping[str, Any] | None,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Validate request shape and routing metadata without calling adapter writes."""

    created = created_at_utc or utc_now_canonical()
    capabilities = dict(adapter_capabilities or {})
    request = dict(request_preview or {})
    routing = dict(routing_policy or {})
    blockers: list[str] = []

    if capabilities.get("supports_place_order") is not False:
        blockers.append("PHASE8_M2_PLACE_ORDER_CAPABILITY_MUST_REMAIN_DISABLED")
    if capabilities.get("supports_cancel_order") is not False:
        blockers.append("PHASE8_M2_CANCEL_ORDER_CAPABILITY_MUST_REMAIN_DISABLED")
    if capabilities.get("testnet_only") is not True:
        blockers.append("PHASE8_M2_ADAPTER_TESTNET_ONLY_REQUIRED")

    required_request_fields = (
        "order_intent_id",
        "symbol",
        "side",
        "order_type",
        "client_order_id",
        "idempotency_key",
    )
    missing = sorted(
        field
        for field in required_request_fields
        if not str(request.get(field) or "").strip()
    )
    if missing:
        blockers.append(
            "PHASE8_M2_DRY_REQUEST_FIELD_MISSING:"
            + ",".join(missing)
        )

    environment = str(routing.get("environment") or "").strip().lower()
    if environment not in {"testnet", "signed_testnet"}:
        blockers.append("PHASE8_M2_DRY_ROUTE_NOT_TESTNET")

    base_url = str(routing.get("base_url") or "").strip().lower()
    if not base_url or not any(
        token in base_url
        for token in ("testnet", "sandbox", ".invalid")
    ):
        blockers.append("PHASE8_M2_DRY_ROUTE_NOT_TESTNET_CLASSIFIED")
    if any(
        token in base_url
        for token in (
            "mainnet",
            "api.binance.com",
            "fapi.binance.com",
            "production",
        )
    ):
        blockers.append("PHASE8_M2_MAINNET_HOST_BLOCKED")

    for field in (
        "network_transport_enabled",
        "request_signing_enabled",
        "write_endpoint_invocation_enabled",
        "fallback_venue_allowed",
    ):
        if routing.get(field) is not False:
            blockers.append("PHASE8_M2_DRY_ROUTE_UNSAFE_FLAG:" + field)

    timeout = routing.get("timeout_seconds")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not 0 < float(timeout) <= 10
    ):
        blockers.append("PHASE8_M2_TIMEOUT_POLICY_INVALID")

    if routing.get("max_retry_attempts") != 1:
        blockers.append("PHASE8_M2_RETRY_POLICY_MUST_BE_SINGLE_ATTEMPT")
    if routing.get("retry_requires_same_idempotency_key") is not True:
        blockers.append("PHASE8_M2_IDEMPOTENT_RETRY_POLICY_MISSING")

    forbidden_fragments = (
        "api_key_value",
        "api_secret_value",
        "private_key",
        "secret_value",
        "passphrase",
        "password",
        "seed_phrase",
        "mnemonic",
    )
    exposed_fields = sorted(
        str(key)
        for payload in (request, routing)
        for key, value in payload.items()
        if value not in (None, "", False)
        and any(fragment in str(key).lower() for fragment in forbidden_fragments)
    )
    if exposed_fields:
        blockers.append(
            "PHASE8_M2_DRY_SECRET_FIELD_EXPOSURE:"
            + ",".join(exposed_fields)
        )

    blockers = sorted(set(blockers))
    valid = not blockers
    report: dict[str, Any] = {
        "write_path_dry_validation_id": stable_id(
            "phase8_m2_write_path_dry",
            {
                "capabilities_hash": sha256_json(capabilities),
                "request_shape_hash": sha256_json(
                    sorted(str(key) for key in request)
                ),
                "routing_hash": sha256_json(routing),
                "blockers": blockers,
                "created_at_utc": created,
            },
            24,
        ),
        "version": PHASE8_M2_VERSION,
        "status": (
            "PHASE8_M2_WRITE_PATH_DRY_VALIDATED_REVIEW_ONLY"
            if valid
            else "PHASE8_M2_WRITE_PATH_DRY_BLOCKED_REVIEW_ONLY"
        ),
        "valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "review_only": True,
        "dry_validation_only": True,
        "adapter_capabilities": capabilities,
        "request_shape": sorted(str(key) for key in request),
        "request_preview_sha256": sha256_json(request),
        "routing_policy_sha256": sha256_json(routing),
        "write_path_dry_validation_runtime_validated": valid,
        "write_path_validated_against_real_order_endpoint": False,
        "place_order_method_called": False,
        "cancel_order_method_called": False,
        "network_transport_invocation_count": 0,
        "request_signing_invocation_count": 0,
        "exchange_endpoint_call_count": 0,
        "actual_http_request_created": False,
        "actual_exchange_response_received": False,
        "exchange_order_id_received": False,
        "real_exchange_fill_received": False,
        "position_mutation_performed": False,
        "balance_mutation_performed": False,
        "real_order_endpoint_not_called_during_dry_validation": True,
        "blockers": blockers,
        **review_only_permission_state(),
        "request_signing_allowed": False,
        "adapter_write_routing_enabled": False,
        "exchange_endpoint_called": False,
        "created_at_utc": created,
    }
    report["write_path_dry_validation_sha256"] = sha256_json(report)
    return report

PHASE8_M3_VERSION = "phase8_m3_hot_path_pre_order_risk_gate_in_place_v1"
PHASE8_M3_MAX_EVIDENCE_AGE_SECONDS = 30
PHASE8_M3_REQUIRED_ID_CHAIN: tuple[str, ...] = (
    "data_snapshot_id",
    "feature_snapshot_id",
    "research_signal_id",
    "profile_id",
    "approval_packet_id",
    "approval_intake_id",
    "decision_id",
    "risk_gate_id",
    "order_intent_id",
)


def _phase8_m3_parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _phase8_m3_hash_without(payload: Mapping[str, Any], field: str) -> str:
    body = dict(payload)
    body.pop(field, None)
    return sha256_json(body)


def validate_hot_path_pre_order_risk_gate(
    *,
    final_order_intent: Mapping[str, Any] | None,
    fresh_risk_evidence: Mapping[str, Any] | None,
    phase8_m2_validation_complete: bool,
    created_at_utc: str | None = None,
    max_evidence_age_seconds: int = PHASE8_M3_MAX_EVIDENCE_AGE_SECONDS,
) -> dict[str, Any]:
    """Validate fresh pre-execution risk evidence without granting permission."""

    created = created_at_utc or utc_now_canonical()
    intent = dict(final_order_intent or {})
    evidence = dict(fresh_risk_evidence or {})
    blockers: list[str] = []

    if phase8_m2_validation_complete is not True:
        blockers.append("PHASE8_M3_M2_VALIDATION_NOT_COMPLETE")
    if not intent:
        blockers.append("PHASE8_M3_FINAL_ORDER_INTENT_MISSING")
    if not evidence:
        blockers.append("PHASE8_M3_FRESH_RISK_EVIDENCE_MISSING")

    if intent.get("payload_frozen") is not True:
        blockers.append("PHASE8_M3_FINAL_ORDER_PAYLOAD_NOT_FROZEN")
    if str(intent.get("stage") or "").strip().lower() != "signed_testnet":
        blockers.append("PHASE8_M3_ORDER_INTENT_STAGE_NOT_SIGNED_TESTNET")
    if str(evidence.get("stage") or "").strip().lower() != "signed_testnet":
        blockers.append("PHASE8_M3_RISK_EVIDENCE_STAGE_NOT_SIGNED_TESTNET")
    if str(evidence.get("status") or "").strip().upper() != "PASS_SIGNED_TESTNET":
        blockers.append("PHASE8_M3_RISK_GATE_STATUS_NOT_PASS_SIGNED_TESTNET")
    if evidence.get("approved") is not True:
        blockers.append("PHASE8_M3_RISK_GATE_NOT_APPROVED")
    if evidence.get("evaluation_mode") != "hot_path_immediate_pre_execution":
        blockers.append("PHASE8_M3_EVALUATION_MODE_NOT_HOT_PATH")

    intent_hash = str(intent.get("final_order_intent_sha256") or "")
    computed_hash = (
        _phase8_m3_hash_without(intent, "final_order_intent_sha256")
        if intent
        else ""
    )
    if not intent_hash or intent_hash != computed_hash:
        blockers.append("PHASE8_M3_FINAL_ORDER_INTENT_HASH_INVALID")
    if str(evidence.get("final_order_intent_sha256") or "") != intent_hash:
        blockers.append("PHASE8_M3_RISK_EVIDENCE_ORDER_INTENT_HASH_MISMATCH")
    if str(evidence.get("order_intent_id") or "") != str(intent.get("order_intent_id") or ""):
        blockers.append("PHASE8_M3_ORDER_INTENT_ID_MISMATCH")

    id_chain: dict[str, Any] = {}
    for field in PHASE8_M3_REQUIRED_ID_CHAIN:
        value = evidence.get(field) if field == "risk_gate_id" else intent.get(field)
        id_chain[field] = value
        if not str(value or "").strip():
            blockers.append(f"PHASE8_M3_REQUIRED_ID_MISSING:{field}")
        evidence_value = evidence.get(field)
        if field != "risk_gate_id" and evidence_value is not None and str(evidence_value) != str(value):
            blockers.append(f"PHASE8_M3_ID_CHAIN_VALUE_MISMATCH:{field}")

    checks = dict(evidence.get("checks") or {})
    failed_checks = sorted(
        name for name in HOT_PATH_REQUIRED_CHECKS
        if checks.get(name) is not True
    )
    if failed_checks:
        blockers.append("PHASE8_M3_REQUIRED_CHECK_FAILED:" + ",".join(failed_checks))

    optional_health = str(evidence.get("optional_data_health") or "").strip().lower()
    if optional_health in {
        "neutral_due_to_missing",
        "missing",
        "stale",
        "invalid",
        "unavailable",
        "legacy_fallback",
    }:
        blockers.append("PHASE8_M3_OPTIONAL_DATA_HEALTH_NOT_EXECUTION_ELIGIBLE")

    for field in (
        "fallback_used",
        "synthetic_data_used",
        "mock_data_used",
        "sample_data_used",
        "stale_data_used",
        "hidden_missing_data_used",
        "missing_source_neutral_used",
    ):
        if evidence.get(field) is True:
            blockers.append(f"PHASE8_M3_FORBIDDEN_DATA_MODE:{field}")

    if evidence.get("kill_switch_active") is not False:
        blockers.append("PHASE8_M3_KILL_SWITCH_NOT_CONFIRMED_INACTIVE")

    now = _phase8_m3_parse_utc(created)
    evaluated_at = _phase8_m3_parse_utc(evidence.get("evaluated_at_utc"))
    evidence_age_seconds: float | None = None
    if now is None or evaluated_at is None:
        blockers.append("PHASE8_M3_EVIDENCE_TIMESTAMP_INVALID")
    else:
        evidence_age_seconds = (now - evaluated_at).total_seconds()
        if evidence_age_seconds < -1:
            blockers.append("PHASE8_M3_EVIDENCE_TIMESTAMP_IN_FUTURE")
        if evidence_age_seconds > float(max_evidence_age_seconds):
            blockers.append("PHASE8_M3_EVIDENCE_STALE")

    unsafe = unsafe_flags_by_artifact({
        "final_order_intent": intent,
        "fresh_risk_evidence": evidence,
    })
    if unsafe:
        blockers.append("PHASE8_M3_UNSAFE_EXECUTION_PERMISSION_FIELD")

    secret_findings = {
        "final_order_intent": forbidden_secret_fields(intent),
        "fresh_risk_evidence": forbidden_secret_fields(evidence),
    }
    secret_findings = {name: fields for name, fields in secret_findings.items() if fields}
    if secret_findings:
        blockers.append("PHASE8_M3_SECRET_VALUE_FIELD_EXPOSURE")

    blockers = sorted(set(blockers))
    valid = not blockers

    report: dict[str, Any] = {
        "hot_path_pre_order_risk_gate_validation_id": stable_id(
            "phase8_m3_hot_path_pre_order_risk_gate",
            {
                "order_intent_id": intent.get("order_intent_id"),
                "risk_gate_id": evidence.get("risk_gate_id"),
                "intent_hash": intent_hash,
                "created_at_utc": created,
                "blockers": blockers,
            },
            24,
        ),
        "version": PHASE8_M3_VERSION,
        "status": (
            "PHASE8_M3_HOT_PATH_PRE_ORDER_RISK_GATE_VALIDATED_REVIEW_ONLY"
            if valid
            else "PHASE8_M3_HOT_PATH_PRE_ORDER_RISK_GATE_BLOCKED_REVIEW_ONLY"
        ),
        "valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "review_only": True,
        "validation_only": True,
        "must_run_immediately_before_executor": True,
        "must_run_after_final_order_payload_is_frozen": True,
        "must_run_before_any_request_signing": True,
        "cold_path_risk_result_reused": False,
        "phase8_m2_validation_complete": phase8_m2_validation_complete is True,
        "final_order_intent_id": intent.get("order_intent_id"),
        "final_order_intent_sha256": intent_hash or None,
        "risk_gate_id": evidence.get("risk_gate_id"),
        "id_chain": id_chain,
        "id_chain_complete": not any(
            blocker.startswith("PHASE8_M3_REQUIRED_ID_MISSING:")
            for blocker in blockers
        ),
        "required_checks": list(HOT_PATH_REQUIRED_CHECKS),
        "failed_checks": failed_checks,
        "optional_data_health": optional_health or None,
        "freshness_budget_seconds": int(max_evidence_age_seconds),
        "evidence_age_seconds": evidence_age_seconds,
        "hot_path_risk_gate_runtime_implemented": True,
        "hot_path_risk_gate_runtime_validated": valid,
        "secret_value_access_performed": False,
        "secret_file_read": False,
        "secret_file_created": False,
        "request_signing_performed": False,
        "network_write_transport_opened": False,
        "exchange_endpoint_called": False,
        "external_order_submission_performed": False,
        "unsafe_flags_by_artifact": unsafe,
        "secret_field_findings": secret_findings,
        "blockers": blockers,
        **review_only_permission_state(),
        "phase8_execution_allowed": False,
        "phase8_write_path_allowed": False,
        "phase8_secret_value_handling_allowed": False,
        "phase8_executor_enablement_allowed": False,
        "phase8_order_submission_allowed": False,
        "request_signing_allowed": False,
        "adapter_write_routing_enabled": False,
        "created_at_utc": created,
    }
    report["hot_path_pre_order_risk_gate_validation_sha256"] = sha256_json(report)
    return report

PHASE8_M4_VERSION = "phase8_m4_executor_final_guard_in_place_v1"
PHASE8_M4_MAX_EVIDENCE_AGE_SECONDS = 30
PHASE8_M4_REQUIRED_OPERATIONAL_CHECKS: tuple[str, ...] = (
    "monitoring_ready",
    "kill_switch_inactive",
    "clock_sync_valid",
    "rollback_ready",
    "reconciliation_ready",
    "venue_session_ready",
    "executor_disabled",
    "request_signing_disabled",
    "network_write_transport_disabled",
    "exchange_order_endpoint_not_called",
)


def validate_executor_final_guard(
    *,
    phase8_m2_validation_complete: bool,
    hot_path_validation: Mapping[str, Any] | None,
    operational_evidence: Mapping[str, Any] | None,
    created_at_utc: str | None = None,
    max_evidence_age_seconds: int = PHASE8_M4_MAX_EVIDENCE_AGE_SECONDS,
) -> dict[str, Any]:
    """Aggregate existing M2/M3 evidence and fail closed without permission."""

    created = created_at_utc or utc_now_canonical()
    hot_path = dict(hot_path_validation or {})
    operations = dict(operational_evidence or {})
    blockers: list[str] = []

    if phase8_m2_validation_complete is not True:
        blockers.append("PHASE8_M4_M2_VALIDATION_NOT_COMPLETE")
    if hot_path.get("valid") is not True:
        blockers.append("PHASE8_M4_M3_HOT_PATH_VALIDATION_NOT_PASSED")
    if hot_path.get("hot_path_risk_gate_runtime_validated") is not True:
        blockers.append("PHASE8_M4_M3_RUNTIME_EVIDENCE_NOT_VALIDATED")
    if not operations:
        blockers.append("PHASE8_M4_OPERATIONAL_EVIDENCE_MISSING")
    if str(operations.get("stage") or "").strip().lower() != "signed_testnet":
        blockers.append("PHASE8_M4_OPERATIONAL_STAGE_NOT_SIGNED_TESTNET")
    if str(operations.get("status") or "").strip().upper() != "PASS_REVIEW_ONLY":
        blockers.append("PHASE8_M4_OPERATIONAL_EVIDENCE_STATUS_INVALID")
    if operations.get("evidence_complete") is not True:
        blockers.append("PHASE8_M4_OPERATIONAL_EVIDENCE_INCOMPLETE")

    hot_path_hash = str(
        hot_path.get("hot_path_pre_order_risk_gate_validation_sha256") or ""
    )
    computed_hot_path_hash = (
        _phase8_m3_hash_without(
            hot_path,
            "hot_path_pre_order_risk_gate_validation_sha256",
        )
        if hot_path
        else ""
    )
    if not hot_path_hash or hot_path_hash != computed_hot_path_hash:
        blockers.append("PHASE8_M4_M3_VALIDATION_HASH_INVALID")
    if str(operations.get("hot_path_validation_sha256") or "") != hot_path_hash:
        blockers.append("PHASE8_M4_OPERATIONAL_TO_M3_HASH_MISMATCH")
    if str(operations.get("final_order_intent_sha256") or "") != str(
        hot_path.get("final_order_intent_sha256") or ""
    ):
        blockers.append("PHASE8_M4_FINAL_ORDER_INTENT_HASH_MISMATCH")
    if str(operations.get("risk_gate_id") or "") != str(
        hot_path.get("risk_gate_id") or ""
    ):
        blockers.append("PHASE8_M4_RISK_GATE_ID_MISMATCH")

    checks = dict(operations.get("checks") or {})
    failed_checks = sorted(
        name
        for name in PHASE8_M4_REQUIRED_OPERATIONAL_CHECKS
        if checks.get(name) is not True
    )
    if failed_checks:
        blockers.append(
            "PHASE8_M4_REQUIRED_OPERATIONAL_CHECK_FAILED:"
            + ",".join(failed_checks)
        )

    now = _phase8_m3_parse_utc(created)
    evaluated_at = _phase8_m3_parse_utc(operations.get("evaluated_at_utc"))
    evidence_age_seconds: float | None = None
    if now is None or evaluated_at is None:
        blockers.append("PHASE8_M4_OPERATIONAL_TIMESTAMP_INVALID")
    else:
        evidence_age_seconds = (now - evaluated_at).total_seconds()
        if evidence_age_seconds < -1:
            blockers.append("PHASE8_M4_OPERATIONAL_TIMESTAMP_IN_FUTURE")
        if evidence_age_seconds > float(max_evidence_age_seconds):
            blockers.append("PHASE8_M4_OPERATIONAL_EVIDENCE_STALE")

    if hot_path.get("request_signing_performed") is not False:
        blockers.append("PHASE8_M4_M3_REQUEST_SIGNING_STATE_INVALID")
    if hot_path.get("exchange_endpoint_called") is not False:
        blockers.append("PHASE8_M4_M3_EXCHANGE_ENDPOINT_STATE_INVALID")
    if hot_path.get("external_order_submission_performed") is not False:
        blockers.append("PHASE8_M4_M3_ORDER_SUBMISSION_STATE_INVALID")

    for field in (
        "request_signing_performed",
        "network_write_transport_opened",
        "exchange_endpoint_called",
        "external_order_submission_performed",
        "position_mutation_performed",
        "balance_mutation_performed",
    ):
        if operations.get(field) is not False:
            blockers.append("PHASE8_M4_OPERATIONAL_UNSAFE_STATE:" + field)
    if operations.get("exchange_endpoint_call_count") != 0:
        blockers.append(
            "PHASE8_M4_OPERATIONAL_EXCHANGE_ENDPOINT_CALL_COUNT_NOT_ZERO"
        )

    unsafe = unsafe_flags_by_artifact(
        {
            "hot_path_validation": hot_path,
            "operational_evidence": operations,
        }
    )
    if unsafe:
        blockers.append("PHASE8_M4_UNSAFE_EXECUTION_PERMISSION_FIELD")

    secret_findings = {
        "hot_path_validation": forbidden_secret_fields(hot_path),
        "operational_evidence": forbidden_secret_fields(operations),
    }
    secret_findings = {
        name: fields for name, fields in secret_findings.items() if fields
    }
    if secret_findings:
        blockers.append("PHASE8_M4_SECRET_VALUE_FIELD_EXPOSURE")

    blockers = sorted(set(blockers))
    valid = not blockers

    report: dict[str, Any] = {
        "executor_final_guard_validation_id": stable_id(
            "phase8_m4_executor_final_guard",
            {
                "hot_path_validation_sha256": hot_path_hash,
                "final_order_intent_sha256": hot_path.get(
                    "final_order_intent_sha256"
                ),
                "risk_gate_id": hot_path.get("risk_gate_id"),
                "created_at_utc": created,
                "blockers": blockers,
            },
            24,
        ),
        "version": PHASE8_M4_VERSION,
        "status": (
            "PHASE8_M4_EXECUTOR_FINAL_GUARD_VALIDATED_REVIEW_ONLY"
            if valid
            else "PHASE8_M4_EXECUTOR_FINAL_GUARD_BLOCKED_REVIEW_ONLY"
        ),
        "valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "review_only": True,
        "validation_only": True,
        "aggregates_existing_m2_m3_results": True,
        "duplicates_m2_m3_checks": False,
        "must_run_after_hot_path_risk_gate": True,
        "must_run_before_any_request_signing": True,
        "must_run_before_any_executor_enablement": True,
        "phase8_m2_validation_complete": phase8_m2_validation_complete is True,
        "phase8_m3_validation_complete": hot_path.get("valid") is True,
        "hot_path_validation_sha256": hot_path_hash or None,
        "final_order_intent_sha256": hot_path.get("final_order_intent_sha256"),
        "risk_gate_id": hot_path.get("risk_gate_id"),
        "required_operational_checks": list(PHASE8_M4_REQUIRED_OPERATIONAL_CHECKS),
        "failed_operational_checks": failed_checks,
        "freshness_budget_seconds": int(max_evidence_age_seconds),
        "operational_evidence_age_seconds": evidence_age_seconds,
        "executor_final_guard_runtime_implemented": True,
        "executor_final_guard_runtime_validated": valid,
        "phase8_m4_validation_complete": valid,
        "phase8_completion_review_allowed": valid,
        "phase9_separate_approval_required": True,
        "phase9_order_submission_permission_granted": False,
        "secret_value_access_performed": False,
        "secret_file_read": False,
        "secret_file_created": False,
        "request_signing_performed": False,
        "network_write_transport_opened": False,
        "exchange_endpoint_called": False,
        "external_order_submission_performed": False,
        "unsafe_flags_by_artifact": unsafe,
        "secret_field_findings": secret_findings,
        "blockers": blockers,
        **review_only_permission_state(),
        "phase8_execution_allowed": False,
        "phase8_write_path_allowed": False,
        "phase8_secret_value_handling_allowed": False,
        "phase8_executor_enablement_allowed": False,
        "phase8_order_submission_allowed": False,
        "request_signing_allowed": False,
        "adapter_write_routing_enabled": False,
        "created_at_utc": created,
    }
    report["executor_final_guard_validation_sha256"] = sha256_json(report)
    return report


def _build_phase8_review_only_artifact(
    *,
    id_field: str,
    id_prefix: str,
    type_field: str,
    type_value: str,
    hash_field: str,
    body: Mapping[str, Any],
    created_at_utc: str | None,
) -> dict[str, Any]:
    """Build one hashed Phase 8 review-only artifact without repeated boilerplate."""
    created = created_at_utc or utc_now_canonical()
    artifact: dict[str, Any] = {
        id_field: stable_id(
            id_prefix,
            {
                "version": PHASE8_M1_VERSION,
                "created_at_utc": created,
            },
            24,
        ),
        type_field: type_value,
        "version": PHASE8_M1_VERSION,
        "review_only": True,
        **dict(body),
        "created_at_utc": created,
    }
    artifact[hash_field] = sha256_json(artifact)
    return artifact


def build_secret_handling_design(
    *,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    return _build_phase8_review_only_artifact(
        id_field="secret_handling_design_id",
        id_prefix="phase8_m1_secret_handling_design",
        type_field="design_type",
        type_value="signed_testnet_secret_handling_metadata_only_design",
        hash_field="secret_handling_design_sha256",
        created_at_utc=created_at_utc,
        body={
            "design_only": True,
            "metadata_only_required": True,
            "allowed_reference_schemes": [
                "secret_ref:",
                "vault_ref:",
                "kms_ref:",
                "metadata_ref:",
            ],
            "required_metadata_fields": [
                "secret_reference_id",
                "key_fingerprint_sha256",
                "environment",
                "venue",
                "scope",
                "operator_id",
                "created_at_utc",
            ],
            "forbidden_secret_value_fields": list(
                SECRET_VALUE_FIELD_NAMES
            ),
            "allowed_environments": [
                "testnet",
                "signed_testnet",
            ],
            "live_mainnet_environment_allowed": False,
            "withdrawal_scope_allowed": False,
            "transfer_scope_allowed": False,
            "admin_scope_allowed": False,
            "leverage_mutation_scope_allowed": False,
            "margin_mutation_scope_allowed": False,
            "secret_dereference_allowed": False,
            "secret_value_read_allowed": False,
            "secret_file_read_allowed": False,
            "secret_file_creation_allowed": False,
            "request_signing_allowed": False,
            "executor_enablement_allowed": False,
            "testnet_order_submission_allowed": False,
        },
    )


def build_write_path_dry_validation_contract(
    *,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    return _build_phase8_review_only_artifact(
        id_field="write_path_dry_validation_contract_id",
        id_prefix="phase8_m1_write_path_dry_validation",
        type_field="contract_type",
        type_value="exchange_write_path_dry_validation_no_endpoint_call",
        hash_field="write_path_dry_validation_contract_sha256",
        created_at_utc=created_at_utc,
        body={
            "dry_validation_only": True,
            "network_transport_enabled": False,
            "request_signing_enabled": False,
            "exchange_write_endpoint_invocation_enabled": False,
            "actual_http_request_created": False,
            "actual_exchange_response_expected": False,
            "adapter_write_routing_enabled": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "required_dry_checks": [
                "adapter_method_boundary_exists",
                "testnet_environment_explicit",
                "testnet_host_allowlist_configured",
                "mainnet_host_denylist_configured",
                "payload_schema_valid",
                "idempotency_key_present",
                "client_order_id_present",
                "timeout_policy_defined",
                "retry_policy_is_bounded",
                "retry_does_not_duplicate_submission",
                "response_schema_contract_defined",
                "error_taxonomy_defined",
                "no_silent_fallback_to_live_or_other_venue",
                "no_secret_value_in_logs_or_artifacts",
            ],
            "allowed_dry_outputs": [
                "sanitized_request_shape",
                "endpoint_classification",
                "payload_schema_validation",
                "idempotency_validation",
                "routing_decision_preview",
                "blocked_endpoint_evidence",
            ],
            "forbidden_dry_outputs": [
                "signed_http_request",
                "authorization_header",
                "api_key_value",
                "api_secret_value",
                "private_key",
                "exchange_order_id",
                "real_exchange_fill",
            ],
            "write_path_validated_against_real_order_endpoint": False,
            "external_order_submission_allowed": False,
            "external_order_submission_performed": False,
            "exchange_endpoint_called": False,
            "testnet_order_submission_allowed": False,
        },
    )


def build_hot_path_risk_gate_contract(
    *,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    return _build_phase8_review_only_artifact(
        id_field="hot_path_risk_gate_contract_id",
        id_prefix="phase8_m1_hot_path_risk_gate_contract",
        type_field="contract_type",
        type_value="pre_order_risk_gate_immediate_pre_execution_contract",
        hash_field="hot_path_risk_gate_contract_sha256",
        created_at_utc=created_at_utc,
        body={
            "design_only": False,
            "must_run_immediately_before_executor": True,
            "must_run_after_final_order_payload_is_frozen": True,
            "must_run_before_any_request_signing": True,
            "freshness_budget_must_be_configured": True,
            "runtime_freshness_budget_validated": False,
            "required_stage": "signed_testnet",
            "required_status": "PASS_SIGNED_TESTNET",
            "required_approved_value": True,
            "required_checks": list(HOT_PATH_REQUIRED_CHECKS),
            "required_id_chain": list(PHASE8_M3_REQUIRED_ID_CHAIN),
            "risk_gate_result_may_be_reused_from_cold_path": False,
            "stale_risk_gate_result_allowed": False,
            "missing_optional_data_may_be_hidden": False,
            "fallback_or_synthetic_candidate_allowed": False,
            "hot_path_risk_gate_runtime_implemented": True,
            "hot_path_risk_gate_runtime_validated": False,
            "executor_enablement_allowed": False,
            "testnet_order_submission_allowed": False,
        },
    )


def build_executor_final_guard_design(
    *,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    return _build_phase8_review_only_artifact(
        id_field="executor_final_guard_design_id",
        id_prefix="phase8_m1_executor_final_guard_design",
        type_field="design_type",
        type_value="signed_testnet_executor_final_guard_design_disabled",
        hash_field="executor_final_guard_design_sha256",
        created_at_utc=created_at_utc,
        body={
            "design_only": False,
            "required_evidence": list(FINAL_GUARD_REQUIRED_EVIDENCE),
            "all_evidence_must_be_current": True,
            "all_hashes_must_match": True,
            "all_stage_values_must_be_signed_testnet": True,
            "kill_switch_must_fail_closed": True,
            "missing_evidence_must_fail_closed": True,
            "unknown_state_must_fail_closed": True,
            "live_or_mainnet_scope_must_fail_closed": True,
            "fallback_synthetic_mock_sample_must_fail_closed": True,
            "secret_value_exposure_must_fail_closed": True,
            "write_endpoint_call_during_dry_validation_must_fail_closed": True,
            "executor_final_guard_runtime_implemented": True,
            "executor_final_guard_runtime_validated": False,
            "executor_final_guard_passed_for_execution": False,
            "ready_for_signed_testnet_execution": False,
            "signed_order_executor_enabled": False,
            "testnet_order_submission_allowed": False,
            "external_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
        },
    )



def build_signed_testnet_execution_preparation_report(
    *,
    pre_executor_review: Mapping[
        str,
        Any,
    ] | None,
    existing_artifacts: Mapping[
        str,
        Mapping[
            str,
            Any,
        ],
    ] | None = None,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created = (
        created_at_utc
        or utc_now_canonical()
    )

    source = dict(
        pre_executor_review
        or {}
    )

    artifacts = {
        str(name): dict(payload)
        for (
            name,
            payload,
        ) in (
            existing_artifacts
            or {}
        ).items()
    }

    unsafe_by_artifact = (
        unsafe_flags_by_artifact(
            artifacts
        )
    )

    source_state = str(
        source.get(
            "pre_executor_review_state"
        )
        or ""
    )

    source_waiting = (
        source_state
        == WAITING_PHASE7_STATE
        or source.get(
            "waiting_for_operator_decision"
        )
        is True
    )

    source_approved = (
        source_state
        == APPROVED_PHASE7_STATE
        and source.get(
            "final_pre_executor_review_ready"
        )
        is True
        and source.get(
            "phase8_preparation_design_review_allowed"
        )
        is True
        and source.get(
            "operator_decision_is_runtime_authority"
        )
        is False
        and source.get(
            "operator_decision_can_transition_stage"
        )
        is False
        and source.get(
            "operator_decision_can_enable_executor"
        )
        is False
        and source.get(
            "operator_decision_can_submit_order"
        )
        is False
        and source.get(
            "blocked"
        )
        is False
    )

    blockers: list[str] = []

    if not source:
        blockers.append(
            "PHASE7_PRE_EXECUTOR_REVIEW_MISSING"
        )

    if (
        source
        and not source_waiting
        and not source_approved
    ):
        blockers.append(
            "PHASE7_PRE_EXECUTOR_REVIEW_NOT_APPROVED_FOR_PHASE8_PREPARATION"
        )

    if unsafe_by_artifact:
        blockers.append(
            "UNSAFE_EXISTING_EXECUTION_PREPARATION_ARTIFACT"
        )

    source_unsafe_fields = tuple(
        field
        for field in DEFAULT_UNSAFE_APPROVAL_FIELDS
        if field
        != "actual_operator_decision_recorded"
    )

    source_unsafe = (
        unsafe_flags_by_artifact(
            {
                "pre_executor_review": source,
            },
            fields=source_unsafe_fields,
        )
        if source
        else {}
    )

    if source_unsafe:
        blockers.append(
            "UNSAFE_PHASE7_PRE_EXECUTOR_REVIEW_SOURCE"
        )

    if source_waiting and not (
        source_unsafe
    ):
        state = (
            STATE_WAITING_FOR_PHASE7_OPERATOR_DECISION
        )

        status = (
            STATUS_WAITING_REVIEW_ONLY
        )

        blocked = False

        fail_closed = False

        next_action = (
            "complete_phase7_manual_operator_decision_intake_"
            "without_enabling_execution"
        )

    elif source_approved and not blockers:
        state = (
            STATE_PREPARATION_DESIGN_RECORDED_REVIEW_ONLY
        )

        status = (
            STATUS_RECORDED_REVIEW_ONLY
        )

        blocked = False

        fail_closed = False

        next_action = (
            "evaluate_phase8_m2_and_m3_validation_evidence_"
            "keep_executor_disabled"
        )

    elif blockers and not (
        source_unsafe
        or unsafe_by_artifact
    ):
        state = (
            STATE_PREPARATION_EVIDENCE_REPAIR_REQUIRED
        )

        status = (
            STATUS_REPAIR_REQUIRED_REVIEW_ONLY
        )

        blocked = True

        fail_closed = True

        next_action = (
            "repair_phase7_or_existing_preparation_evidence_"
            "before_phase8_review"
        )

    else:
        state = (
            STATE_BLOCKED
        )

        status = (
            STATUS_BLOCKED_REVIEW_ONLY
        )

        blocked = True

        fail_closed = True

        next_action = (
            "resolve_unsafe_phase8_preparation_source_evidence"
        )

    secret_design = (
        build_secret_handling_design(
            created_at_utc=created
        )
    )

    write_path_contract = (
        build_write_path_dry_validation_contract(
            created_at_utc=created
        )
    )

    metadata_scope_validation = validate_metadata_only_key_scope(
        artifacts.get("secret_metadata_intake"),
        created_at_utc=created,
    )

    dry_adapter = DisabledExchangeAdapter(
        venue="extended_testnet",
        environment="signed_testnet",
    )

    write_path_dry_validation = validate_write_path_dry(
        adapter_capabilities=dry_adapter.get_capabilities(),
        request_preview={
            "order_intent_id": "phase8_m2_dry_order_intent_review_only",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "client_order_id": "phase8m2-dry-client-001",
            "idempotency_key": "phase8m2-dry-idem-001",
        },
        routing_policy={
            "environment": "signed_testnet",
            "base_url": "https://testnet.review-only.invalid",
            "network_transport_enabled": False,
            "request_signing_enabled": False,
            "write_endpoint_invocation_enabled": False,
            "fallback_venue_allowed": False,
            "timeout_seconds": 5,
            "max_retry_attempts": 1,
            "retry_requires_same_idempotency_key": True,
        },
        created_at_utc=created,
    )

    phase8_m2_validation_complete = (
        metadata_scope_validation.get("valid") is True
        and write_path_dry_validation.get("valid") is True
    )

    hot_path_pre_order_risk_gate_validation = (
        validate_hot_path_pre_order_risk_gate(
            final_order_intent=(
                artifacts.get("final_order_intent")
            ),
            fresh_risk_evidence=(
                artifacts.get("hot_path_risk_gate_evidence")
            ),
            phase8_m2_validation_complete=(
                phase8_m2_validation_complete
            ),
            created_at_utc=created,
        )
    )

    phase8_m3_validation_complete = (
        phase8_m2_validation_complete
        and hot_path_pre_order_risk_gate_validation.get("valid") is True
    )

    executor_final_guard_validation = (
        validate_executor_final_guard(
            phase8_m2_validation_complete=(
                phase8_m2_validation_complete
            ),
            hot_path_validation=(
                hot_path_pre_order_risk_gate_validation
            ),
            operational_evidence=(
                artifacts.get("executor_final_guard_evidence")
            ),
            created_at_utc=created,
        )
    )

    phase8_m4_validation_complete = (
        phase8_m3_validation_complete
        and executor_final_guard_validation.get("valid") is True
    )

    if source_approved and not blockers:
        if not phase8_m2_validation_complete:
            next_action = (
                "repair_phase8_m2_metadata_or_dry_validation_"
                "evidence_keep_executor_disabled"
            )
        elif not phase8_m3_validation_complete:
            next_action = (
                "collect_or_repair_fresh_hot_path_pre_order_risk_gate_"
                "evidence_keep_executor_disabled"
            )
        elif not phase8_m4_validation_complete:
            next_action = (
                "collect_or_repair_executor_final_guard_operational_"
                "evidence_keep_executor_disabled"
            )
        else:
            next_action = (
                "prepare_separate_phase9_single_order_approval_"
                "review_packet_keep_executor_disabled"
            )

    hot_path_contract = (
        build_hot_path_risk_gate_contract(
            created_at_utc=created
        )
    )

    final_guard_design = (
        build_executor_final_guard_design(
            created_at_utc=created
        )
    )

    report: dict[str, Any] = {
        "signed_testnet_execution_preparation_id": (
            stable_id(
                "phase8_m1_signed_testnet_execution_preparation",
                {
                    "source_id": source.get(
                        "pre_executor_review_id"
                    ),
                    "source_state": source_state,
                    "state": state,
                    "created_at_utc": created,
                },
                24,
            )
        ),
        "version": PHASE8_M1_VERSION,
        "status": status,
        "phase8_execution_preparation_state": state,
        "review_only": True,
        "preparation_only": True,
        "design_only": True,
        "blocked": blocked,
        "fail_closed": fail_closed,
        "phase8_m1_design_complete": True,
        "phase8_preparation_design_review_allowed": (
            source_approved
            and not blockers
        ),
        "phase8_execution_preparation_ready": False,
        "source_pre_executor_review_id": (
            source.get(
                "pre_executor_review_id"
            )
        ),
        "source_pre_executor_review_state": (
            source_state
            or None
        ),
        "source_operator_decision_recorded": (
            source.get(
                "actual_operator_decision_recorded"
            )
            is True
        ),
        "source_operator_decision_is_runtime_authority": False,
        "source_artifact_summaries": {
            name: artifact_summary(
                name,
                payload,
            )
            for (
                name,
                payload,
            ) in artifacts.items()
        },
        "unsafe_flags_by_artifact": (
            unsafe_by_artifact
        ),
        "source_unsafe_flags": (
            source_unsafe
        ),
        "blockers": sorted(
            set(
                blockers
            )
        ),
        "secret_handling_design": (
            secret_design
        ),
        "write_path_dry_validation_contract": (
            write_path_contract
        ),
        "hot_path_risk_gate_contract": (
            hot_path_contract
        ),
        "executor_final_guard_design": (
            final_guard_design
        ),
        "metadata_only_key_reference_design_complete": True,
        "phase8_m2_validators_implemented_in_place": True,
        "phase8_m2_new_runtime_module_created": False,
        "metadata_only_key_scope_validation": metadata_scope_validation,
        "metadata_only_key_scope_runtime_validated": (
            metadata_scope_validation.get(
                "metadata_only_key_scope_runtime_validated"
            )
            is True
        ),
        "write_path_dry_validation_contract_complete": True,
        "write_path_dry_validation": write_path_dry_validation,
        "write_path_dry_validation_runtime_validated": (
            write_path_dry_validation.get(
                "write_path_dry_validation_runtime_validated"
            )
            is True
        ),
        "phase8_m2_validation_complete": phase8_m2_validation_complete,
        "write_path_validated_against_real_order_endpoint": False,
        "real_order_endpoint_not_called_during_dry_validation": True,
        "hot_path_risk_gate_contract_complete": True,
        "phase8_m3_validator_implemented_in_place": True,
        "phase8_m3_new_runtime_module_created": False,
        "hot_path_pre_order_risk_gate_validation": (
            hot_path_pre_order_risk_gate_validation
        ),
        "hot_path_risk_gate_runtime_implemented": True,
        "hot_path_risk_gate_runtime_validated": (
            hot_path_pre_order_risk_gate_validation.get(
                "hot_path_risk_gate_runtime_validated"
            )
            is True
        ),
        "phase8_m3_validation_complete": phase8_m3_validation_complete,
        "executor_final_guard_design_complete": True,
        "phase8_m4_validator_implemented_in_place": True,
        "phase8_m4_new_runtime_module_created": False,
        "executor_final_guard_validation": executor_final_guard_validation,
        "executor_final_guard_runtime_implemented": True,
        "executor_final_guard_runtime_validated": (
            executor_final_guard_validation.get(
                "executor_final_guard_runtime_validated"
            )
            is True
        ),
        "phase8_m4_validation_complete": phase8_m4_validation_complete,
        "phase8_completion_review_allowed": (
            phase8_m4_validation_complete
        ),
        "phase8_implementation_complete": True,
        "phase8_architecture_compressed_in_place": True,
        "phase8_contract_artifact_schema_preserved": True,
        "phase8_single_active_module": True,
        "phase8_new_runtime_modules_created": False,
        "phase8_integrated_runtime_validation_complete": (
            phase8_m4_validation_complete
        ),
        "phase8_fresh_runtime_evidence_validated": (
            phase8_m4_validation_complete
        ),
        "phase8_runtime_evidence_validation_id": stable_id(
            "phase8_fresh_runtime_evidence_validation",
            {
                "metadata_scope_sha256": (
                    metadata_scope_validation.get(
                        "metadata_only_key_scope_validation_sha256"
                    )
                ),
                "write_path_sha256": (
                    write_path_dry_validation.get(
                        "write_path_dry_validation_sha256"
                    )
                ),
                "hot_path_sha256": (
                    hot_path_pre_order_risk_gate_validation.get(
                        "hot_path_pre_order_risk_gate_validation_sha256"
                    )
                ),
                "final_guard_sha256": (
                    executor_final_guard_validation.get(
                        "executor_final_guard_validation_sha256"
                    )
                ),
                "created_at_utc": created,
            },
            24,
        ),
        "phase8_runtime_evidence_sources": {
            "metadata_scope_sha256": (
                metadata_scope_validation.get(
                    "metadata_only_key_scope_validation_sha256"
                )
            ),
            "write_path_sha256": (
                write_path_dry_validation.get(
                    "write_path_dry_validation_sha256"
                )
            ),
            "hot_path_sha256": (
                hot_path_pre_order_risk_gate_validation.get(
                    "hot_path_pre_order_risk_gate_validation_sha256"
                )
            ),
            "final_guard_sha256": (
                executor_final_guard_validation.get(
                    "executor_final_guard_validation_sha256"
                )
            ),
        },
        "phase8_runtime_evidence_valid_for_phase9_review_only": (
            phase8_m4_validation_complete
        ),
        "phase8_runtime_evidence_is_phase9_approval": False,
        "phase8_completion_review_state": (
            "PHASE8_RUNTIME_EVIDENCE_VALIDATED_REVIEW_ONLY"
            if phase8_m4_validation_complete
            else
            "PHASE8_IMPLEMENTATION_COMPLETE_RUNTIME_EVIDENCE_PENDING_REVIEW_ONLY"
        ),
        "phase9_approval_review_allowed": (
            phase8_m4_validation_complete
        ),
        "phase9_separate_approval_required": True,
        "phase9_order_submission_permission_granted": False,
        "monitoring_alerting_runtime_validated": False,
        "kill_switch_runtime_validated": False,
        "clock_sync_runtime_validated": False,
        "rollback_runtime_validated": False,
        "real_fill_position_balance_reconciliation_validated": False,
        "paper_testnet_gap_metrics_validated": False,
        "next_action": next_action,
        **review_only_permission_state(),
        "phase8_execution_allowed": False,
        "phase8_write_path_allowed": False,
        "phase8_secret_value_handling_allowed": False,
        "phase8_executor_enablement_allowed": False,
        "phase8_order_submission_allowed": False,
        "request_signing_allowed": False,
        "adapter_write_routing_enabled": False,
        "exchange_endpoint_called": False,
        "created_at_utc": created,
    }

    report[
        "signed_testnet_execution_preparation_sha256"
    ] = sha256_json(
        report
    )

    return report


def run_signed_testnet_execution_preparation_chain(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = (
        cfg
        or load_config(
            project_root
        )
    )

    pre_executor_review = (
        read_latest_json(
            cfg,
            "pre_executor_review_report.json",
        )
    )

    artifacts = {
        name: read_latest_json(
            cfg,
            file_name,
        )
        for (
            name,
            file_name,
        ) in PHASE8_M1_ARTIFACT_FILES.items()
    }

    report = (
        build_signed_testnet_execution_preparation_report(
            pre_executor_review=(
                pre_executor_review
            ),
            existing_artifacts=(
                artifacts
            ),
        )
    )

    from crypto_ai_system.governance.executor_approval import (
        build_phase9_single_order_approval_review_packet,
    )

    phase9_scope = dict(
        artifacts.get("final_order_intent")
        or {}
    )

    phase9_scope.setdefault(
        "risk_gate_id",
        (
            report.get(
                "hot_path_pre_order_risk_gate_validation"
            )
            or {}
        ).get("risk_gate_id"),
    )

    phase9_single_order_approval_review_packet = (
        build_phase9_single_order_approval_review_packet(
            phase8_report=report,
            proposed_order_scope=phase9_scope,
        )
    )

    persist_report(
        cfg=cfg,
        latest_name=(
            "signed_testnet_execution_preparation_report.json"
        ),
        storage_relative_dir=(
            "storage/governance/"
            "signed_testnet_execution_preparation"
        ),
        storage_name=(
            "signed_testnet_execution_preparation_report.json"
        ),
        payload=report,
    )

    persist_report(
        cfg=cfg,
        latest_name=(
            "phase9_single_order_approval_review_packet.json"
        ),
        storage_relative_dir=(
            "storage/governance/executor_approval"
        ),
        storage_name=(
            "phase9_single_order_approval_review_packet.json"
        ),
        payload=(
            phase9_single_order_approval_review_packet
        ),
    )

    return {
        "report": report,
        "phase9_single_order_approval_review_packet": (
            phase9_single_order_approval_review_packet
        ),
        "design_artifacts": {
            "secret_handling_design": (
                report[
                    "secret_handling_design"
                ]
            ),
            "write_path_dry_validation_contract": (
                report[
                    "write_path_dry_validation_contract"
                ]
            ),
            "hot_path_risk_gate_contract": (
                report[
                    "hot_path_risk_gate_contract"
                ]
            ),
            "executor_final_guard_design": (
                report[
                    "executor_final_guard_design"
                ]
            ),
        },
    }


def run_signed_testnet_execution_preparation_latest(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    return (
        run_signed_testnet_execution_preparation_chain(
            cfg=cfg,
            project_root=project_root,
        )["report"]
    )


__all__ = [
    "PHASE8_M1_VERSION",
    "STATE_WAITING_FOR_PHASE7_OPERATOR_DECISION",
    "STATE_PREPARATION_DESIGN_RECORDED_REVIEW_ONLY",
    "STATE_PREPARATION_EVIDENCE_REPAIR_REQUIRED",
    "STATE_BLOCKED",
    "validate_metadata_only_key_scope",
    "validate_write_path_dry",
    "validate_hot_path_pre_order_risk_gate",
    "validate_executor_final_guard",
    "build_secret_handling_design",
    "build_write_path_dry_validation_contract",
    "build_hot_path_risk_gate_contract",
    "build_executor_final_guard_design",
    "build_signed_testnet_execution_preparation_report",
    "run_signed_testnet_execution_preparation_chain",
    "run_signed_testnet_execution_preparation_latest",
]

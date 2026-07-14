from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.governance.common import (
    DEFAULT_UNSAFE_APPROVAL_FIELDS,
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


def build_secret_handling_design(
    *,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created = (
        created_at_utc
        or utc_now_canonical()
    )

    design: dict[str, Any] = {
        "secret_handling_design_id": (
            stable_id(
                "phase8_m1_secret_handling_design",
                {
                    "version": PHASE8_M1_VERSION,
                    "created_at_utc": created,
                },
                24,
            )
        ),
        "design_type": (
            "signed_testnet_secret_handling_metadata_only_design"
        ),
        "version": PHASE8_M1_VERSION,
        "review_only": True,
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
        "created_at_utc": created,
    }

    design[
        "secret_handling_design_sha256"
    ] = sha256_json(
        design
    )

    return design


def build_write_path_dry_validation_contract(
    *,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created = (
        created_at_utc
        or utc_now_canonical()
    )

    contract: dict[str, Any] = {
        "write_path_dry_validation_contract_id": (
            stable_id(
                "phase8_m1_write_path_dry_validation",
                {
                    "version": PHASE8_M1_VERSION,
                    "created_at_utc": created,
                },
                24,
            )
        ),
        "contract_type": (
            "exchange_write_path_dry_validation_no_endpoint_call"
        ),
        "version": PHASE8_M1_VERSION,
        "review_only": True,
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
        "created_at_utc": created,
    }

    contract[
        "write_path_dry_validation_contract_sha256"
    ] = sha256_json(
        contract
    )

    return contract


def build_hot_path_risk_gate_contract(
    *,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created = (
        created_at_utc
        or utc_now_canonical()
    )

    contract: dict[str, Any] = {
        "hot_path_risk_gate_contract_id": (
            stable_id(
                "phase8_m1_hot_path_risk_gate_contract",
                {
                    "version": PHASE8_M1_VERSION,
                    "created_at_utc": created,
                },
                24,
            )
        ),
        "contract_type": (
            "pre_order_risk_gate_immediate_pre_execution_contract"
        ),
        "version": PHASE8_M1_VERSION,
        "review_only": True,
        "design_only": True,
        "must_run_immediately_before_executor": True,
        "must_run_after_final_order_payload_is_frozen": True,
        "must_run_before_any_request_signing": True,
        "freshness_budget_must_be_configured": True,
        "runtime_freshness_budget_validated": False,
        "required_stage": "signed_testnet",
        "required_status": "PASS_SIGNED_TESTNET",
        "required_approved_value": True,
        "required_checks": list(
            HOT_PATH_REQUIRED_CHECKS
        ),
        "required_id_chain": [
            "data_snapshot_id",
            "feature_snapshot_id",
            "research_signal_id",
            "profile_id",
            "approval_packet_id",
            "approval_intake_id",
            "decision_id",
            "risk_gate_id",
            "order_intent_id",
        ],
        "risk_gate_result_may_be_reused_from_cold_path": False,
        "stale_risk_gate_result_allowed": False,
        "missing_optional_data_may_be_hidden": False,
        "fallback_or_synthetic_candidate_allowed": False,
        "hot_path_risk_gate_runtime_implemented": False,
        "hot_path_risk_gate_runtime_validated": False,
        "executor_enablement_allowed": False,
        "testnet_order_submission_allowed": False,
        "created_at_utc": created,
    }

    contract[
        "hot_path_risk_gate_contract_sha256"
    ] = sha256_json(
        contract
    )

    return contract


def build_executor_final_guard_design(
    *,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created = (
        created_at_utc
        or utc_now_canonical()
    )

    design: dict[str, Any] = {
        "executor_final_guard_design_id": (
            stable_id(
                "phase8_m1_executor_final_guard_design",
                {
                    "version": PHASE8_M1_VERSION,
                    "created_at_utc": created,
                },
                24,
            )
        ),
        "design_type": (
            "signed_testnet_executor_final_guard_design_disabled"
        ),
        "version": PHASE8_M1_VERSION,
        "review_only": True,
        "design_only": True,
        "required_evidence": list(
            FINAL_GUARD_REQUIRED_EVIDENCE
        ),
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
        "executor_final_guard_runtime_implemented": False,
        "executor_final_guard_runtime_validated": False,
        "executor_final_guard_passed_for_execution": False,
        "ready_for_signed_testnet_execution": False,
        "signed_order_executor_enabled": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "created_at_utc": created,
    }

    design[
        "executor_final_guard_design_sha256"
    ] = sha256_json(
        design
    )

    return design


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
            "implement_phase8_m2_metadata_only_key_scope_"
            "and_write_path_dry_validation_keep_executor_disabled"
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
        "metadata_only_key_scope_runtime_validated": False,
        "write_path_dry_validation_contract_complete": True,
        "write_path_dry_validation_runtime_validated": False,
        "write_path_validated_against_real_order_endpoint": False,
        "hot_path_risk_gate_contract_complete": True,
        "hot_path_risk_gate_runtime_implemented": False,
        "hot_path_risk_gate_runtime_validated": False,
        "executor_final_guard_design_complete": True,
        "executor_final_guard_runtime_implemented": False,
        "executor_final_guard_runtime_validated": False,
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

    return {
        "report": report,
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
    "build_secret_handling_design",
    "build_write_path_dry_validation_contract",
    "build_hot_path_risk_gate_contract",
    "build_executor_final_guard_design",
    "build_signed_testnet_execution_preparation_report",
    "run_signed_testnet_execution_preparation_chain",
    "run_signed_testnet_execution_preparation_latest",
]

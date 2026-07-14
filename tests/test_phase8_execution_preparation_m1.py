from __future__ import annotations

from crypto_ai_system.execution.exchange_adapter_contract import (
    DisabledExchangeAdapter,
)
from crypto_ai_system.execution.testnet_secret_metadata_intake_v2 import (
    build_testnet_secret_metadata_intake_v2,
)
from crypto_ai_system.governance.executor_approval import (
    build_phase9_single_order_approval_review_packet,
)

from crypto_ai_system.utils.audit import sha256_json, sha256_text

from crypto_ai_system.governance.signed_testnet_execution_preparation import (
    STATE_BLOCKED,
    STATE_PREPARATION_DESIGN_RECORDED_REVIEW_ONLY,
    STATE_WAITING_FOR_PHASE7_OPERATOR_DECISION,
    build_executor_final_guard_design,
    build_hot_path_risk_gate_contract,
    build_secret_handling_design,
    build_signed_testnet_execution_preparation_report,
    build_write_path_dry_validation_contract,
    HOT_PATH_REQUIRED_CHECKS,
    PHASE8_M4_REQUIRED_OPERATIONAL_CHECKS,
    validate_executor_final_guard,
    validate_hot_path_pre_order_risk_gate,
    validate_metadata_only_key_scope,
    validate_write_path_dry,
)


def _approved_pre_executor_review() -> dict:
    return {
        "pre_executor_review_id": "pre_executor_review_001",
        "pre_executor_review_state": (
            "OPERATOR_APPROVED_PHASE8_PREPARATION_REVIEW_ONLY"
        ),
        "final_pre_executor_review_ready": True,
        "phase8_preparation_design_review_allowed": True,
        "actual_operator_decision_recorded": True,
        "operator_decision_is_runtime_authority": False,
        "operator_decision_can_transition_stage": False,
        "operator_decision_can_enable_executor": False,
        "operator_decision_can_submit_order": False,
        "blocked": False,
        "fail_closed": False,
        "review_only": True,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "runtime_settings_mutated": False,
        "auto_promotion_allowed": False,
    }


def _waiting_pre_executor_review() -> dict:
    payload = _approved_pre_executor_review()

    payload.update(
        {
            "pre_executor_review_state": (
                "WAITING_FOR_OPERATOR_DECISION"
            ),
            "final_pre_executor_review_ready": False,
            "phase8_preparation_design_review_allowed": False,
            "actual_operator_decision_recorded": False,
            "waiting_for_operator_decision": True,
        }
    )

    return payload


def _safe_existing_artifacts() -> dict:
    return {
        "secret_metadata_intake": {
            "status": "VALID_METADATA_ONLY_TESTNET_REFERENCE",
            "metadata_only": True,
            "testnet_order_submission_allowed": False,
            "external_order_submission_allowed": False,
            "external_order_submission_performed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "api_key_value_access_allowed": False,
            "api_secret_value_access_allowed": False,
            "secret_file_access_allowed": False,
            "secret_file_creation_allowed": False,
        },
        "read_only_venue_probe": {
            "status": "REAL_READ_ONLY_VENUE_PROBE_VALID",
            "valid": True,
            "testnet_order_submission_allowed": False,
            "external_order_submission_allowed": False,
            "external_order_submission_performed": False,
            "exchange_endpoint_called": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
        },
        "pre_submit_validation": {
            "status": (
                "SIGNED_TESTNET_PRE_SUBMIT_VALIDATED_REVIEW_ONLY"
            ),
            "review_only": True,
            "testnet_order_submission_allowed": False,
            "external_order_submission_allowed": False,
            "external_order_submission_performed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
        },
        "enablement_packet": {
            "status": (
                "SIGNED_TESTNET_EXECUTION_ENABLEMENT_PACKET_"
                "READY_REVIEW_ONLY"
            ),
            "review_only": True,
            "testnet_order_submission_allowed": False,
            "external_order_submission_allowed": False,
            "external_order_submission_performed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
        },
        "disabled_executor_evidence": {
            "status": "NO_SIGNED_TESTNET_ORDER_SUBMITTED",
            "testnet_order_submission_allowed": False,
            "external_order_submission_allowed": False,
            "external_order_submission_performed": False,
            "exchange_endpoint_called": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
        },
    }


def test_secret_handling_design_is_metadata_only() -> None:
    design = build_secret_handling_design(
        created_at_utc="2026-07-14T00:00:00Z",
    )

    assert design["review_only"] is True
    assert design["design_only"] is True
    assert design["metadata_only_required"] is True
    assert design["secret_dereference_allowed"] is False
    assert design["secret_value_read_allowed"] is False
    assert design["secret_file_read_allowed"] is False
    assert design["secret_file_creation_allowed"] is False
    assert design["request_signing_allowed"] is False
    assert design["executor_enablement_allowed"] is False
    assert design["testnet_order_submission_allowed"] is False

    for field in (
        "api_key",
        "api_secret",
        "private_key",
        "passphrase",
        "seed_phrase",
        "mnemonic",
    ):
        assert (
            field
            in design["forbidden_secret_value_fields"]
        )


def test_write_path_dry_contract_never_calls_endpoint() -> None:
    contract = build_write_path_dry_validation_contract(
        created_at_utc="2026-07-14T00:00:00Z",
    )

    assert contract["dry_validation_only"] is True
    assert contract["network_transport_enabled"] is False
    assert contract["request_signing_enabled"] is False

    assert (
        contract[
            "exchange_write_endpoint_invocation_enabled"
        ]
        is False
    )

    assert contract["actual_http_request_created"] is False

    assert (
        contract[
            "write_path_validated_against_real_order_endpoint"
        ]
        is False
    )

    assert (
        contract["external_order_submission_performed"]
        is False
    )

    assert contract["exchange_endpoint_called"] is False
    assert contract["testnet_order_submission_allowed"] is False


def test_hot_path_risk_gate_contract_requires_fresh_recheck() -> None:
    contract = build_hot_path_risk_gate_contract(
        created_at_utc="2026-07-14T00:00:00Z",
    )

    assert (
        contract["must_run_immediately_before_executor"]
        is True
    )

    assert (
        contract["must_run_after_final_order_payload_is_frozen"]
        is True
    )

    assert (
        contract["must_run_before_any_request_signing"]
        is True
    )

    assert (
        contract["risk_gate_result_may_be_reused_from_cold_path"]
        is False
    )

    assert contract["stale_risk_gate_result_allowed"] is False

    assert (
        contract["hot_path_risk_gate_runtime_implemented"]
        is True
    )

    assert (
        contract["hot_path_risk_gate_runtime_validated"]
        is False
    )

    for required in (
        "approved_profile_hash_matches",
        "data_freshness_valid",
        "fallback_synthetic_mock_sample_absent",
        "daily_loss_limit_valid",
        "kill_switch_inactive",
        "hard_caps_valid",
        "venue_readiness_valid",
        "canonical_id_chain_complete",
    ):
        assert required in contract["required_checks"]


def test_executor_final_guard_is_design_only_and_disabled() -> None:
    design = build_executor_final_guard_design(
        created_at_utc="2026-07-14T00:00:00Z",
    )

    assert design["review_only"] is True
    assert design["design_only"] is False

    assert (
        design["executor_final_guard_runtime_implemented"]
        is True
    )

    assert (
        design["executor_final_guard_runtime_validated"]
        is False
    )

    assert (
        design["executor_final_guard_passed_for_execution"]
        is False
    )

    assert (
        design["ready_for_signed_testnet_execution"]
        is False
    )

    assert design["signed_order_executor_enabled"] is False
    assert design["testnet_order_submission_allowed"] is False
    assert design["external_order_submission_allowed"] is False
    assert design["place_order_enabled"] is False
    assert design["cancel_order_enabled"] is False


def test_approved_phase7_records_phase8_design_only() -> None:
    report = (
        build_signed_testnet_execution_preparation_report(
            pre_executor_review=(
                _approved_pre_executor_review()
            ),
            existing_artifacts=(
                _safe_existing_artifacts()
            ),
            created_at_utc="2026-07-14T00:00:00Z",
        )
    )

    assert (
        report["phase8_execution_preparation_state"]
        == STATE_PREPARATION_DESIGN_RECORDED_REVIEW_ONLY
    )

    assert report["blocked"] is False
    assert report["phase8_m1_design_complete"] is True

    assert (
        report["phase8_preparation_design_review_allowed"]
        is True
    )

    assert (
        report["phase8_execution_preparation_ready"]
        is False
    )

    assert (
        report["metadata_only_key_scope_runtime_validated"]
        is False
    )

    assert (
        report["write_path_dry_validation_runtime_validated"]
        is True
    )

    assert (
        report["hot_path_risk_gate_runtime_validated"]
        is False
    )

    assert (
        report["executor_final_guard_runtime_validated"]
        is False
    )

    assert report["phase8_execution_allowed"] is False
    assert report["phase8_write_path_allowed"] is False

    assert (
        report["phase8_secret_value_handling_allowed"]
        is False
    )

    assert (
        report["phase8_executor_enablement_allowed"]
        is False
    )

    assert (
        report["phase8_order_submission_allowed"]
        is False
    )

    assert (
        report["ready_for_signed_testnet_execution"]
        is False
    )

    assert (
        report["testnet_order_submission_allowed"]
        is False
    )

    assert (
        report["external_order_submission_performed"]
        is False
    )

    assert report["exchange_endpoint_called"] is False


def test_missing_operator_decision_waits_without_opening_phase8() -> None:
    report = (
        build_signed_testnet_execution_preparation_report(
            pre_executor_review=(
                _waiting_pre_executor_review()
            ),
            existing_artifacts=(
                _safe_existing_artifacts()
            ),
            created_at_utc="2026-07-14T00:00:00Z",
        )
    )

    assert (
        report["phase8_execution_preparation_state"]
        == STATE_WAITING_FOR_PHASE7_OPERATOR_DECISION
    )

    assert report["blocked"] is False

    assert (
        report["phase8_preparation_design_review_allowed"]
        is False
    )

    assert report["phase8_execution_allowed"] is False
    assert report["phase8_order_submission_allowed"] is False


def test_unsafe_existing_artifact_blocks_fail_closed() -> None:
    artifacts = _safe_existing_artifacts()

    artifacts[
        "disabled_executor_evidence"
    ][
        "external_order_submission_performed"
    ] = True

    report = (
        build_signed_testnet_execution_preparation_report(
            pre_executor_review=(
                _approved_pre_executor_review()
            ),
            existing_artifacts=artifacts,
            created_at_utc="2026-07-14T00:00:00Z",
        )
    )

    assert (
        report["phase8_execution_preparation_state"]
        == STATE_BLOCKED
    )

    assert report["blocked"] is True
    assert report["fail_closed"] is True

    assert (
        report["phase8_preparation_design_review_allowed"]
        is False
    )

    assert (
        "UNSAFE_EXISTING_EXECUTION_PREPARATION_ARTIFACT"
        in report["blockers"]
    )

    assert (
        report["external_order_submission_performed"]
        is False
    )

    assert report["phase8_execution_allowed"] is False
    assert report["testnet_order_submission_allowed"] is False
def _phase8_m2_valid_metadata_intake() -> dict:
    return build_testnet_secret_metadata_intake_v2(
        {
            "secret_reference_id": (
                "metadata_ref:testnet/extended/phase8_m2_review_only"
            ),
            "key_fingerprint_sha256": sha256_text(
                "phase8-m2-extended-testnet-metadata-only"
            ),
            "environment": "signed_testnet",
            "venue": "extended_testnet",
            "scope": [
                "read_only",
                "signed_testnet_preparation",
            ],
            "operator_id": "operator_phase8_m2_review_only",
            "base_url": "https://testnet.review-only.invalid",
            "secret_file_loaded": False,
            "secret_file_created": False,
            "secret_bytes_read": False,
            "secret_value_read": False,
            "live_key_detected": False,
            "created_at_utc": "2026-07-14T00:00:00Z",
        }
    )


def test_phase8_m2_metadata_scope_reuses_existing_intake_validator() -> None:
    report = validate_metadata_only_key_scope(
        _phase8_m2_valid_metadata_intake(),
        created_at_utc="2026-07-14T00:00:00Z",
    )

    assert report["valid"] is True
    assert report["metadata_only_key_scope_runtime_validated"] is True
    assert report["secret_value_access_performed"] is False
    assert report["secret_file_read"] is False
    assert report["request_signing_performed"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False


def test_phase8_m2_metadata_scope_blocks_live_and_high_risk_scope() -> None:
    intake = _phase8_m2_valid_metadata_intake()
    intake["environment"] = "mainnet"
    intake["scope"] = ["admin", "withdrawal"]

    report = validate_metadata_only_key_scope(intake)

    assert report["valid"] is False
    assert report["metadata_only_key_scope_runtime_validated"] is False
    assert report["blocked"] is True
    assert report["fail_closed"] is True


def test_phase8_m2_write_path_dry_never_calls_or_opens_transport() -> None:
    adapter = DisabledExchangeAdapter(
        venue="extended_testnet",
        environment="signed_testnet",
    )

    report = validate_write_path_dry(
        adapter_capabilities=adapter.get_capabilities(),
        request_preview={
            "order_intent_id": "phase8_m2_order_intent",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "client_order_id": "phase8m2-client-001",
            "idempotency_key": "phase8m2-idem-001",
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
        created_at_utc="2026-07-14T00:00:00Z",
    )

    assert report["valid"] is True
    assert report["write_path_dry_validation_runtime_validated"] is True
    assert report["place_order_method_called"] is False
    assert report["cancel_order_method_called"] is False
    assert report["network_transport_invocation_count"] == 0
    assert report["request_signing_invocation_count"] == 0
    assert report["exchange_endpoint_call_count"] == 0
    assert report["write_path_validated_against_real_order_endpoint"] is False
    assert report["external_order_submission_performed"] is False


def test_phase8_m2_in_place_report_does_not_make_execution_ready() -> None:
    artifacts = _safe_existing_artifacts()
    artifacts["secret_metadata_intake"] = _phase8_m2_valid_metadata_intake()

    report = build_signed_testnet_execution_preparation_report(
        pre_executor_review=_approved_pre_executor_review(),
        existing_artifacts=artifacts,
        created_at_utc="2026-07-14T00:00:00Z",
    )

    assert report["phase8_m2_validators_implemented_in_place"] is True
    assert report["metadata_only_key_scope_runtime_validated"] is True
    assert report["write_path_dry_validation_runtime_validated"] is True
    assert report["phase8_m2_validation_complete"] is True
    assert report["phase8_execution_preparation_ready"] is False
    assert report["hot_path_risk_gate_runtime_implemented"] is True
    assert report["executor_final_guard_runtime_implemented"] is True
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
def _phase8_m3_final_order_intent() -> dict:
    intent = {
        "stage": "signed_testnet",
        "payload_frozen": True,
        "data_snapshot_id": "data_snapshot_phase8_m3",
        "feature_snapshot_id": "feature_snapshot_phase8_m3",
        "research_signal_id": "research_signal_phase8_m3",
        "profile_id": "profile_phase8_m3",
        "approval_packet_id": "approval_packet_phase8_m3",
        "approval_intake_id": "approval_intake_phase8_m3",
        "decision_id": "decision_phase8_m3",
        "order_intent_id": "order_intent_phase8_m3",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": "0.001",
        "price": "1",
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
    }
    intent["final_order_intent_sha256"] = sha256_json(intent)
    return intent


def _phase8_m3_fresh_risk_evidence(intent: dict) -> dict:
    return {
        "stage": "signed_testnet",
        "status": "PASS_SIGNED_TESTNET",
        "approved": True,
        "evaluation_mode": "hot_path_immediate_pre_execution",
        "evaluated_at_utc": "2026-07-14T00:00:00Z",
        "risk_gate_id": "risk_gate_phase8_m3",
        "order_intent_id": intent["order_intent_id"],
        "final_order_intent_sha256": intent["final_order_intent_sha256"],
        "data_snapshot_id": intent["data_snapshot_id"],
        "feature_snapshot_id": intent["feature_snapshot_id"],
        "research_signal_id": intent["research_signal_id"],
        "profile_id": intent["profile_id"],
        "approval_packet_id": intent["approval_packet_id"],
        "approval_intake_id": intent["approval_intake_id"],
        "decision_id": intent["decision_id"],
        "optional_data_health": "healthy",
        "checks": {name: True for name in HOT_PATH_REQUIRED_CHECKS},
        "fallback_used": False,
        "synthetic_data_used": False,
        "mock_data_used": False,
        "sample_data_used": False,
        "stale_data_used": False,
        "hidden_missing_data_used": False,
        "missing_source_neutral_used": False,
        "kill_switch_active": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
    }


def test_phase8_m3_fresh_hot_path_gate_passes_without_execution_permission() -> None:
    intent = _phase8_m3_final_order_intent()
    evidence = _phase8_m3_fresh_risk_evidence(intent)
    report = validate_hot_path_pre_order_risk_gate(
        final_order_intent=intent,
        fresh_risk_evidence=evidence,
        phase8_m2_validation_complete=True,
        created_at_utc="2026-07-14T00:00:00Z",
    )
    assert report["valid"] is True
    assert report["hot_path_risk_gate_runtime_implemented"] is True
    assert report["hot_path_risk_gate_runtime_validated"] is True
    assert report["must_run_immediately_before_executor"] is True
    assert report["cold_path_risk_result_reused"] is False
    assert report["failed_checks"] == []
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["external_order_submission_performed"] is False
    assert report["request_signing_performed"] is False
    assert report["exchange_endpoint_called"] is False


def test_phase8_m3_stale_evidence_blocks_fail_closed() -> None:
    intent = _phase8_m3_final_order_intent()
    evidence = _phase8_m3_fresh_risk_evidence(intent)
    report = validate_hot_path_pre_order_risk_gate(
        final_order_intent=intent,
        fresh_risk_evidence=evidence,
        phase8_m2_validation_complete=True,
        created_at_utc="2026-07-14T00:01:00Z",
        max_evidence_age_seconds=30,
    )
    assert report["valid"] is False
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "PHASE8_M3_EVIDENCE_STALE" in report["blockers"]


def test_phase8_m3_required_check_failure_blocks() -> None:
    intent = _phase8_m3_final_order_intent()
    evidence = _phase8_m3_fresh_risk_evidence(intent)
    evidence["checks"]["kill_switch_inactive"] = False
    report = validate_hot_path_pre_order_risk_gate(
        final_order_intent=intent,
        fresh_risk_evidence=evidence,
        phase8_m2_validation_complete=True,
        created_at_utc="2026-07-14T00:00:00Z",
    )
    assert report["valid"] is False
    assert "kill_switch_inactive" in report["failed_checks"]
    assert report["ready_for_signed_testnet_execution"] is False


def test_phase8_m3_in_place_report_opens_only_m4_review_scope() -> None:
    artifacts = _safe_existing_artifacts()
    artifacts["secret_metadata_intake"] = _phase8_m2_valid_metadata_intake()
    intent = _phase8_m3_final_order_intent()
    artifacts["final_order_intent"] = intent
    artifacts["hot_path_risk_gate_evidence"] = _phase8_m3_fresh_risk_evidence(intent)
    report = build_signed_testnet_execution_preparation_report(
        pre_executor_review=_approved_pre_executor_review(),
        existing_artifacts=artifacts,
        created_at_utc="2026-07-14T00:00:00Z",
    )
    assert report["phase8_m2_validation_complete"] is True
    assert report["phase8_m3_validator_implemented_in_place"] is True
    assert report["hot_path_risk_gate_runtime_implemented"] is True
    assert report["hot_path_risk_gate_runtime_validated"] is True
    assert report["phase8_m3_validation_complete"] is True
    assert report["phase8_execution_preparation_ready"] is False
    assert report["executor_final_guard_runtime_implemented"] is True
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["next_action"] == (
        "collect_or_repair_executor_final_guard_operational_"
        "evidence_keep_executor_disabled"
    )


def test_phase8_m3_missing_evidence_repairs_without_m2_order_bug() -> None:
    artifacts = _safe_existing_artifacts()
    artifacts["secret_metadata_intake"] = _phase8_m2_valid_metadata_intake()
    report = build_signed_testnet_execution_preparation_report(
        pre_executor_review=_approved_pre_executor_review(),
        existing_artifacts=artifacts,
        created_at_utc="2026-07-14T00:00:00Z",
    )
    assert report["phase8_m2_validation_complete"] is True
    assert report["phase8_m3_validation_complete"] is False
    assert report["blocked"] is False
    assert report["phase8_execution_preparation_ready"] is False
    assert report["next_action"] == (
        "collect_or_repair_fresh_hot_path_pre_order_risk_gate_"
        "evidence_keep_executor_disabled"
    )
def _phase8_m4_operational_evidence(hot_path_validation: dict) -> dict:
    return {
        "stage": "signed_testnet",
        "status": "PASS_REVIEW_ONLY",
        "evidence_complete": True,
        "evaluated_at_utc": "2026-07-14T00:00:00Z",
        "hot_path_validation_sha256": hot_path_validation[
            "hot_path_pre_order_risk_gate_validation_sha256"
        ],
        "final_order_intent_sha256": hot_path_validation[
            "final_order_intent_sha256"
        ],
        "risk_gate_id": hot_path_validation["risk_gate_id"],
        "checks": {
            name: True for name in PHASE8_M4_REQUIRED_OPERATIONAL_CHECKS
        },
        "request_signing_performed": False,
        "network_write_transport_opened": False,
        "exchange_endpoint_called": False,
        "exchange_endpoint_call_count": 0,
        "external_order_submission_performed": False,
        "position_mutation_performed": False,
        "balance_mutation_performed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
    }


def _phase8_m4_valid_hot_path_validation() -> dict:
    intent = _phase8_m3_final_order_intent()
    evidence = _phase8_m3_fresh_risk_evidence(intent)
    return validate_hot_path_pre_order_risk_gate(
        final_order_intent=intent,
        fresh_risk_evidence=evidence,
        phase8_m2_validation_complete=True,
        created_at_utc="2026-07-14T00:00:00Z",
    )


def test_phase8_m4_final_guard_aggregates_without_execution_permission() -> None:
    hot_path = _phase8_m4_valid_hot_path_validation()
    operations = _phase8_m4_operational_evidence(hot_path)
    report = validate_executor_final_guard(
        phase8_m2_validation_complete=True,
        hot_path_validation=hot_path,
        operational_evidence=operations,
        created_at_utc="2026-07-14T00:00:00Z",
    )
    assert report["valid"] is True
    assert report["aggregates_existing_m2_m3_results"] is True
    assert report["duplicates_m2_m3_checks"] is False
    assert report["executor_final_guard_runtime_implemented"] is True
    assert report["executor_final_guard_runtime_validated"] is True
    assert report["phase8_completion_review_allowed"] is True
    assert report["phase9_separate_approval_required"] is True
    assert report["phase9_order_submission_permission_granted"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["external_order_submission_performed"] is False


def test_phase8_m4_monitoring_uncertainty_blocks_fail_closed() -> None:
    hot_path = _phase8_m4_valid_hot_path_validation()
    operations = _phase8_m4_operational_evidence(hot_path)
    operations["checks"]["monitoring_ready"] = False
    report = validate_executor_final_guard(
        phase8_m2_validation_complete=True,
        hot_path_validation=hot_path,
        operational_evidence=operations,
        created_at_utc="2026-07-14T00:00:00Z",
    )
    assert report["valid"] is False
    assert report["fail_closed"] is True
    assert "monitoring_ready" in report["failed_operational_checks"]


def test_phase8_m4_stale_operational_evidence_blocks() -> None:
    hot_path = _phase8_m4_valid_hot_path_validation()
    operations = _phase8_m4_operational_evidence(hot_path)
    report = validate_executor_final_guard(
        phase8_m2_validation_complete=True,
        hot_path_validation=hot_path,
        operational_evidence=operations,
        created_at_utc="2026-07-14T00:01:00Z",
        max_evidence_age_seconds=30,
    )
    assert report["valid"] is False
    assert "PHASE8_M4_OPERATIONAL_EVIDENCE_STALE" in report["blockers"]
def test_phase8_contract_builders_share_factory_and_preserve_hashes() -> None:
    secret = build_secret_handling_design(
        created_at_utc="2026-07-14T00:00:00Z"
    )
    dry = build_write_path_dry_validation_contract(
        created_at_utc="2026-07-14T00:00:00Z"
    )
    hot = build_hot_path_risk_gate_contract(
        created_at_utc="2026-07-14T00:00:00Z"
    )
    guard = build_executor_final_guard_design(
        created_at_utc="2026-07-14T00:00:00Z"
    )

    for payload, hash_field in (
        (secret, "secret_handling_design_sha256"),
        (dry, "write_path_dry_validation_contract_sha256"),
        (hot, "hot_path_risk_gate_contract_sha256"),
        (guard, "executor_final_guard_design_sha256"),
    ):
        expected = payload[hash_field]
        body = dict(payload)
        body.pop(hash_field)
        assert expected == sha256_json(body)

    assert secret["metadata_only_required"] is True
    assert dry["exchange_endpoint_called"] is False
    assert hot["hot_path_risk_gate_runtime_implemented"] is True
    assert hot["hot_path_risk_gate_runtime_validated"] is False
    assert guard["executor_final_guard_runtime_implemented"] is True
    assert guard["executor_final_guard_runtime_validated"] is False
    assert guard["ready_for_signed_testnet_execution"] is False


def test_phase8_integrated_completion_review_requires_runtime_evidence() -> None:
    artifacts = _safe_existing_artifacts()
    artifacts["secret_metadata_intake"] = (
        _phase8_m2_valid_metadata_intake()
    )

    report = build_signed_testnet_execution_preparation_report(
        pre_executor_review=_approved_pre_executor_review(),
        existing_artifacts=artifacts,
        created_at_utc="2026-07-14T00:00:00Z",
    )

    assert report["phase8_implementation_complete"] is True
    assert report["phase8_architecture_compressed_in_place"] is True
    assert report["phase8_contract_artifact_schema_preserved"] is True
    assert report["phase8_integrated_runtime_validation_complete"] is False
    assert report["phase9_approval_review_allowed"] is False
    assert report["phase8_execution_preparation_ready"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False


def test_phase8_integrated_completion_review_never_grants_order_permission() -> None:
    artifacts = _safe_existing_artifacts()
    artifacts["secret_metadata_intake"] = (
        _phase8_m2_valid_metadata_intake()
    )

    intent = _phase8_m3_final_order_intent()
    artifacts["final_order_intent"] = intent
    artifacts["hot_path_risk_gate_evidence"] = (
        _phase8_m3_fresh_risk_evidence(intent)
    )

    hot_path = validate_hot_path_pre_order_risk_gate(
        final_order_intent=intent,
        fresh_risk_evidence=(
            artifacts["hot_path_risk_gate_evidence"]
        ),
        phase8_m2_validation_complete=True,
        created_at_utc="2026-07-14T00:00:00Z",
    )
    artifacts["executor_final_guard_evidence"] = (
        _phase8_m4_operational_evidence(hot_path)
    )

    report = build_signed_testnet_execution_preparation_report(
        pre_executor_review=_approved_pre_executor_review(),
        existing_artifacts=artifacts,
        created_at_utc="2026-07-14T00:00:00Z",
    )

    assert report["phase8_integrated_runtime_validation_complete"] is True
    assert report["phase8_completion_review_allowed"] is True
    assert report["phase9_approval_review_allowed"] is True
    assert report["phase9_separate_approval_required"] is True
    assert report["phase9_order_submission_permission_granted"] is False
    assert report["phase8_execution_preparation_ready"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["external_order_submission_performed"] is False
def _phase9_complete_order_scope(
    phase8_report: dict,
) -> dict:
    hot_path = phase8_report[
        "hot_path_pre_order_risk_gate_validation"
    ]

    return {
        "stage": "signed_testnet",
        "payload_frozen": True,
        "maximum_order_count": 1,
        "order_intent_id": hot_path["final_order_intent_id"],
        "final_order_intent_sha256": hot_path[
            "final_order_intent_sha256"
        ],
        "risk_gate_id": hot_path["risk_gate_id"],
        "venue": "extended_testnet",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "LIMIT",
        "max_notional_cap": "25",
        "approval_expires_at_utc": "2026-07-14T00:05:00Z",
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
    }


def test_phase8_fresh_runtime_evidence_projection_is_review_only() -> None:
    artifacts = _safe_existing_artifacts()
    artifacts["secret_metadata_intake"] = (
        _phase8_m2_valid_metadata_intake()
    )

    intent = _phase8_m3_final_order_intent()
    artifacts["final_order_intent"] = intent
    artifacts["hot_path_risk_gate_evidence"] = (
        _phase8_m3_fresh_risk_evidence(intent)
    )

    hot_path = validate_hot_path_pre_order_risk_gate(
        final_order_intent=intent,
        fresh_risk_evidence=(
            artifacts["hot_path_risk_gate_evidence"]
        ),
        phase8_m2_validation_complete=True,
        created_at_utc="2026-07-14T00:00:00Z",
    )
    artifacts["executor_final_guard_evidence"] = (
        _phase8_m4_operational_evidence(hot_path)
    )

    report = build_signed_testnet_execution_preparation_report(
        pre_executor_review=_approved_pre_executor_review(),
        existing_artifacts=artifacts,
        created_at_utc="2026-07-14T00:00:00Z",
    )

    assert report["phase8_fresh_runtime_evidence_validated"] is True
    assert report["phase8_runtime_evidence_valid_for_phase9_review_only"] is True
    assert report["phase8_runtime_evidence_is_phase9_approval"] is False
    assert report["phase8_execution_preparation_ready"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False


def test_phase9_single_order_review_waits_for_fresh_phase8_evidence() -> None:
    report = build_signed_testnet_execution_preparation_report(
        pre_executor_review=_approved_pre_executor_review(),
        existing_artifacts=_safe_existing_artifacts(),
        created_at_utc="2026-07-14T00:00:00Z",
    )

    packet = build_phase9_single_order_approval_review_packet(
        phase8_report=report,
        proposed_order_scope={},
        created_at_utc="2026-07-14T00:00:00Z",
    )

    assert packet[
        "phase9_single_order_approval_review_packet_ready"
    ] is False
    assert packet["blocked"] is True
    assert packet["actual_phase9_approval_created"] is False
    assert packet["phase9_order_submission_permission_granted"] is False
    assert packet["testnet_order_submission_allowed"] is False


def test_phase9_single_order_review_packet_never_grants_permission() -> None:
    artifacts = _safe_existing_artifacts()
    artifacts["secret_metadata_intake"] = (
        _phase8_m2_valid_metadata_intake()
    )

    intent = _phase8_m3_final_order_intent()
    artifacts["final_order_intent"] = intent
    artifacts["hot_path_risk_gate_evidence"] = (
        _phase8_m3_fresh_risk_evidence(intent)
    )

    hot_path = validate_hot_path_pre_order_risk_gate(
        final_order_intent=intent,
        fresh_risk_evidence=(
            artifacts["hot_path_risk_gate_evidence"]
        ),
        phase8_m2_validation_complete=True,
        created_at_utc="2026-07-14T00:00:00Z",
    )
    artifacts["executor_final_guard_evidence"] = (
        _phase8_m4_operational_evidence(hot_path)
    )

    report = build_signed_testnet_execution_preparation_report(
        pre_executor_review=_approved_pre_executor_review(),
        existing_artifacts=artifacts,
        created_at_utc="2026-07-14T00:00:00Z",
    )

    packet = build_phase9_single_order_approval_review_packet(
        phase8_report=report,
        proposed_order_scope=_phase9_complete_order_scope(
            report
        ),
        created_at_utc="2026-07-14T00:00:00Z",
    )

    assert packet[
        "phase9_single_order_approval_review_packet_ready"
    ] is True
    assert packet["approval_scope"] == (
        "single_signed_testnet_order"
    )
    assert packet["maximum_order_count"] == 1
    assert packet["single_order_only"] is True
    assert packet["explicit_operator_approval_required"] is True
    assert packet["actual_phase9_approval_created"] is False
    assert packet["phase9_approval_runtime_authority"] is False
    assert packet["phase9_executor_enablement_allowed"] is False
    assert packet["phase9_request_signing_allowed"] is False
    assert packet["phase9_order_submission_permission_granted"] is False
    assert packet["phase9_order_submission_performed"] is False
    assert packet["ready_for_signed_testnet_execution"] is False
    assert packet["testnet_order_submission_allowed"] is False
    assert packet["external_order_submission_performed"] is False


def test_phase9_single_order_scope_cannot_expand_order_count() -> None:
    phase8_report = {
        "signed_testnet_execution_preparation_id": "phase8",
        "phase8_fresh_runtime_evidence_validated": True,
        "phase8_integrated_runtime_validation_complete": True,
        "phase8_completion_review_allowed": True,
        "phase9_approval_review_allowed": True,
        "phase8_execution_preparation_ready": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "hot_path_pre_order_risk_gate_validation": {
            "final_order_intent_id": "intent",
            "final_order_intent_sha256": "a" * 64,
            "risk_gate_id": "risk",
        },
    }
    phase8_report[
        "signed_testnet_execution_preparation_sha256"
    ] = sha256_json(phase8_report)

    scope = {
        "stage": "signed_testnet",
        "payload_frozen": True,
        "maximum_order_count": 2,
        "order_intent_id": "intent",
        "final_order_intent_sha256": "a" * 64,
        "risk_gate_id": "risk",
        "venue": "extended_testnet",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "LIMIT",
        "max_notional_cap": "25",
        "approval_expires_at_utc": "2026-07-14T00:05:00Z",
    }

    packet = build_phase9_single_order_approval_review_packet(
        phase8_report=phase8_report,
        proposed_order_scope=scope,
    )

    assert packet[
        "phase9_single_order_approval_review_packet_ready"
    ] is False
    assert (
        "PHASE9_MAXIMUM_ORDER_COUNT_MUST_EQUAL_ONE"
        in packet["blockers"]
    )
def test_phase9_runner_summary_preserves_review_only_boundary(
    tmp_path,
) -> None:
    from scripts.build_phase9_single_order_review import (
        _build_summary,
    )

    phase7_result = {
        "report": {
            "status": "PRE_EXECUTOR_REVIEW_WAITING_FOR_OPERATOR_DECISION_REVIEW_ONLY",
            "pre_executor_review_state": "WAITING_FOR_OPERATOR_DECISION",
            "operator_decision_intake_validated": False,
            "actual_operator_decision_recorded": False,
            "final_pre_executor_review_ready": False,
            "blockers": [],
            "next_action": "record_manual_operator_decision",
        },
        "legacy_outputs": {
            "operator_decision_intake_template": {
                "source_phase7_14_report_id": "phase7_14_report",
                "source_phase7_14_report_hash": "a" * 64,
                "source_stage_transition_review_id": "stage_transition",
                "source_stage_transition_review_hash": "b" * 64,
            },
        },
    }

    phase8_result = {
        "report": {
            "status": "PHASE8_M1_WAITING_FOR_PHASE7_OPERATOR_DECISION_REVIEW_ONLY",
            "phase8_fresh_runtime_evidence_validated": False,
            "blockers": [],
            "next_action": "complete_phase7_manual_operator_decision_intake",
        },
        "phase9_single_order_approval_review_packet": {
            "status": (
                "PHASE9_SINGLE_ORDER_APPROVAL_REVIEW_"
                "WAITING_FOR_FRESH_PHASE8_EVIDENCE"
            ),
            "phase9_single_order_approval_review_packet_ready": False,
            "blockers": [
                "PHASE9_FRESH_PHASE8_RUNTIME_EVIDENCE_NOT_VALIDATED"
            ],
            "next_action": "collect_fresh_phase8_runtime_evidence",
        },
    }

    summary = _build_summary(
        mode="prepare-template",
        project_root=tmp_path,
        phase7_result=phase7_result,
        phase8_result=phase8_result,
    )

    assert summary["canonical_handoff_runner"] is True
    assert summary["operator_submission_written_automatically"] is False
    assert summary["source_phase7_14_report_id"] == "phase7_14_report"
    assert summary["source_phase7_14_report_hash"] == "a" * 64
    assert summary["phase7_final_pre_executor_review_ready"] is False
    assert summary["phase8_fresh_runtime_evidence_validated"] is False
    assert summary["phase9_review_packet_ready"] is False
    assert summary["actual_phase9_approval_created"] is False
    assert summary["phase9_order_submission_permission_granted"] is False
    assert summary["ready_for_signed_testnet_execution"] is False
    assert summary["testnet_order_submission_allowed"] is False
    assert summary["external_order_submission_performed"] is False


def test_phase9_runner_loads_only_json_object_submission(
    tmp_path,
) -> None:
    from scripts.build_phase9_single_order_review import (
        _load_json_object,
    )

    valid = (
        tmp_path
        / "valid.json"
    )

    valid.write_text(
        '{"decision_option":"APPROVE"}',
        encoding="utf-8",
    )

    assert (
        _load_json_object(
            valid
        )["decision_option"]
        == "APPROVE"
    )

    invalid = (
        tmp_path
        / "invalid.json"
    )

    invalid.write_text(
        '["not","an","object"]',
        encoding="utf-8",
    )

    try:
        _load_json_object(
            invalid
        )
    except ValueError as exc:
        assert (
            "Expected a JSON object"
            in str(exc)
        )
    else:
        raise AssertionError(
            "Non-object operator submission must fail closed."
        )

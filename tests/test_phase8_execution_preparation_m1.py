from __future__ import annotations

from crypto_ai_system.governance.signed_testnet_execution_preparation import (
    STATE_BLOCKED,
    STATE_PREPARATION_DESIGN_RECORDED_REVIEW_ONLY,
    STATE_WAITING_FOR_PHASE7_OPERATOR_DECISION,
    build_executor_final_guard_design,
    build_hot_path_risk_gate_contract,
    build_secret_handling_design,
    build_signed_testnet_execution_preparation_report,
    build_write_path_dry_validation_contract,
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
        is False
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
    assert design["design_only"] is True

    assert (
        design["executor_final_guard_runtime_implemented"]
        is False
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
        is False
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

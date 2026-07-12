from __future__ import annotations

from typing import Any, Mapping

# Central source of truth for execution-related flags that must remain false in
# review-only / signed-testnet-preparation packages.  Modules may report these
# keys for evidence, but this package must not use them as runtime authority.
EXECUTION_FLAGS: tuple[str, ...] = (
    "binance_reference_branch_runtime_enabled",
    "cross_venue_evidence_import_allowed",
    "runtime_auto_route_allowed",
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
    "runtime_authority_granted",
    "runtime_submit_action_approved",
    "runtime_submit_action_executed",
    "runtime_submit_action_performed",
    "phase9_2_real_submit_authorized",
    "phase9_2_order_submission_authorized",
    "phase9_3_status_polling_may_begin",
    "phase9_4_testnet_reconciliation_may_begin",
    "phase10_signed_testnet_session_validation_may_begin",
    "live_canary_preparation_may_begin",
    "live_read_only_probe_performed",
    "live_key_scope_validation_performed",
    "live_canary_approval_packet_created",
    "secret_manager_runtime_binding_performed",
    "executor_policy_application_performed",
    "endpoint_policy_application_performed",
    "endpoint_policy_changed",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "cancel_request_sent",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "actual_executor_enablement_performed",
    "actual_order_submission_performed",
    "real_testnet_order_endpoint_called",
    "private_account_endpoint_called",
    "balance_endpoint_called",
    "position_endpoint_called",
    "public_metadata_network_probe_performed",
    "public_metadata_network_probe_result_validated",
    "runtime_settings_mutated",
    "score_weights_mutated",
)

# Dotted settings.yaml paths that must stay disabled for the current package.
# Kept centrally so baseline freeze, dashboards, and future status surfaces do
# not drift from one another.
DISABLED_RUNTIME_FLAG_PATHS: tuple[tuple[str, bool], ...] = (
    ("safety.live_trading_enabled", False),
    ("safety.testnet_signed_order_enabled", False),
    ("execution.explicit_signed_testnet_execution_approval_packet.ready_for_signed_testnet_execution", False),
    ("execution.explicit_signed_testnet_execution_approval_packet.testnet_order_submission_allowed", False),
    ("execution.explicit_signed_testnet_execution_approval_packet.external_order_submission_allowed", False),
    ("execution.explicit_signed_testnet_execution_approval_packet.external_order_submission_performed", False),
    ("execution.explicit_signed_testnet_execution_approval_packet.place_order_enabled", False),
    ("execution.explicit_signed_testnet_execution_approval_packet.cancel_order_enabled", False),
    ("execution.explicit_signed_testnet_execution_approval_packet.signed_order_executor_enabled", False),
    ("execution.live_canary_order_executor.live_canary_execution_enabled", False),
    ("execution.live_canary_order_executor.live_order_submission_allowed", False),
    ("execution.live_canary_order_executor.place_order_enabled", False),
    ("execution.live_canary_order_executor.cancel_order_enabled", False),
    ("execution.live_canary_order_executor.external_order_submission_performed", False),
)

PHASE_STATUS_MARKERS: Mapping[str, str] = {
    "p69": "venue_alignment_recovery_execution_frozen",
    "phase9_2": "closed_review_only_no_order_submit",
    "phase9_3": "status_polling_cancel_boundary_no_endpoint_call",
    "phase10": "blocked_until_repeated_clean_signed_testnet_sessions",
    "phase11": "blocked_until_live_read_only_probe_and_separate_canary_approval",
}


def default_execution_flag_state() -> dict[str, bool]:
    return {flag: False for flag in EXECUTION_FLAGS}


def truthy_execution_flags(payload: Mapping[str, Any]) -> list[str]:
    return sorted(flag for flag in EXECUTION_FLAGS if payload.get(flag) is True)

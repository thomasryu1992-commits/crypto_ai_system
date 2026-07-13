from __future__ import annotations

from copy import deepcopy

from crypto_ai_system.execution.disabled_p7_importer_atomic_append_transaction import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_DESIGN_VALID_REVIEW_ONLY_IMPORTER_DISABLED,
    STATUS_READY_REVIEW_ONLY_IMPORTER_DISABLED,
    AtomicAppendTransactionDesignTemplate,
    DisabledP7ImporterInterfaceTemplate,
    TransactionBackendCapabilityEvidenceTemplate,
    build_p55_disabled_p7_importer_atomic_append_transaction_report,
    build_p55_negative_fixture_results,
    build_valid_p55_inputs_fixture,
    validate_atomic_append_dry_run,
    validate_atomic_append_transaction_design,
    validate_backend_capability_evidence,
    validate_disabled_importer_interface,
    validate_p54_source,
)
from crypto_ai_system.utils.audit import sha256_json


def _rehash(payload: dict, key: str) -> None:
    payload[key] = sha256_json({k: v for k, v in payload.items() if k != key})


def test_p55_default_report_is_ready_and_importer_disabled():
    report = build_p55_disabled_p7_importer_atomic_append_transaction_report()
    assert report["status"] == STATUS_READY_REVIEW_ONLY_IMPORTER_DISABLED
    assert report["review_only"] is True
    assert report["design_only"] is True
    assert report["importer_disabled_by_default"] is True
    assert report["p7_importer_enabled"] is False
    assert report["p7_importer_action_allowed"] is False
    assert report["p7_importer_action_executed"] is False
    assert report["current_backend_transaction_ready"] is False
    assert report["actual_p7_import_ready"] is False
    assert report["p7_registry_append_performed_by_p55"] is False
    assert report["p7_valid_status_written_by_p55"] is False
    assert report["runtime_mutation_performed"] is False


def test_p55_valid_fixture_validates_design_but_keeps_importer_disabled():
    inputs = build_valid_p55_inputs_fixture()
    report = build_p55_disabled_p7_importer_atomic_append_transaction_report(**inputs)
    assert report["status"] == STATUS_DESIGN_VALID_REVIEW_ONLY_IMPORTER_DISABLED
    assert report["transaction_design_valid"] is True
    assert report["p7_internal_design_chain_closed_after_p55"] is True
    assert report["current_backend_transaction_ready"] is False
    assert report["current_backend_safe_for_real_p7_import"] is False
    assert report["actual_p7_import_ready"] is False
    assert report["p7_importer_enabled"] is False
    assert report["p7_atomic_transaction_started"] is False
    assert report["p7_atomic_transaction_committed"] is False
    assert report["p7_registry_append_performed_by_p55"] is False
    assert report["p7_import_nonce_consumed_by_p55"] is False
    assert report["p7_duplicate_import_lock_acquired_by_p55"] is False
    assert report["atomic_append_transaction_dry_run"]["status"] == (
        "P55_ATOMIC_APPEND_TRANSACTION_DRY_RUN_VALID_NO_MUTATION"
    )


def test_p55_disabled_importer_interface_has_no_execution_permissions():
    payload = DisabledP7ImporterInterfaceTemplate().to_dict()
    validation = validate_disabled_importer_interface(payload)
    assert validation["disabled_importer_interface_valid"] is True
    assert validation["importer_disabled_by_default"] is True
    assert validation["implementation_included"] is False
    assert payload["can_start_transaction"] is False
    assert payload["can_acquire_duplicate_lock"] is False
    assert payload["can_consume_nonce"] is False
    assert payload["can_append_p7_registry"] is False
    assert payload["can_commit_transaction"] is False


def test_p55_transaction_design_enforces_lock_nonce_append_commit_order():
    payload = AtomicAppendTransactionDesignTemplate().to_dict()
    validation = validate_atomic_append_transaction_design(payload)
    assert validation["atomic_append_transaction_design_valid"] is True
    steps = payload["exact_step_order"]
    assert steps.index("acquire_duplicate_import_lock") < steps.index("consume_one_time_nonce")
    assert steps.index("consume_one_time_nonce") < steps.index("append_exactly_one_p7_record")
    assert steps.index("append_exactly_one_p7_record") < steps.index("commit_atomic_transaction")
    assert payload["rollback_before_commit_required"] is True
    assert payload["partial_commit_allowed"] is False
    assert payload["best_effort_multi_file_write_allowed"] is False


def test_p55_current_jsonl_backend_is_explicitly_not_transaction_ready():
    payload = TransactionBackendCapabilityEvidenceTemplate().to_dict()
    validation = validate_backend_capability_evidence(payload)
    assert validation["backend_capability_evidence_valid"] is True
    assert validation["current_backend_safe_for_real_p7_import"] is False
    assert validation["current_backend_blocks_actual_import"] is True
    assert validation["actual_import_ready"] is False
    assert payload["current_backend_multi_resource_atomic_transaction_supported"] is False
    assert payload["current_backend_transaction_rollback_supported"] is False
    assert payload["current_backend_durable_transaction_journal_supported"] is False


def test_p55_revalidates_p54_report_and_packet():
    inputs = build_valid_p55_inputs_fixture()
    validation = validate_p54_source(inputs["p54_report"])
    assert validation["p54_source_valid_for_p55"] is True
    assert validation["final_guard_packet"] is not None


def test_p55_blocks_importer_enablement_or_append_permission():
    inputs = build_valid_p55_inputs_fixture()
    bad = deepcopy(inputs)
    bad["importer_interface"]["can_enable_importer"] = True
    _rehash(bad["importer_interface"], "p55_disabled_p7_importer_interface_sha256")
    report = build_p55_disabled_p7_importer_atomic_append_transaction_report(**bad)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert any("CAN_ENABLE_IMPORTER_NOT_FALSE" in r for r in report["block_reasons"])

    bad = deepcopy(inputs)
    bad["importer_interface"]["can_append_p7_registry"] = True
    _rehash(bad["importer_interface"], "p55_disabled_p7_importer_interface_sha256")
    report = build_p55_disabled_p7_importer_atomic_append_transaction_report(**bad)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert any("CAN_APPEND_P7_REGISTRY_NOT_FALSE" in r for r in report["block_reasons"])


def test_p55_blocks_invalid_transaction_order_and_missing_rollback():
    inputs = build_valid_p55_inputs_fixture()
    bad = deepcopy(inputs)
    steps = list(bad["transaction_design"]["exact_step_order"])
    lock_idx = steps.index("acquire_duplicate_import_lock")
    nonce_idx = steps.index("consume_one_time_nonce")
    steps[lock_idx], steps[nonce_idx] = steps[nonce_idx], steps[lock_idx]
    bad["transaction_design"]["exact_step_order"] = steps
    _rehash(bad["transaction_design"], "p55_atomic_append_transaction_design_sha256")
    report = build_p55_disabled_p7_importer_atomic_append_transaction_report(**bad)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P55_TRANSACTION_DESIGN_STEP_ORDER_INVALID" in report["block_reasons"]

    bad = deepcopy(inputs)
    bad["transaction_design"]["rollback_before_commit_required"] = False
    _rehash(bad["transaction_design"], "p55_atomic_append_transaction_design_sha256")
    report = build_p55_disabled_p7_importer_atomic_append_transaction_report(**bad)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert any("ROLLBACK_BEFORE_COMMIT_REQUIRED_NOT_TRUE" in r for r in report["block_reasons"])


def test_p55_dry_run_is_simulation_only_with_zero_mutation():
    inputs = build_valid_p55_inputs_fixture()
    report = build_p55_disabled_p7_importer_atomic_append_transaction_report(**inputs)
    dry_run = report["atomic_append_transaction_dry_run"]
    validation = validate_atomic_append_dry_run(dry_run)
    assert validation["atomic_append_dry_run_valid"] is True
    assert validation["transaction_steps_simulated_only"] is True
    assert validation["actual_import_ready"] is False
    assert all(step["simulated_only"] is True for step in dry_run["transaction_steps"])
    assert all(step["performed"] is False for step in dry_run["transaction_steps"])
    assert dry_run["transaction_started"] is False
    assert dry_run["transaction_committed"] is False
    assert dry_run["p7_registry_append_performed"] is False


def test_p55_blocks_false_backend_readiness_and_secret_injection():
    inputs = build_valid_p55_inputs_fixture()
    bad = deepcopy(inputs)
    bad["backend_capability_evidence"]["actual_import_ready"] = True
    _rehash(
        bad["backend_capability_evidence"],
        "p55_transaction_backend_capability_evidence_sha256",
    )
    report = build_p55_disabled_p7_importer_atomic_append_transaction_report(**bad)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert any("ACTUAL_IMPORT_READY_NOT_FALSE" in r for r in report["block_reasons"])

    bad = deepcopy(inputs)
    bad["importer_interface"]["api_secret_value"] = "forbidden"
    _rehash(bad["importer_interface"], "p55_disabled_p7_importer_interface_sha256")
    report = build_p55_disabled_p7_importer_atomic_append_transaction_report(**bad)
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert any("FORBIDDEN_SECRET_OR_RAW_FIELD" in r for r in report["block_reasons"])


def test_p55_negative_fixtures_all_fail_closed():
    result = build_p55_negative_fixture_results()
    assert result["case_count"] == 10
    assert result["all_negative_fixtures_blocked_fail_closed"] is True
    assert result["valid_fixture_transaction_design_valid_importer_disabled"] is True

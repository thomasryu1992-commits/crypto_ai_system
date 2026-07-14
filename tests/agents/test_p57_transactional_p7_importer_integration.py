from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from crypto_ai_system.execution.transactional_evidence_store import (
    DuplicateImportError,
    InjectedTransactionFailure,
    SQLiteTransactionalEvidenceStore,
)
from crypto_ai_system.execution.transactional_p7_importer_integration import (
    STATUS_BLOCKED_FAIL_CLOSED,
    P57ImporterIntegrationRequest,
    TransactionalP7ImporterIntegration,
    TransactionalP7ImporterIntegrationConfig,
    TransactionalP7ImporterIntegrationDisabledError,
    TransactionalP7ImporterIntegrationValidationError,
    build_p57_negative_fixture_results,
    build_p57_transactional_p7_importer_integration_report,
    build_valid_p57_integration_request,
    run_p57_transactional_importer_integration_self_test,
)


def test_p57_valid_integration_commits_exactly_one_transactional_record(tmp_path):
    store = SQLiteTransactionalEvidenceStore(tmp_path / "p57.sqlite3")
    importer = TransactionalP7ImporterIntegration(store)
    receipt = importer.execute_integration_self_test(build_valid_p57_integration_request())
    assert receipt["transaction_committed"] is True
    assert receipt["exactly_one_transactional_record_committed"] is True
    assert receipt["real_p7_import"] is False
    assert receipt["p7_importer_enabled"] is False
    assert store.row_counts() == {
        "import_records": 1,
        "import_locks": 1,
        "consumed_nonces": 1,
        "transaction_receipts": 1,
    }


def test_p57_duplicate_attempt_is_blocked_without_partial_state(tmp_path):
    store = SQLiteTransactionalEvidenceStore(tmp_path / "p57.sqlite3")
    importer = TransactionalP7ImporterIntegration(store)
    request = build_valid_p57_integration_request()
    importer.execute_integration_self_test(request)
    before = store.row_counts()
    with pytest.raises(DuplicateImportError):
        importer.execute_integration_self_test(request)
    assert store.row_counts() == before


@pytest.mark.parametrize("step", ["after_lock", "after_nonce", "after_record", "before_commit"])
def test_p57_injected_failures_roll_back_all_state(tmp_path, step):
    store = SQLiteTransactionalEvidenceStore(tmp_path / f"{step}.sqlite3")
    importer = TransactionalP7ImporterIntegration(store)
    before = store.row_counts()
    with pytest.raises(InjectedTransactionFailure):
        importer.execute_integration_self_test(
            build_valid_p57_integration_request(), fault_injection_step=step
        )
    assert store.row_counts() == before


def test_p57_real_import_path_remains_disabled(tmp_path):
    store = SQLiteTransactionalEvidenceStore(tmp_path / "p57.sqlite3")
    importer = TransactionalP7ImporterIntegration(store)
    request = replace(
        build_valid_p57_integration_request(),
        operation_scope="p7_real_import",
        evidence_origin="real_signed_testnet_external_runtime",
    )
    with pytest.raises(TransactionalP7ImporterIntegrationDisabledError):
        importer.execute_real_import(request)
    assert store.row_counts() == {
        "import_records": 0,
        "import_locks": 0,
        "consumed_nonces": 0,
        "transaction_receipts": 0,
    }


def test_p57_rejects_importer_enablement_attempt(tmp_path):
    store = SQLiteTransactionalEvidenceStore(tmp_path / "p57.sqlite3")
    importer = TransactionalP7ImporterIntegration(
        store,
        config=replace(
            TransactionalP7ImporterIntegrationConfig(), p7_importer_enabled=True
        ),
    )
    with pytest.raises(TransactionalP7ImporterIntegrationValidationError):
        importer.execute_integration_self_test(build_valid_p57_integration_request())
    assert store.row_counts()["import_records"] == 0


def test_p57_rejects_tampered_p54_packet(tmp_path):
    request = build_valid_p57_integration_request()
    payload = deepcopy(request.canonical_payload())
    payload["final_guard_packet"]["candidate_sha256"] = "f" * 64
    tampered = P57ImporterIntegrationRequest(**payload)
    importer = TransactionalP7ImporterIntegration(
        SQLiteTransactionalEvidenceStore(tmp_path / "p57.sqlite3")
    )
    validation = importer.validate_request(tampered)
    assert validation["request_valid"] is False
    assert any("P54_FINAL_GUARD_PACKET_EMBEDDED_SHA256_INVALID" in x for x in validation["request_block_reasons"])


def test_p57_rejects_candidate_hash_mismatch(tmp_path):
    request = build_valid_p57_integration_request()
    payload = deepcopy(request.canonical_payload())
    payload["candidate"]["p7_input_preview"]["client_order_id"] = "mutated"
    mutated = P57ImporterIntegrationRequest(**payload)
    importer = TransactionalP7ImporterIntegration(
        SQLiteTransactionalEvidenceStore(tmp_path / "p57.sqlite3")
    )
    validation = importer.validate_request(mutated)
    assert validation["request_valid"] is False
    assert "P57_CANDIDATE_SHA256_MISMATCH" in validation["request_block_reasons"]


def test_p57_self_test_proves_connected_transactional_path():
    report = run_p57_transactional_importer_integration_self_test()
    assert report["integration_self_test_passed"] is True
    assert report["p54_guard_to_p56_backend_code_path_exercised"] is True
    assert report["commit_test_passed"] is True
    assert report["duplicate_import_blocked"] is True
    assert report["all_injected_failures_rolled_back_without_partial_state"] is True
    assert report["real_p7_import_scope_blocked_by_p57"] is True
    assert report["actual_p7_import_ready"] is False
    assert report["p7_importer_enabled"] is False


def test_p57_negative_fixtures_all_fail_closed():
    report = build_p57_negative_fixture_results()
    assert report["all_negative_fixtures_blocked_fail_closed"] is True
    assert len(report["fixture_results"]) == 10


def test_p57_report_blocks_without_real_evidence_but_keeps_integration_validation():
    report = build_p57_transactional_p7_importer_integration_report()
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert report["blocked"] is True
    assert report["p54_final_guard_connected_to_p56_transaction_backend"] is True
    assert report["transactional_importer_orchestration_implemented"] is True
    assert report["integration_self_test_passed"] is True
    assert report["actual_p7_import_ready"] is False
    assert report["real_signed_testnet_evidence_present"] is False
    assert report["p7_importer_enabled"] is False
    assert report["p7_real_import_executed"] is False
    assert report["runtime_mutation_performed"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["no_additional_p7_review_wrapper_recommended"] is True

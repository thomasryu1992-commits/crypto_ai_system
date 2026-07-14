from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from crypto_ai_system.execution.transactional_evidence_store import (
    STATUS_BLOCKED_FAIL_CLOSED,
    DuplicateImportError,
    EvidenceIntegrityError,
    InjectedTransactionFailure,
    SQLiteTransactionalEvidenceStore,
    TransactionalEvidenceRecordRequest,
    TransactionalEvidenceStoreDisabledError,
    _self_test_request,
    build_p56_transactional_evidence_store_report,
    run_transactional_evidence_store_self_test,
)


def test_p56_self_test_proves_atomic_backend_capabilities():
    report = run_transactional_evidence_store_self_test()
    assert report["backend_self_test_passed"] is True
    assert report["commit_test_passed"] is True
    assert report["duplicate_import_blocked"] is True
    assert report["duplicate_attempt_created_no_partial_state"] is True
    assert report["all_injected_failures_rolled_back_without_partial_state"] is True
    assert report["append_only_update_blocked"] is True
    assert report["append_only_delete_blocked"] is True
    assert report["real_p7_import_scope_blocked_by_p56"] is True
    assert report["runtime_mutation_performed"] is False
    assert report["p7_importer_enabled"] is False
    assert report["actual_p7_import_ready"] is False


def test_p56_capability_snapshot_uses_wal_full_sync_and_foreign_keys(tmp_path):
    store = SQLiteTransactionalEvidenceStore(tmp_path / "store.sqlite3")
    capability = store.capability_snapshot()
    assert capability["journal_mode"] == "WAL"
    assert capability["synchronous_full"] is True
    assert capability["foreign_keys_enabled"] is True
    assert capability["integrity_check_passed"] is True
    assert capability["append_only_triggers_present"] is True
    assert capability["atomic_transaction_supported"] is True
    assert capability["transaction_rollback_supported"] is True
    assert capability["current_backend_transaction_ready"] is True
    assert capability["actual_p7_import_ready"] is False
    assert capability["p7_importer_enabled"] is False


def test_p56_atomic_commit_writes_one_lock_nonce_record_and_receipt(tmp_path):
    store = SQLiteTransactionalEvidenceStore(tmp_path / "store.sqlite3")
    receipt = store._append_self_test_record_atomically(_self_test_request("one"))
    assert receipt["record_id"].startswith("p56_self_test_record_")
    assert len(receipt["record_sha256"]) == 64
    assert store.row_counts() == {
        "import_records": 1,
        "import_locks": 1,
        "consumed_nonces": 1,
        "transaction_receipts": 1,
    }


@pytest.mark.parametrize("step", ["after_lock", "after_nonce", "after_record", "before_commit"])
def test_p56_injected_failures_roll_back_all_state(tmp_path, step):
    store = SQLiteTransactionalEvidenceStore(tmp_path / "store.sqlite3")
    before = store.row_counts()
    with pytest.raises(InjectedTransactionFailure):
        store._append_self_test_record_atomically(
            _self_test_request(step),
            fault_injection_step=step,
        )
    assert store.row_counts() == before


def test_p56_duplicate_identity_is_blocked_without_partial_state(tmp_path):
    store = SQLiteTransactionalEvidenceStore(tmp_path / "store.sqlite3")
    request = _self_test_request("duplicate")
    store._append_self_test_record_atomically(request)
    before = store.row_counts()
    with pytest.raises(DuplicateImportError):
        store._append_self_test_record_atomically(request)
    assert store.row_counts() == before


def test_p56_concurrent_duplicate_attempt_commits_exactly_once(tmp_path):
    store = SQLiteTransactionalEvidenceStore(tmp_path / "store.sqlite3")
    request = _self_test_request("concurrent")

    def attempt() -> str:
        try:
            store._append_self_test_record_atomically(request)
            return "committed"
        except DuplicateImportError:
            return "duplicate"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == ["committed", "duplicate"]
    assert store.row_counts() == {
        "import_records": 1,
        "import_locks": 1,
        "consumed_nonces": 1,
        "transaction_receipts": 1,
    }


def test_p56_append_only_update_and_delete_are_blocked(tmp_path):
    store = SQLiteTransactionalEvidenceStore(tmp_path / "store.sqlite3")
    receipt = store._append_self_test_record_atomically(_self_test_request("append-only"))
    result = store.assert_append_only_guards(receipt["record_id"])
    assert result == {"update_blocked": True, "delete_blocked": True}
    assert store.row_counts()["import_records"] == 1


def test_p56_rejects_real_p7_import_scope(tmp_path):
    store = SQLiteTransactionalEvidenceStore(tmp_path / "store.sqlite3")
    request = replace(_self_test_request("real"), operation_scope="p7_real_import")
    with pytest.raises(TransactionalEvidenceStoreDisabledError):
        store._append_self_test_record_atomically(request)
    assert store.row_counts() == {
        "import_records": 0,
        "import_locks": 0,
        "consumed_nonces": 0,
        "transaction_receipts": 0,
    }


def test_p56_rejects_secret_or_raw_payload_fields(tmp_path):
    store = SQLiteTransactionalEvidenceStore(tmp_path / "store.sqlite3")
    request = _self_test_request("secret")
    bad = TransactionalEvidenceRecordRequest(
        **{
            **request.canonical_payload(),
            "payload": {**dict(request.payload), "api_secret_value": "FORBIDDEN"},
        }
    )
    with pytest.raises(EvidenceIntegrityError):
        store._append_self_test_record_atomically(bad)
    assert store.row_counts()["import_records"] == 0


def test_p56_report_blocks_without_real_evidence_but_keeps_backend_validation():
    report = build_p56_transactional_evidence_store_report()
    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert report["blocked"] is True
    assert report["backend_implementation_added"] is True
    assert report["backend_transaction_ready"] is True
    assert report["backend_atomic_lock_nonce_append_commit_proven"] is True
    assert report["backend_rollback_proven"] is True
    assert report["backend_duplicate_prevention_proven"] is True
    assert report["backend_append_only_guards_proven"] is True
    assert report["backend_self_test_database_persisted"] is False
    assert report["real_signed_testnet_evidence_present"] is False
    assert report["real_p7_import_integrated"] is False
    assert report["actual_p7_import_ready"] is False
    assert report["p7_importer_enabled"] is False
    assert report["p7_importer_action_executed"] is False
    assert report["runtime_mutation_performed"] is False
    assert report["actual_order_submission_performed"] is False

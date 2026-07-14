from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_p7_importer_atomic_append_transaction import (
    P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_VERSION,
    AtomicAppendTransactionDesignTemplate,
    validate_atomic_append_transaction_design,
)
from crypto_ai_system.execution.runtime_disabled_flags import (
    default_execution_flag_state,
    truthy_execution_flags,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P56_TRANSACTIONAL_EVIDENCE_STORE_VERSION = "p56_transactional_evidence_store_v1"
P56_TRANSACTIONAL_EVIDENCE_STORE_REGISTRY_NAME = "p56_transactional_evidence_store_registry"
P56_SCHEMA_VERSION = "p56_sqlite_transactional_evidence_store_schema_v1"

STATUS_BACKEND_VALIDATED_REVIEW_ONLY_IMPORTER_DISABLED = (
    "P56_TRANSACTIONAL_EVIDENCE_STORE_BACKEND_VALIDATED_REVIEW_ONLY_IMPORTER_DISABLED"
)
STATUS_BLOCKED_FAIL_CLOSED = "P56_TRANSACTIONAL_EVIDENCE_STORE_BLOCKED_FAIL_CLOSED"

_ALLOWED_BACKEND = "sqlite_wal_full_sync_local"
_ALLOWED_SCOPE = "p56_backend_self_test"
_ALLOWED_RECORD_ARTIFACT_TYPE = "p56_transactional_evidence_store_self_test_record"
_P57_INTEGRATION_SCOPE = "p57_transactional_p7_importer_integration_self_test"
_P57_INTEGRATION_RECORD_ARTIFACT_TYPE = "p57_transactional_p7_importer_integration_self_test_record"

_FORBIDDEN_FIELD_TOKENS = (
    "api_key_value",
    "api_secret_value",
    "secret_value",
    "private_key",
    "passphrase",
    "raw_signed_payload",
    "raw_request_body",
    "raw_exchange_payload",
    "unredacted_exchange_response",
)


class TransactionalEvidenceStoreError(RuntimeError):
    """Base fail-closed error for the P56 transactional evidence store."""


class TransactionalEvidenceStoreDisabledError(TransactionalEvidenceStoreError):
    """Raised when a caller attempts a non-self-test import through P56."""


class DuplicateImportError(TransactionalEvidenceStoreError):
    """Raised when a candidate/order/idempotency/lock key already exists."""


class NonceAlreadyConsumedError(TransactionalEvidenceStoreError):
    """Raised when a one-time nonce was already committed."""


class EvidenceIntegrityError(TransactionalEvidenceStoreError):
    """Raised when hash, scope, or payload integrity is invalid."""


class InjectedTransactionFailure(TransactionalEvidenceStoreError):
    """Used only by backend self-tests to prove rollback behavior."""


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _storage_dir(cfg: AppConfig, rel: str) -> Path:
    path = cfg.root / rel
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _read_latest_json(cfg: AppConfig, filename: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / filename, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _is_sha256_hex(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _walk_forbidden(obj: Any, *, prefix: str = "") -> list[str]:
    blockers: list[str] = []
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            key_l = str(key).lower()
            if any(token in key_l for token in _FORBIDDEN_FIELD_TOKENS):
                safe_boolean = isinstance(value, bool) and any(
                    marker in key_l
                    for marker in ("_included", "_accessed", "_logged", "_created", "_performed")
                )
                if not safe_boolean:
                    blockers.append(f"P56_FORBIDDEN_SECRET_OR_RAW_FIELD:{child}")
            blockers.extend(_walk_forbidden(value, prefix=child))
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        for idx, value in enumerate(obj):
            blockers.extend(_walk_forbidden(value, prefix=f"{prefix}[{idx}]"))
    return blockers


def _execution_false_payload() -> dict[str, bool]:
    payload = default_execution_flag_state()
    payload.update(
        {
            "actual_order_submission_performed": False,
            "actual_testnet_order_submitted": False,
            "actual_live_order_submitted": False,
            "external_order_submission_performed": False,
            "order_endpoint_called": False,
            "order_status_endpoint_called": False,
            "cancel_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "secret_value_accessed": False,
            "secret_value_logged": False,
            "runtime_scheduler_enabled": False,
            "runtime_loop_started": False,
            "runtime_authority_granted": False,
            "runtime_mutation_performed": False,
            "p7_importer_enabled": False,
            "p7_importer_action_allowed": False,
            "p7_importer_action_executed": False,
            "p7_valid_status_written_by_p56": False,
            "p7_report_persisted_by_p56": False,
            "p7_runtime_registry_append_performed_by_p56": False,
            "p7_runtime_nonce_consumed_by_p56": False,
            "p7_runtime_duplicate_lock_acquired_by_p56": False,
            "p7_runtime_transaction_started_by_p56": False,
            "p7_runtime_transaction_committed_by_p56": False,
            "p8_repeated_session_candidate_created": False,
            "signed_testnet_promotion_allowed": False,
            "live_canary_execution_enabled": False,
            "live_scaled_execution_enabled": False,
        }
    )
    return payload


@dataclass(frozen=True)
class TransactionalEvidenceStoreConfig:
    backend_name: str = _ALLOWED_BACKEND
    schema_version: str = P56_SCHEMA_VERSION
    journal_mode: str = "WAL"
    synchronous_mode: str = "FULL"
    foreign_keys_enabled: bool = True
    busy_timeout_ms: int = 5000
    begin_mode: str = "IMMEDIATE"
    append_only_triggers_required: bool = True
    unique_candidate_required: bool = True
    unique_exchange_order_required: bool = True
    unique_client_order_required: bool = True
    unique_idempotency_key_required: bool = True
    unique_nonce_required: bool = True
    unique_lock_key_required: bool = True
    committed_receipt_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p56_transactional_evidence_store_config_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class TransactionalEvidenceRecordRequest:
    operation_scope: str
    artifact_type: str
    candidate_sha256: str
    exchange_order_id: str
    client_order_id: str
    idempotency_key: str
    one_time_nonce_sha256: str
    p7_input_preview_sha256: str
    payload: Mapping[str, Any]
    created_at_utc: str = field(default_factory=utc_now_canonical)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "operation_scope": self.operation_scope,
            "artifact_type": self.artifact_type,
            "candidate_sha256": self.candidate_sha256,
            "exchange_order_id": self.exchange_order_id,
            "client_order_id": self.client_order_id,
            "idempotency_key": self.idempotency_key,
            "one_time_nonce_sha256": self.one_time_nonce_sha256,
            "p7_input_preview_sha256": self.p7_input_preview_sha256,
            "payload": dict(self.payload),
            "created_at_utc": self.created_at_utc,
        }


class SQLiteTransactionalEvidenceStore:
    """SQLite ACID backend for atomic lock + nonce + append + receipt.

    P56 exposes only an ephemeral backend self-test operation. It deliberately
    rejects real P7 import scope, so this backend cannot become runtime authority
    merely because its storage capabilities validate.
    """

    def __init__(self, db_path: str | Path, *, config: TransactionalEvidenceStoreConfig | None = None):
        self.db_path = Path(db_path)
        self.config = config or TransactionalEvidenceStoreConfig()
        self._schema_lock = threading.Lock()
        self._schema_initialized = False

    def _connect(self, *, configure_journal: bool = False) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=max(1.0, self.config.busy_timeout_ms / 1000),
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {int(self.config.busy_timeout_ms)}")
        if configure_journal:
            conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = FULL")
        return conn

    def initialize_schema(self) -> None:
        if self._schema_initialized:
            return
        schema = """
        CREATE TABLE IF NOT EXISTS p56_store_metadata (
            schema_version TEXT PRIMARY KEY,
            backend_name TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS p56_import_records (
            record_id TEXT PRIMARY KEY,
            transaction_id TEXT NOT NULL UNIQUE,
            candidate_sha256 TEXT NOT NULL UNIQUE,
            exchange_order_id TEXT NOT NULL UNIQUE,
            client_order_id TEXT NOT NULL UNIQUE,
            idempotency_key TEXT NOT NULL UNIQUE,
            p7_input_preview_sha256 TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            operation_scope TEXT NOT NULL,
            record_payload_json TEXT NOT NULL,
            record_sha256 TEXT NOT NULL UNIQUE,
            created_at_utc TEXT NOT NULL,
            committed_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS p56_import_locks (
            lock_key_sha256 TEXT PRIMARY KEY,
            candidate_sha256 TEXT NOT NULL UNIQUE,
            exchange_order_id TEXT NOT NULL UNIQUE,
            client_order_id TEXT NOT NULL UNIQUE,
            idempotency_key TEXT NOT NULL UNIQUE,
            import_record_id TEXT NOT NULL UNIQUE,
            acquired_at_utc TEXT NOT NULL,
            FOREIGN KEY(import_record_id) REFERENCES p56_import_records(record_id)
                DEFERRABLE INITIALLY DEFERRED
        );

        CREATE TABLE IF NOT EXISTS p56_consumed_nonces (
            nonce_sha256 TEXT PRIMARY KEY,
            import_record_id TEXT NOT NULL UNIQUE,
            consumed_at_utc TEXT NOT NULL,
            FOREIGN KEY(import_record_id) REFERENCES p56_import_records(record_id)
                DEFERRABLE INITIALLY DEFERRED
        );

        CREATE TABLE IF NOT EXISTS p56_transaction_receipts (
            transaction_id TEXT PRIMARY KEY,
            import_record_id TEXT NOT NULL UNIQUE,
            lock_key_sha256 TEXT NOT NULL UNIQUE,
            nonce_sha256 TEXT NOT NULL UNIQUE,
            record_sha256 TEXT NOT NULL UNIQUE,
            receipt_sha256 TEXT NOT NULL UNIQUE,
            committed_at_utc TEXT NOT NULL,
            FOREIGN KEY(import_record_id) REFERENCES p56_import_records(record_id)
                DEFERRABLE INITIALLY DEFERRED,
            FOREIGN KEY(lock_key_sha256) REFERENCES p56_import_locks(lock_key_sha256)
                DEFERRABLE INITIALLY DEFERRED,
            FOREIGN KEY(nonce_sha256) REFERENCES p56_consumed_nonces(nonce_sha256)
                DEFERRABLE INITIALLY DEFERRED
        );
        """
        with self._schema_lock:
            if self._schema_initialized:
                return
            with self._connect(configure_journal=True) as conn:
                conn.executescript(schema)
                conn.execute(
                    "INSERT OR IGNORE INTO p56_store_metadata(schema_version, backend_name, created_at_utc) "
                    "VALUES (?, ?, ?)",
                    (self.config.schema_version, self.config.backend_name, utc_now_canonical()),
                )
                for table in (
                    "p56_import_records",
                    "p56_import_locks",
                    "p56_consumed_nonces",
                    "p56_transaction_receipts",
                ):
                    conn.execute(
                        f"CREATE TRIGGER IF NOT EXISTS {table}_block_update "
                        f"BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, 'P56_APPEND_ONLY_UPDATE_BLOCKED'); END"
                    )
                    conn.execute(
                        f"CREATE TRIGGER IF NOT EXISTS {table}_block_delete "
                        f"BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, 'P56_APPEND_ONLY_DELETE_BLOCKED'); END"
                    )
            self._schema_initialized = True

    def capability_snapshot(self) -> dict[str, Any]:
        self.initialize_schema()
        with self._connect() as conn:
            journal_mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).upper()
            synchronous_value = int(conn.execute("PRAGMA synchronous").fetchone()[0])
            foreign_keys_value = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
            integrity_check = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
            triggers = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'p56_%_block_%'"
                ).fetchall()
            }
        required_triggers = {
            f"{table}_block_{verb}"
            for table in (
                "p56_import_records",
                "p56_import_locks",
                "p56_consumed_nonces",
                "p56_transaction_receipts",
            )
            for verb in ("update", "delete")
        }
        payload = {
            "artifact_type": "p56_transactional_evidence_store_capability_snapshot",
            "p56_version": P56_TRANSACTIONAL_EVIDENCE_STORE_VERSION,
            "backend_name": self.config.backend_name,
            "schema_version": self.config.schema_version,
            "sqlite_version": sqlite3.sqlite_version,
            "journal_mode": journal_mode,
            "synchronous_value": synchronous_value,
            "synchronous_full": synchronous_value == 2,
            "foreign_keys_enabled": foreign_keys_value == 1,
            "integrity_check": integrity_check,
            "integrity_check_passed": integrity_check.lower() == "ok",
            "begin_immediate_supported": True,
            "atomic_transaction_supported": True,
            "transaction_rollback_supported": True,
            "durable_wal_journal_supported": journal_mode == "WAL",
            "compare_and_set_equivalent_supported": True,
            "duplicate_lock_enforced_by_unique_constraints": True,
            "nonce_uniqueness_enforced_by_primary_key": True,
            "append_only_triggers_present": required_triggers.issubset(triggers),
            "append_only_trigger_count": len(required_triggers.intersection(triggers)),
            "required_append_only_trigger_count": len(required_triggers),
            "current_backend_transaction_ready": (
                journal_mode == "WAL"
                and synchronous_value == 2
                and foreign_keys_value == 1
                and integrity_check.lower() == "ok"
                and required_triggers.issubset(triggers)
            ),
            "actual_p7_import_ready": False,
            "p7_importer_enabled": False,
            "runtime_authority_source": False,
            "created_at_utc": utc_now_canonical(),
        }
        payload["p56_capability_snapshot_sha256"] = sha256_json(payload)
        return payload

    @staticmethod
    def _validate_request(request: TransactionalEvidenceRecordRequest) -> None:
        allowed_pairs = {
            (_ALLOWED_SCOPE, _ALLOWED_RECORD_ARTIFACT_TYPE),
            (_P57_INTEGRATION_SCOPE, _P57_INTEGRATION_RECORD_ARTIFACT_TYPE),
        }
        if (request.operation_scope, request.artifact_type) not in allowed_pairs:
            raise TransactionalEvidenceStoreDisabledError(
                "P56_REAL_P7_IMPORT_DISABLED_ONLY_EXPLICIT_SELF_TEST_SCOPES_ALLOWED"
            )
        for field_name in (
            "candidate_sha256",
            "one_time_nonce_sha256",
            "p7_input_preview_sha256",
        ):
            if not _is_sha256_hex(getattr(request, field_name)):
                raise EvidenceIntegrityError(f"P56_{field_name.upper()}_INVALID")
        for field_name in ("exchange_order_id", "client_order_id", "idempotency_key"):
            value = str(getattr(request, field_name) or "").strip()
            if not value:
                raise EvidenceIntegrityError(f"P56_{field_name.upper()}_MISSING")
        forbidden = _walk_forbidden(request.canonical_payload())
        if forbidden:
            raise EvidenceIntegrityError(";".join(sorted(dict.fromkeys(forbidden))))

    @staticmethod
    def _lock_key(request: TransactionalEvidenceRecordRequest) -> str:
        return sha256_json(
            {
                "candidate_sha256": request.candidate_sha256,
                "exchange_order_id": request.exchange_order_id,
                "client_order_id": request.client_order_id,
                "idempotency_key": request.idempotency_key,
            }
        )

    def _append_self_test_record_atomically(
        self,
        request: TransactionalEvidenceRecordRequest,
        *,
        fault_injection_step: str | None = None,
    ) -> dict[str, Any]:
        self._validate_request(request)
        self.initialize_schema()
        lock_key = self._lock_key(request)
        committed_at = utc_now_canonical()
        canonical = request.canonical_payload()
        record_prefix = (
            "p57_integration_record"
            if request.operation_scope == _P57_INTEGRATION_SCOPE
            else "p56_self_test_record"
        )
        transaction_prefix = (
            "p57_integration_tx"
            if request.operation_scope == _P57_INTEGRATION_SCOPE
            else "p56_tx"
        )
        record_id = stable_id(record_prefix, canonical, 24)
        transaction_id = stable_id(
            transaction_prefix,
            {
                "record_id": record_id,
                "nonce": request.one_time_nonce_sha256,
                "lock": lock_key,
            },
            24,
        )
        immutable_record = {
            **canonical,
            "record_id": record_id,
            "transaction_id": transaction_id,
            "lock_key_sha256": lock_key,
            "committed_at_utc": committed_at,
        }
        record_sha256 = sha256_json(immutable_record)
        receipt = {
            "transaction_id": transaction_id,
            "record_id": record_id,
            "lock_key_sha256": lock_key,
            "nonce_sha256": request.one_time_nonce_sha256,
            "record_sha256": record_sha256,
            "committed_at_utc": committed_at,
        }
        receipt_sha256 = sha256_json(receipt)

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "INSERT INTO p56_import_locks(" 
                    "lock_key_sha256, candidate_sha256, exchange_order_id, client_order_id, "
                    "idempotency_key, import_record_id, acquired_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        lock_key,
                        request.candidate_sha256,
                        request.exchange_order_id,
                        request.client_order_id,
                        request.idempotency_key,
                        record_id,
                        committed_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateImportError("P56_DUPLICATE_IMPORT_LOCK_OR_IDENTITY") from exc
            if fault_injection_step == "after_lock":
                raise InjectedTransactionFailure("P56_INJECTED_FAILURE_AFTER_LOCK")

            try:
                conn.execute(
                    "INSERT INTO p56_consumed_nonces(nonce_sha256, import_record_id, consumed_at_utc) "
                    "VALUES (?, ?, ?)",
                    (request.one_time_nonce_sha256, record_id, committed_at),
                )
            except sqlite3.IntegrityError as exc:
                raise NonceAlreadyConsumedError("P56_ONE_TIME_NONCE_ALREADY_CONSUMED") from exc
            if fault_injection_step == "after_nonce":
                raise InjectedTransactionFailure("P56_INJECTED_FAILURE_AFTER_NONCE")

            conn.execute(
                "INSERT INTO p56_import_records(" 
                "record_id, transaction_id, candidate_sha256, exchange_order_id, client_order_id, "
                "idempotency_key, p7_input_preview_sha256, artifact_type, operation_scope, "
                "record_payload_json, record_sha256, created_at_utc, committed_at_utc) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record_id,
                    transaction_id,
                    request.candidate_sha256,
                    request.exchange_order_id,
                    request.client_order_id,
                    request.idempotency_key,
                    request.p7_input_preview_sha256,
                    request.artifact_type,
                    request.operation_scope,
                    json.dumps(immutable_record, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    record_sha256,
                    request.created_at_utc,
                    committed_at,
                ),
            )
            if fault_injection_step == "after_record":
                raise InjectedTransactionFailure("P56_INJECTED_FAILURE_AFTER_RECORD")

            conn.execute(
                "INSERT INTO p56_transaction_receipts(" 
                "transaction_id, import_record_id, lock_key_sha256, nonce_sha256, record_sha256, "
                "receipt_sha256, committed_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    transaction_id,
                    record_id,
                    lock_key,
                    request.one_time_nonce_sha256,
                    record_sha256,
                    receipt_sha256,
                    committed_at,
                ),
            )
            if fault_injection_step == "before_commit":
                raise InjectedTransactionFailure("P56_INJECTED_FAILURE_BEFORE_COMMIT")

            row = conn.execute(
                "SELECT record_sha256 FROM p56_import_records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            if row is None or row["record_sha256"] != record_sha256:
                raise EvidenceIntegrityError("P56_RECORD_VERIFICATION_FAILED_BEFORE_COMMIT")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return {
            "record_id": record_id,
            "transaction_id": transaction_id,
            "lock_key_sha256": lock_key,
            "nonce_sha256": request.one_time_nonce_sha256,
            "record_sha256": record_sha256,
            "receipt_sha256": receipt_sha256,
            "committed_at_utc": committed_at,
        }


    def _append_integration_test_record_atomically(
        self,
        request: TransactionalEvidenceRecordRequest,
        *,
        fault_injection_step: str | None = None,
    ) -> dict[str, Any]:
        """Run the P57 importer integration through the same ACID backend.

        This method accepts only the explicit P57 integration-self-test scope.
        Real P7 import remains rejected by the shared request validator.
        """
        if (
            request.operation_scope != _P57_INTEGRATION_SCOPE
            or request.artifact_type != _P57_INTEGRATION_RECORD_ARTIFACT_TYPE
        ):
            raise TransactionalEvidenceStoreDisabledError(
                "P56_P57_INTEGRATION_METHOD_ONLY_ACCEPTS_P57_SELF_TEST_SCOPE"
            )
        return self._append_self_test_record_atomically(
            request,
            fault_injection_step=fault_injection_step,
        )

    def row_counts(self) -> dict[str, int]:
        self.initialize_schema()
        with self._connect() as conn:
            return {
                "import_records": int(conn.execute("SELECT COUNT(*) FROM p56_import_records").fetchone()[0]),
                "import_locks": int(conn.execute("SELECT COUNT(*) FROM p56_import_locks").fetchone()[0]),
                "consumed_nonces": int(conn.execute("SELECT COUNT(*) FROM p56_consumed_nonces").fetchone()[0]),
                "transaction_receipts": int(
                    conn.execute("SELECT COUNT(*) FROM p56_transaction_receipts").fetchone()[0]
                ),
            }

    def assert_append_only_guards(self, record_id: str) -> dict[str, bool]:
        update_blocked = False
        delete_blocked = False
        with self._connect() as conn:
            try:
                conn.execute("UPDATE p56_import_records SET exchange_order_id = exchange_order_id WHERE record_id = ?", (record_id,))
            except sqlite3.DatabaseError as exc:
                update_blocked = "P56_APPEND_ONLY_UPDATE_BLOCKED" in str(exc)
            try:
                conn.execute("DELETE FROM p56_import_records WHERE record_id = ?", (record_id,))
            except sqlite3.DatabaseError as exc:
                delete_blocked = "P56_APPEND_ONLY_DELETE_BLOCKED" in str(exc)
        return {"update_blocked": update_blocked, "delete_blocked": delete_blocked}


def _self_test_request(seed: str) -> TransactionalEvidenceRecordRequest:
    return TransactionalEvidenceRecordRequest(
        operation_scope=_ALLOWED_SCOPE,
        artifact_type=_ALLOWED_RECORD_ARTIFACT_TYPE,
        candidate_sha256=sha256_json({"seed": seed, "kind": "candidate"}),
        exchange_order_id=f"P56-SELFTEST-EXCHANGE-{seed}",
        client_order_id=f"P56-SELFTEST-CLIENT-{seed}",
        idempotency_key=f"P56-SELFTEST-IDEMPOTENCY-{seed}",
        one_time_nonce_sha256=sha256_json({"seed": seed, "kind": "nonce"}),
        p7_input_preview_sha256=sha256_json({"seed": seed, "kind": "p7_preview"}),
        payload={
            "artifact_type": _ALLOWED_RECORD_ARTIFACT_TYPE,
            "self_test_seed": seed,
            "redacted_metadata_only": True,
            "contains_real_exchange_evidence": False,
            "runtime_authority": False,
        },
    )


def run_transactional_evidence_store_self_test() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="cas_p56_store_self_test_") as tmp:
        db_path = Path(tmp) / "p56_transactional_evidence_store_self_test.sqlite3"
        store = SQLiteTransactionalEvidenceStore(db_path)
        capability = store.capability_snapshot()

        committed = store._append_self_test_record_atomically(_self_test_request("commit"))
        counts_after_commit = store.row_counts()
        append_only = store.assert_append_only_guards(committed["record_id"])

        duplicate_blocked = False
        try:
            store._append_self_test_record_atomically(_self_test_request("commit"))
        except DuplicateImportError:
            duplicate_blocked = True
        counts_after_duplicate = store.row_counts()

        rollback_results: dict[str, Any] = {}
        for step in ("after_lock", "after_nonce", "after_record", "before_commit"):
            before = store.row_counts()
            blocked = False
            try:
                store._append_self_test_record_atomically(
                    _self_test_request(f"rollback-{step}"),
                    fault_injection_step=step,
                )
            except InjectedTransactionFailure:
                blocked = True
            after = store.row_counts()
            rollback_results[step] = {
                "injected_failure_observed": blocked,
                "row_counts_before": before,
                "row_counts_after": after,
                "no_partial_state_published": before == after,
            }

        real_scope_blocked = False
        bad_request = _self_test_request("real-scope-block")
        bad_request = TransactionalEvidenceRecordRequest(
            **{**bad_request.canonical_payload(), "operation_scope": "p7_real_import"}
        )
        try:
            store._append_self_test_record_atomically(bad_request)
        except TransactionalEvidenceStoreDisabledError:
            real_scope_blocked = True

        final_counts = store.row_counts()
        payload = {
            "artifact_type": "p56_transactional_evidence_store_self_test_report",
            "p56_version": P56_TRANSACTIONAL_EVIDENCE_STORE_VERSION,
            "backend_name": _ALLOWED_BACKEND,
            "ephemeral_database_used": True,
            "ephemeral_database_deleted_after_test": True,
            "capability_snapshot": capability,
            "commit_test_passed": counts_after_commit == {
                "import_records": 1,
                "import_locks": 1,
                "consumed_nonces": 1,
                "transaction_receipts": 1,
            },
            "commit_receipt": committed,
            "duplicate_import_blocked": duplicate_blocked,
            "duplicate_attempt_created_no_partial_state": counts_after_duplicate == counts_after_commit,
            "rollback_results": rollback_results,
            "all_injected_failures_rolled_back_without_partial_state": all(
                result["injected_failure_observed"] and result["no_partial_state_published"]
                for result in rollback_results.values()
            ),
            "append_only_update_blocked": append_only["update_blocked"],
            "append_only_delete_blocked": append_only["delete_blocked"],
            "real_p7_import_scope_blocked_by_p56": real_scope_blocked,
            "final_row_counts": final_counts,
            "backend_self_test_passed": (
                capability["current_backend_transaction_ready"]
                and counts_after_commit
                == {
                    "import_records": 1,
                    "import_locks": 1,
                    "consumed_nonces": 1,
                    "transaction_receipts": 1,
                }
                and duplicate_blocked
                and counts_after_duplicate == counts_after_commit
                and all(
                    result["injected_failure_observed"] and result["no_partial_state_published"]
                    for result in rollback_results.values()
                )
                and append_only["update_blocked"]
                and append_only["delete_blocked"]
                and real_scope_blocked
            ),
            "runtime_mutation_performed": False,
            "p7_importer_enabled": False,
            "actual_p7_import_ready": False,
            "created_at_utc": utc_now_canonical(),
        }
        payload["p56_self_test_report_sha256"] = sha256_json(payload)
        return payload


def build_p56_transactional_evidence_store_report(
    *,
    cfg: AppConfig | None = None,
    self_test_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    p55_report = _read_latest_json(
        cfg, "p55_disabled_p7_importer_atomic_append_transaction_report.json"
    )
    p55_design = AtomicAppendTransactionDesignTemplate().to_dict()
    p55_design_validation = validate_atomic_append_transaction_design(p55_design)
    self_test = dict(self_test_report or run_transactional_evidence_store_self_test())
    blockers: list[str] = []

    if not p55_report:
        blockers.append("P56_P55_REPORT_MISSING")
    if p55_report and p55_report.get("p7_importer_enabled") is not False:
        blockers.append("P56_P55_IMPORTER_NOT_DISABLED")
    if p55_report and p55_report.get("actual_p7_import_ready") is not False:
        blockers.append("P56_P55_ACTUAL_IMPORT_READY_NOT_FALSE")
    if p55_report.get("p55_version") not in {
        None,
        P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_VERSION,
    }:
        blockers.append("P56_P55_VERSION_INVALID")
    if not p55_design_validation.get("atomic_append_transaction_design_valid"):
        blockers.extend(p55_design_validation.get("atomic_append_transaction_design_block_reasons", []))
    if not self_test.get("backend_self_test_passed"):
        blockers.append("P56_BACKEND_SELF_TEST_FAILED")
    capability = dict(self_test.get("capability_snapshot") or {})
    if not capability.get("current_backend_transaction_ready"):
        blockers.append("P56_SQLITE_BACKEND_NOT_TRANSACTION_READY")
    if self_test.get("real_p7_import_scope_blocked_by_p56") is not True:
        blockers.append("P56_REAL_P7_IMPORT_SCOPE_NOT_BLOCKED")
    if self_test.get("runtime_mutation_performed") is not False:
        blockers.append("P56_RUNTIME_MUTATION_PERFORMED")
    blockers.extend(_walk_forbidden(self_test))

    flags = _execution_false_payload()
    enabled = truthy_execution_flags(flags)
    if enabled:
        blockers.append("P56_EXECUTION_FLAGS_TRUE:" + ",".join(sorted(enabled)))

    status = (
        STATUS_BACKEND_VALIDATED_REVIEW_ONLY_IMPORTER_DISABLED
        if not blockers
        else STATUS_BLOCKED_FAIL_CLOSED
    )
    created_at = utc_now_canonical()
    report = {
        "artifact_type": "p56_transactional_evidence_store_report",
        "p56_version": P56_TRANSACTIONAL_EVIDENCE_STORE_VERSION,
        "p56_transactional_evidence_store_id": stable_id(
            "p56_transactional_evidence_store",
            {
                "p55_sha256": p55_report.get(
                    "p55_disabled_p7_importer_atomic_append_transaction_sha256"
                ),
                "self_test_sha256": self_test.get("p56_self_test_report_sha256"),
                "created_at_utc": created_at,
            },
            24,
        ),
        "status": status,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "review_only": True,
        "backend_implementation_added": True,
        "backend_self_test_only": True,
        "backend_name": _ALLOWED_BACKEND,
        "backend_transaction_ready": bool(
            not blockers and capability.get("current_backend_transaction_ready")
        ),
        "backend_atomic_lock_nonce_append_commit_proven": bool(
            not blockers and self_test.get("backend_self_test_passed")
        ),
        "backend_rollback_proven": bool(
            not blockers
            and self_test.get("all_injected_failures_rolled_back_without_partial_state")
        ),
        "backend_duplicate_prevention_proven": bool(
            not blockers and self_test.get("duplicate_import_blocked")
        ),
        "backend_append_only_guards_proven": bool(
            not blockers
            and self_test.get("append_only_update_blocked")
            and self_test.get("append_only_delete_blocked")
        ),
        "backend_self_test_ephemeral": True,
        "backend_self_test_database_persisted": False,
        "real_signed_testnet_evidence_present": False,
        "real_p7_import_integrated": False,
        "actual_p7_import_ready": False,
        "p7_importer_enabled": False,
        "p7_importer_action_allowed": False,
        "p7_importer_action_executed": False,
        "p7_internal_review_wrapper_expansion_stopped_after_p55": True,
        "next_progress_gate": "ONE_REAL_REDACTED_SIGNED_TESTNET_EVIDENCE_BUNDLE_AND_SEPARATE_IMPORT_APPROVAL",
        "p55_source_status": p55_report.get("status"),
        "p55_source_sha256": p55_report.get(
            "p55_disabled_p7_importer_atomic_append_transaction_sha256"
        ),
        "p55_transaction_design_validation": p55_design_validation,
        "transactional_store_capability_snapshot": capability,
        "transactional_store_self_test": self_test,
        **flags,
        "created_at_utc": created_at,
    }
    report["p56_transactional_evidence_store_sha256"] = sha256_json(report)
    return report


def persist_p56_transactional_evidence_store(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    self_test = run_transactional_evidence_store_self_test()
    report = build_p56_transactional_evidence_store_report(cfg=cfg, self_test_report=self_test)
    capability = dict(self_test["capability_snapshot"])

    config_template = TransactionalEvidenceStoreConfig().to_dict()
    future_runtime_template = {
        "artifact_type": "p56_future_runtime_transactional_evidence_store_config_TEMPLATE_DISABLED",
        "p56_version": P56_TRANSACTIONAL_EVIDENCE_STORE_VERSION,
        "review_only": True,
        "runtime_use_enabled": False,
        "p7_importer_enabled": False,
        "database_path": "OPERATOR_SUPPLIED_LOCAL_RUNTIME_PATH_REQUIRED",
        "backend_name": _ALLOWED_BACKEND,
        "journal_mode": "WAL",
        "synchronous_mode": "FULL",
        "foreign_keys_enabled": True,
        "begin_mode": "IMMEDIATE",
        "real_signed_testnet_evidence_required": True,
        "separate_operator_import_approval_required": True,
        "fresh_p54_final_guard_required": True,
        "no_secret_evidence_required": True,
        "duplicate_lock_nonce_append_receipt_single_transaction_required": True,
        "runtime_authority_source": False,
        **_execution_false_payload(),
    }
    future_runtime_template[
        "p56_future_runtime_transactional_evidence_store_config_sha256"
    ] = sha256_json(future_runtime_template)

    registry_record = {
        "artifact_type": "p56_transactional_evidence_store_registry_record",
        "p56_transactional_evidence_store_id": report["p56_transactional_evidence_store_id"],
        "p56_transactional_evidence_store_sha256": report[
            "p56_transactional_evidence_store_sha256"
        ],
        "status": report["status"],
        "review_only": True,
        "backend_transaction_ready": report["backend_transaction_ready"],
        "backend_self_test_only": True,
        "actual_p7_import_ready": False,
        "p7_importer_enabled": False,
        "created_at_utc": report["created_at_utc"],
    }
    registry_record["p56_registry_record_sha256"] = sha256_json(registry_record)
    append_registry_record(
        registry_path(cfg, P56_TRANSACTIONAL_EVIDENCE_STORE_REGISTRY_NAME),
        registry_record,
        registry_name=P56_TRANSACTIONAL_EVIDENCE_STORE_REGISTRY_NAME,
    )

    summary = {
        "artifact_type": "p56_transactional_evidence_store_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "review_only": True,
        "backend_implementation_added": True,
        "backend_transaction_ready": report["backend_transaction_ready"],
        "backend_atomic_lock_nonce_append_commit_proven": report[
            "backend_atomic_lock_nonce_append_commit_proven"
        ],
        "backend_rollback_proven": report["backend_rollback_proven"],
        "backend_duplicate_prevention_proven": report[
            "backend_duplicate_prevention_proven"
        ],
        "backend_append_only_guards_proven": report["backend_append_only_guards_proven"],
        "backend_self_test_ephemeral": True,
        "real_signed_testnet_evidence_present": False,
        "real_p7_import_integrated": False,
        "actual_p7_import_ready": False,
        "p7_importer_enabled": False,
        "next_progress_gate": report["next_progress_gate"],
        "p56_transactional_evidence_store_id": report["p56_transactional_evidence_store_id"],
        "p56_transactional_evidence_store_sha256": report[
            "p56_transactional_evidence_store_sha256"
        ],
        "created_at_utc": report["created_at_utc"],
    }
    summary["p56_summary_sha256"] = sha256_json(summary)

    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p56_transactional_evidence_store")
    writes = {
        "p56_transactional_evidence_store_report.json": report,
        "p56_transactional_evidence_store_config.json": config_template,
        "p56_transactional_evidence_store_capability_snapshot.json": capability,
        "p56_transactional_evidence_store_self_test_report.json": self_test,
        "p56_future_runtime_transactional_evidence_store_config_TEMPLATE_DISABLED.json": future_runtime_template,
        "p56_transactional_evidence_store_registry_record.json": registry_record,
        "p56_transactional_evidence_store_summary.json": summary,
    }
    for filename, payload in writes.items():
        atomic_write_json(latest / filename, payload)
        atomic_write_json(storage / filename, payload)
    return report


__all__ = [
    "P56_TRANSACTIONAL_EVIDENCE_STORE_VERSION",
    "STATUS_BACKEND_VALIDATED_REVIEW_ONLY_IMPORTER_DISABLED",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "TransactionalEvidenceStoreError",
    "TransactionalEvidenceStoreDisabledError",
    "DuplicateImportError",
    "NonceAlreadyConsumedError",
    "EvidenceIntegrityError",
    "InjectedTransactionFailure",
    "TransactionalEvidenceStoreConfig",
    "TransactionalEvidenceRecordRequest",
    "SQLiteTransactionalEvidenceStore",
    "run_transactional_evidence_store_self_test",
    "build_p56_transactional_evidence_store_report",
    "persist_p56_transactional_evidence_store",
]

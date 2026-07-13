# P56 — Transactional Evidence Store

Status: `P56_TRANSACTIONAL_EVIDENCE_STORE_BACKEND_VALIDATED_REVIEW_ONLY_IMPORTER_DISABLED`

P56 replaces the P55 finding that the JSONL registry cannot atomically coordinate duplicate-lock acquisition, one-time nonce consumption, immutable record append, and commit. It implements and self-tests a SQLite-backed transactional evidence store while keeping the real P7 importer disabled.

## Scope correction

P48 through P55 built and reviewed the P7 evidence handoff/import safety chain. P56 is not another review wrapper. It is a concrete storage implementation milestone.

P56 proves the storage backend only. It does **not** prove that a real signed-testnet evidence bundle exists, that P50–P54 have accepted real evidence, or that an operator has approved a P7 import.

## Implemented backend

Backend: `sqlite_wal_full_sync_local`

Required database controls:

- SQLite WAL journal mode
- `PRAGMA synchronous=FULL`
- foreign-key enforcement
- `BEGIN IMMEDIATE` transaction start
- unique candidate hash
- unique exchange order ID
- unique client order ID
- unique idempotency key
- unique one-time nonce
- unique duplicate-lock key
- immutable record SHA256
- committed transaction receipt
- update/delete blocking triggers on import, lock, nonce, and receipt tables

## Atomic transaction shape

The backend self-test executes this sequence inside one SQLite transaction:

```text
BEGIN IMMEDIATE
-> insert duplicate-import lock
-> insert one-time nonce consumption
-> insert immutable evidence record
-> insert transaction receipt
-> verify record hash
-> COMMIT
```

Any failure before commit rolls back all four resources.

## Self-test evidence

The ephemeral self-test verifies:

1. exactly one successful commit creates one lock, one nonce, one immutable record, and one receipt;
2. a duplicate candidate/order/idempotency attempt is blocked without partial state;
3. injected failures after lock, after nonce, after record, and immediately before commit leave no partial state;
4. update and delete operations are blocked by append-only triggers;
5. real P7 import scope is rejected by P56;
6. the temporary self-test database is not packaged or retained.

## Readiness distinction

P56 may report:

```text
backend_transaction_ready=true
```

while it must still report:

```text
real_signed_testnet_evidence_present=false
real_p7_import_integrated=false
actual_p7_import_ready=false
p7_importer_enabled=false
```

Backend readiness is not runtime authority and is not P7 import approval.

## Remaining real progress gate

The next meaningful gate is:

1. obtain one real redacted signed-testnet external-runtime evidence bundle under separate approval;
2. rerun P50–P54 against that real bundle;
3. issue a separate operator import approval bound to the exact hashes and nonce;
4. integrate a future P7 importer with this transactional backend;
5. execute exactly one approved P7 import transaction;
6. accumulate repeated clean P7 records for P8.

No additional P7 review-only wrapper should be added unless a concrete defect is discovered.

## Safety state

```text
p7_importer_enabled=false
p7_importer_action_allowed=false
p7_importer_action_executed=false
p7_valid_status_written_by_p56=false
p7_report_persisted_by_p56=false
p7_runtime_registry_append_performed_by_p56=false
p7_runtime_nonce_consumed_by_p56=false
p7_runtime_duplicate_lock_acquired_by_p56=false
p7_runtime_transaction_started_by_p56=false
p7_runtime_transaction_committed_by_p56=false
actual_order_submission_performed=false
order_endpoint_called=false
http_request_sent=false
signature_created=false
secret_value_accessed=false
runtime_mutation_performed=false
live_canary_execution_enabled=false
live_scaled_execution_enabled=false
```

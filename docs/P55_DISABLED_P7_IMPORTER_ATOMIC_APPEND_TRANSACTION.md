# P55 - Disabled P7 Importer Interface & Atomic Append Transaction Design

Status: `P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_READY_REVIEW_ONLY_IMPORTER_DISABLED`

P55 is the final internal design step for the P7 evidence-import path. It does not implement, enable, or execute a P7 importer. It closes the review-only design chain by defining the future transaction contract and by explicitly recording that the current JSONL registry backend is not sufficient for real atomic import.

## Why P55 exists

P54 proved that an evidence candidate can pass the final guard while the importer remains disabled. A future importer still needs to make three state changes safely:

1. acquire a duplicate-import lock,
2. consume one one-time nonce,
3. append exactly one immutable P7 evidence record.

Those changes must be atomic. A best-effort sequence across separate JSONL files can leave partial state after a process crash. P55 therefore requires a transactional backend or equivalent durable coordination mechanism before real P7 import can be enabled.

## Required future transaction order

```text
freshly_revalidate_p54_final_guard
-> begin_atomic_transaction
-> acquire_duplicate_import_lock
-> recheck_one_time_nonce_freshness
-> consume_one_time_nonce
-> construct_immutable_p7_record
-> append_exactly_one_p7_record
-> verify_p7_record_hash_and_unique_id
-> commit_atomic_transaction
-> release_duplicate_import_lock
```

## Required failure behavior

- No P7 valid status may be published before commit.
- Duplicate-lock failure consumes no nonce.
- Nonce failure appends no P7 record.
- Append failure must roll back nonce and lock state.
- Verification failure must not commit.
- Crash recovery must use a durable transaction journal.
- Registry overwrite, in-place update, delete, truncate, partial commit, and best-effort multi-file writes remain forbidden.

## Current backend assessment

The current `jsonl_append_only_current` backend is intentionally classified as:

```text
multi_resource_atomic_transaction_supported=false
compare_and_set_supported=false
durable_distributed_lock_supported=false
transaction_rollback_supported=false
durable_transaction_journal_supported=false
crash_recovery_supported=false
current_backend_safe_for_real_p7_import=false
actual_import_ready=false
```

This is a design finding, not a regression. Review artifacts may still be generated, but actual P7 import must remain disabled until a backend proves the required transaction properties.

## P7 scope correction

P48 through P54 split the evidence handoff and import boundary into many small safety layers. P55 consolidates the remaining importer/transaction requirements and closes the internal review-only P7 design chain. No additional review-only wrapper phase should be added after P55 unless a concrete defect is found.

The next meaningful milestone is external evidence, not another wrapper:

1. obtain one real signed-testnet external-runtime evidence bundle under separate operator approval,
2. provide a transaction-capable backend,
3. rerun P50-P54 against the real redacted evidence,
4. perform one separately approved P7 import transaction,
5. accumulate multiple clean real P7 records for P8.

## Safety state

```text
p7_importer_enabled=false
p7_importer_action_executed=false
p7_atomic_transaction_started=false
p7_atomic_transaction_committed=false
p7_duplicate_import_lock_acquired_by_p55=false
p7_import_nonce_consumed_by_p55=false
p7_registry_append_performed_by_p55=false
p7_valid_status_written_by_p55=false
actual_order_submission_performed=false
order_endpoint_called=false
http_request_sent=false
signature_created=false
secret_value_accessed=false
live_canary_execution_enabled=false
live_scaled_execution_enabled=false
```

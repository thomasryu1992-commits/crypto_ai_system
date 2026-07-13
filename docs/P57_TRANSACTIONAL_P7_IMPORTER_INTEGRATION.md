# P57 — Transactional P7 Importer Integration

## Purpose
P57 connects the already validated P54 final guard to the P56 SQLite transactional evidence store through an actual importer orchestration class. This is an implementation step, not another review-wrapper layer.

## Implemented Path

```text
P54 final-guard-passed packet
        ↓
P57 guard/candidate/approval revalidation
        ↓
P57 transactional importer orchestration
        ↓
P56 BEGIN IMMEDIATE transaction
        ↓
duplicate lock → nonce consume → immutable record → receipt
        ↓
commit or full rollback
```

## Package Safety Boundary
Package-generated validation runs only under:

```text
operation_scope=p57_transactional_p7_importer_integration_self_test
```

The following path is explicitly disabled:

```text
operation_scope=p7_real_import
```

P57 therefore proves that P54 and P56 are correctly integrated while preserving:

```text
p7_importer_enabled=false
p7_real_import_enabled=false
actual_p7_import_ready=false
```

## What P57 Proves
- P54 packet and candidate hashes are revalidated.
- A self-test-only operator approval is hash-bound to P54 and the candidate.
- The importer invokes the same P56 ACID transaction path.
- Exactly one record commits.
- Duplicate attempts fail without partial state.
- Failures after lock, nonce, record, and before commit fully roll back.
- Append-only update and delete guards remain active.
- Real P7 import remains blocked.

## What P57 Does Not Do
- It does not import real signed-testnet evidence.
- It does not persist P7 valid status.
- It does not append the runtime P7 registry.
- It does not consume a runtime nonce or acquire a runtime duplicate lock.
- It does not enable a P8 candidate.
- It does not call exchange endpoints or access secret values.

## P7 Boundary Decision
P7 internal design and implementation preparation are now complete enough that additional review-only wrappers are not recommended. The next meaningful progress requires a real, redacted signed-testnet external-runtime evidence bundle and a separate operator-controlled real-import approval.

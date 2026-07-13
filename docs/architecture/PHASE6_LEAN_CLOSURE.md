# Phase 6 Lean Closure

Status: `PHASE6_LEAN_MERGE_CLOSED`

## Active architecture

```text
src/crypto_ai_system/governance/
├── readiness_common.py
├── readiness.py
├── signed_testnet_preparation.py
├── operator_unlock_template.py
├── operator_unlock_fixtures.py
├── readiness_gate.py
├── readiness_packet.py
├── actual_intake_sandbox.py
└── actual_intake_bridge.py
```

## Completion criteria

- one canonical Readiness Review entry point;
- semantic Governance modules;
- one shared Readiness utility module;
- explicit readiness state model;
- old `validation/phase6_*.py` modules reduced to thin wrappers;
- historical Phase 6 commands use semantic imports;
- active source no longer imports old Phase 6 validation paths;
- one consolidated Phase 6 development-history document;
- closure manifest with every readiness, secret, and execution permission false;
- focused closure checker and regression tests;
- Lean migration state advanced to Phase 7 Executor Review.

## Deferred until final global compaction

These compatibility surfaces remain intentionally:

- historical Phase 6 report files used by older validation contracts;
- historical Phase 6 command filenames;
- thin Phase 6 validation wrappers;
- phase-number status-checker entries.

They are no longer active architecture.

Removing them now would mix active code migration with historical-contract
deletion and make regression failures harder to isolate.

## Permission boundary

A preparation preview, operator template, fixture result, readiness gate,
readiness packet, actual-intake sandbox, or bridge packet must never directly
grant runtime permission.

All signed-testnet, live, secret-access, and external-order permissions remain
false.

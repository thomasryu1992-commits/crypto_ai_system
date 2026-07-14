# Phase 8 Execution Preparation Architecture

## Stage boundary

```text
Phase 7
Pre-Executor Governance

↓

Phase 8
Signed Testnet Execution Preparation

↓

Phase 9
Single Signed Testnet Order
only after separate explicit approval
```

Phase 8 does not contain order-submission authority.

## Phase 8-M1

```text
governance/
└── signed_testnet_execution_preparation.py
```

Responsibilities:

```text
Secret / key handling design

Metadata-only reference boundary

Exchange write-path dry-validation contract

Hot-path PreOrderRiskGate contract

Executor final-guard design

Preparation state model

Review-only evidence report
```

## Runtime sequence target

Future Phase 8 implementation must converge on:

```text
final order intent frozen

↓

fresh market / account / venue evidence

↓

hot-path PreOrderRiskGate

↓

executor final guard

↓

future request signing boundary

↓

future signed-testnet executor
```

M1 implements only the contracts.

## Secret boundary

Allowed:

```text
secret reference ID

key fingerprint

environment metadata

venue metadata

scope metadata

operator reference

canonical timestamp
```

Forbidden:

```text
API key value

API secret value

private key

passphrase

password

seed phrase

mnemonic

secret-file content

secret-file creation
```

## Write-path dry validation

The dry path may validate:

```text
method boundary

testnet routing classification

payload schema

idempotency

timeouts

bounded retries

response schema

error taxonomy

mainnet denylist

no silent fallback
```

The dry path may not:

```text
sign a request

open write transport

call a real order endpoint

receive an exchange order ID

receive a fill

change a position

change a balance
```

## Hot-path risk contract

The hot-path gate must run immediately before any future executor and after the
final payload is frozen.

It must not reuse an old cold-path approval as an execution-time risk result.

Required checks:

```text
profile approval and hash

data freshness

optional-data health

fallback / synthetic / mock / sample block

position limit

daily loss

consecutive loss

spread

slippage

API error rate

reconciliation mismatch

kill switch

hard caps

min/max notional

fee/slippage evidence

venue readiness

ID chain completeness
```

## Final guard

The final guard must fail closed on:

```text
missing evidence

unknown state

stale evidence

hash mismatch

live/mainnet scope

secret exposure

write call during dry validation

fallback/synthetic/mock/sample evidence

kill-switch uncertainty

monitoring uncertainty

clock-sync uncertainty

reconciliation uncertainty

rollback uncertainty
```

## Current runtime validation state

```text
metadata_only_key_scope_runtime_validated=false

write_path_dry_validation_runtime_validated=false

write_path_validated_against_real_order_endpoint=false

hot_path_risk_gate_runtime_implemented=false

hot_path_risk_gate_runtime_validated=false

executor_final_guard_runtime_implemented=false

executor_final_guard_runtime_validated=false

monitoring_alerting_runtime_validated=false

kill_switch_runtime_validated=false

clock_sync_runtime_validated=false

rollback_runtime_validated=false

real_fill_position_balance_reconciliation_validated=false
```

## Permissions

```text
ready_for_signed_testnet_execution=false

testnet_order_submission_allowed=false

external_order_submission_allowed=false

external_order_submission_performed=false

exchange_endpoint_called=false

place_order_enabled=false

cancel_order_enabled=false

signed_order_executor_enabled=false

adapter_write_routing_enabled=false

request_signing_allowed=false
```

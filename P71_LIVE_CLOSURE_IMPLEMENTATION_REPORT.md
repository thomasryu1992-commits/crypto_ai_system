# P71 Live Read-only Closure Implementation Report

## Scope

This cumulative package includes the P71 required WebSocket/REST/evidence hardening and adds the final operator-controlled live closure layer.

Implemented:

- public Extended Sepolia REST + BTC-USD WebSocket live evidence runner
- external Windows Credential Manager-backed private REST + account WebSocket runner
- one-command PowerShell operator flow
- fresh-evidence source correlation with maximum 180-second skew
- canonical closure report and redacted attestation
- append-only consumed-evidence registry
- anti-replay validation for public evidence IDs and private read-session IDs
- atomic report writes and registry locking
- canonical successful closure preservation after later blocked/replay attempts
- manual public-only GitHub Actions workflow with read-only permissions and no repository secrets
- independent `p71-contract` CI job so P71 diagnostics remain visible even when broader legacy validation fails

## Safety invariants

Always false:

- `ready_for_signed_testnet_execution`
- `testnet_order_submission_allowed`
- `signed_testnet_promotion_allowed`
- `external_order_submission_allowed`
- `external_order_submission_performed`
- `place_order_enabled`
- `cancel_order_enabled`
- `signed_order_executor_enabled`
- `network_write_call_performed`
- `order_endpoint_called`
- `cancel_endpoint_called`
- `signature_created`
- `stark_private_key_accessed`

The closure layer reads JSON evidence only. It does not import the external credential-bearing package and cannot access credential values.

## Validation performed

Offline focused validation:

```text
31 passed
```

Static checks:

```text
P71_CLOSURE_CONTRACT_PASSED
P71_STATUS_CONSISTENCY_PASSED
```

Simulated fresh live-evidence closure:

```text
status=P71_EXTENDED_READONLY_CLOSURE_COMPLETE
p71_complete=true
closure_evidence_consumed=true
exit_code=0
```

Replay simulation:

```text
P71_PUBLIC_EVIDENCE_REPLAY_DETECTED
P71_PRIVATE_SESSION_REPLAY_DETECTED
exit_code=2
```

The replay attempt did not overwrite the previously successful canonical closure report.

## Real-network status

Real Extended public/private WebSocket evidence was not generated in this isolated build environment. P71 must remain incomplete until the operator runs the PowerShell closure flow on the Windows host with the read-only Extended credential reference and the live endpoints pass.

# Crypto_AI_System P64 Development & Validation Report

## Step

P64 — Opaque Sender Subprocess Bridge

## Final Status

`P64_OPAQUE_SENDER_SUBPROCESS_BRIDGE_VALIDATED_REVIEW_ONLY_DISABLED`

## Objective

Implement a hardened metadata-only subprocess boundary between the P63 concrete executor orchestrator and an operator-installed opaque sender program without bundling credentials, a concrete signer, or a network-capable sender executable in the review/default runtime package.

## Implemented

- `external_runtime_packages/binance_futures_testnet_adapter/opaque_sender_subprocess_bridge.py`
- `src/crypto_ai_system/execution/opaque_sender_subprocess_bridge.py`
- `scripts/build_p64_opaque_sender_subprocess_bridge.py`
- `tests/agents/test_p64_opaque_sender_subprocess_bridge.py`
- `agents/execution/opaque_sender_subprocess_bridge_agent.md`
- `docs/P64_OPAQUE_SENDER_SUBPROCESS_BRIDGE.md`
- `P64_OPAQUE_SENDER_SUBPROCESS_BRIDGE_REPORT.md`

## Security Boundary

- Absolute launcher path required
- Absolute sender-program path required
- SHA256 attestation for launcher and sender program
- Fixed argv contract
- `shell=false`
- Parent environment not inherited
- Stdin disabled
- Minimal metadata-only environment allowlist
- Ephemeral metadata request file with mode `0600`
- Request-file cleanup after execution
- Timeout guard
- Stdout/stderr size guards
- One redacted JSON object on stdout only
- Empty stderr requirement
- No raw credential, raw signed payload, raw request, or raw response fields
- `POST /fapi/v1/order` permanently blocked

## Self-test

The no-network self-test creates an ephemeral sender program outside the package, verifies the launcher/program hashes, executes it through the hardened subprocess bridge, validates the redacted response, and removes the temporary directory.

Self-test result:

```text
self_test_passed=true
subprocess_bridge_used=true
fixture_sender_program_packaged=false
shell_used=false
inherited_environment_used=false
stdin_used=false
http_request_sent=false
signature_created=false
secret_value_accessed=false
actual_order_submission_performed=false
```

## Regression Validation

```text
compileall: passed
P64 standalone: 13 passed
P7/P8/P48-P64 focused regression: 211 passed
Agent lint: passed
Agent contract validation: passed
Agent output validation: passed
Agent evals: 61 passed, including 10 blocked negative cases
Agent Library contract review: passed, 85 agents
Status consistency checker: passed
External package independent installation: passed
Installed-package P64 no-network subprocess self-test: passed
```

## Negative Fixtures

10/10 blocked fail-closed:

- bridge enabled by default
- shell execution allowed
- inherited parent environment allowed
- external package included in default runtime candidate
- concrete sender program bundled
- mainnet sender metadata
- credential exposure to bridge
- runtime authority granted
- real order submission requested
- raw credential included

## Runtime State

```text
p64_opaque_sender_subprocess_bridge_enabled=false
p64_subprocess_execution_enabled=false
p64_sender_program_injection_enabled=false
p64_concrete_network_sender_program_included=false
p64_external_runtime_network_calls_enabled=false
p64_external_runtime_signing_enabled=false
p64_order_test_endpoint_call_enabled=false
p64_order_test_endpoint_call_performed=false
p64_real_order_submit_enabled=false
p64_real_order_endpoint_called=false
real_order_test_endpoint_call_enabled=false
real_order_test_endpoint_call_performed=false
real_order_endpoint_enabled=false
real_order_endpoint_called=false
real_signed_testnet_evidence_present=false
actual_p7_import_ready=false
actual_order_submission_performed=false
actual_testnet_order_submitted=false
actual_live_order_submitted=false
external_order_submission_performed=false
http_request_sent=false
signature_created=false
signed_request_created=false
secret_value_accessed=false
runtime_mutation_performed=false
runtime_scheduler_enabled=false
live_canary_execution_enabled=false
live_scaled_execution_enabled=false
```

## Remaining External Requirement

A separately built and operator-installed sender program is still required before any real `/fapi/v1/order/test` execution. That program must own credential access, signing, API-key header handling, and HTTP transport inside its own process and return only redacted JSON evidence. P64 does not grant permission to run it.

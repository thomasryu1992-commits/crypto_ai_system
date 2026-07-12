# P64 — Opaque Sender Subprocess Bridge

P64 implements the process boundary between the P63 executor orchestrator and an operator-installed sender program. Crypto_AI_System passes only metadata references and a validated order-test descriptor; credential access, signing, and HTTP remain inside the separately installed sender process.

## Implemented

- Absolute launcher/program path validation
- SHA256 attestation of both launcher and sender program
- Fixed argv contract with `shell=false`
- Full parent-environment inheritance disabled
- Stdin disabled
- Minimal environment allowlist containing metadata references only
- Ephemeral metadata-only request file with `0600` permissions
- Request-file deletion after execution
- Timeout guard
- Stdout/stderr size guards
- Single redacted JSON stdout contract
- Empty stderr requirement
- P61 request hash, P63 source/request hash, operator confirmation, and one-shot nonce bindings
- No-network ephemeral sender-program self-test
- Fail-closed negative fixtures
- Permanent block on `POST /fapi/v1/order`

## Package Boundary

Included:

- Subprocess bridge implementation
- Sender executable metadata contract
- Disabled activation/request templates
- Hash, path, subprocess, output, and no-secret validators
- Ephemeral no-network self-test generator

Not included:

- API key value reader
- API secret value reader
- Secret-file reader/writer
- Concrete signer
- Concrete network sender program
- Raw signed request persistence
- Raw response persistence
- Real order-submit capability

## Subprocess Contract

```text
Crypto_AI_System / P63
        ↓ metadata only
P64 bridge
        ↓ fixed argv, shell=false
operator-installed sender program
        ↓ credential access/signing/HTTP inside child process only
redacted JSON stdout
        ↓
P64 validation
```

The request file contains only:

- `credential_reference_id`
- key fingerprint
- validated P61 request descriptor
- P63 source/request hashes
- one-shot nonce hash

It must not contain raw credentials, raw HTTP requests, signatures, or raw exchange responses.

## Current Disabled State

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
http_request_sent=false
signature_created=false
secret_value_accessed=false
actual_order_submission_performed=false
```

## No-network Self-test

The self-test creates an ephemeral Python sender program outside the package, verifies the launcher/program SHA256 values, executes it through the hardened subprocess boundary, validates redacted JSON stdout, and deletes the entire temporary directory. The fixture performs no credential access, signing, network request, endpoint call, or order submission.

## Status

`P64_OPAQUE_SENDER_SUBPROCESS_BRIDGE_VALIDATED_REVIEW_ONLY_DISABLED`

This status means the subprocess boundary, executable attestation, metadata-only IPC, output validation, no-network self-test, and fail-closed fixtures are valid. It does not mean that a concrete sender program was bundled, credentials were accessed, a signature was created, `/fapi/v1/order/test` was called, or any order was submitted.

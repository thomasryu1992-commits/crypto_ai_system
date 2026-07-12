# P63 — Concrete External Order-Test Executor Integration

P63 implements the concrete executor orchestration layer between the P62 operator-side one-shot kit and an operator-supplied opaque credentialed sender. The orchestrator is real code, but the credentialed network sender remains outside the review/default runtime package.

## Implemented

- Concrete `P61ExternalSignedOrderTestExecutor` orchestration implementation
- P62 report, P62 run request, P61 request descriptor, and one-shot nonce hash binding
- Exact P63 operator authorization phrase
- Metadata-only credential reference and key fingerprint boundary
- Opaque external sender protocol for process-memory credential handling, signing, and HTTP
- Testnet-only `POST /fapi/v1/order/test` endpoint enforcement
- BTCUSDT-only and one-request-only policy
- Redacted-result validation
- No-network fixture sender integration self-test
- Fail-closed negative fixtures
- Permanent hard block on `POST /fapi/v1/order`

## Package Boundary

Included:

- Concrete executor orchestrator
- Opaque sender protocol
- Sender metadata contract
- Disabled activation template
- No-network fixture sender
- Validation and self-test code

Not included:

- API key value reader
- API secret value reader
- Secret-file reader/writer
- Concrete signer
- Concrete network sender
- Raw signed request persistence
- Raw response persistence
- Real order-submit capability

## Credential Boundary

The P63 orchestrator receives only:

- `credential_reference_id`
- `key_fingerprint_sha256`
- validated request hashes
- operator approval hashes
- one-shot nonce hashes

The external opaque sender owns credential access, request signing, API-key headers, and HTTP transport inside its own process. P63 does not receive or persist raw credential values.

## Current Disabled State

```text
p63_concrete_external_order_test_executor_enabled=false
p63_opaque_credentialed_sender_injection_enabled=false
p63_concrete_network_sender_included=false
p63_external_runtime_network_calls_enabled=false
p63_external_runtime_signing_enabled=false
p63_order_test_endpoint_call_enabled=false
p63_order_test_endpoint_call_performed=false
p63_real_order_submit_enabled=false
p63_real_order_endpoint_called=false
http_request_sent=false
signature_created=false
secret_value_accessed=false
actual_order_submission_performed=false
```

## No-network Integration Self-test

The self-test uses:

1. P61 request descriptor
2. P62 run-request hash context
3. P63 enabled fixture activation
4. Concrete P63 executor orchestrator
5. No-network opaque fixture sender
6. Redacted-result validation

The fixture performs no signing, HTTP request, endpoint call, credential access, or order submission.

## Status

`P63_CONCRETE_EXTERNAL_ORDER_TEST_EXECUTOR_INTEGRATION_VALIDATED_REVIEW_ONLY_DISABLED`

This status means the executor orchestration, metadata-only boundary, sender contract, endpoint policy, no-network self-test, and fail-closed fixtures are valid. It does not mean that a concrete network sender was included, an external credential was accessed, a signature was created, `/fapi/v1/order/test` was called, or any order was submitted.

# P62 — Operator-side External Order-Test Execution Kit

P62 packages the P61 Binance Futures testnet `POST /fapi/v1/order/test` adapter boundary into a separate operator-side, one-shot execution kit. It adds an exclusive one-shot run guard, exact operator authorization contract, P61 request/approval hash binding, redacted evidence exporter, no-secret scanner, evidence manifest, and P58 bridge candidate.

P62 does **not** bundle a concrete credential reader, secret-file reader/writer, signer, HTTP transport, or external executor. The default package is disabled and does not call any endpoint.

## Implemented

- Separate operator-side external-runtime kit manifest
- Testnet-only, BTCUSDT-only, one-request-only policy
- Exact operator phrase and confirmation hash contract
- P61 report, request descriptor, and approval hash binding
- Metadata-only credential reference and key fingerprint binding
- Filesystem one-shot guard using exclusive creation
- Duplicate second-run rejection
- Redacted evidence exporter with atomic writes
- No-secret scan report
- P58 bridge candidate and evidence hash manifest
- No-network injected-executor self-test
- Hard block on `POST /fapi/v1/order`

## Default Disabled State

```text
operator_side_external_order_test_execution_kit_enabled=false
operator_side_external_order_test_execution_enabled=false
operator_side_external_order_test_network_calls_enabled=false
operator_side_external_order_test_signing_enabled=false
operator_side_external_order_test_endpoint_call_enabled=false
operator_side_external_order_test_endpoint_call_performed=false
real_order_test_endpoint_call_performed=false
real_order_endpoint_called=false
http_request_sent=false
signature_created=false
secret_value_accessed=false
actual_order_submission_performed=false
```

## One-shot Guard

The future operator-side execution path must acquire an exclusive marker before any external executor call. The marker contains hashes only:

- one-shot nonce SHA256
- P62 operator run request SHA256
- marker SHA256

A duplicate marker blocks the second run. On execution failure, the marker is released. On successful execution/evidence export, it is retained to prevent replay.

## Evidence Export

The exporter writes only:

1. Redacted order-test result
2. Operator execution transcript
3. No-secret scan report
4. P58 bridge candidate
5. Evidence export manifest

Raw credentials, raw query strings, raw signed payloads, raw request bodies, raw responses, and unredacted exchange responses are forbidden.

## Current Boundary

The package self-test uses a no-network fixture executor. Its evidence is explicitly marked fixture/synthetic and is not eligible for P58 real acquisition or P7 import.

A future real `/order/test` run still requires a separately supplied concrete external executor and separate operator approval outside the review/default runtime package. The real order endpoint `/fapi/v1/order` remains disabled.

## Status

`P62_OPERATOR_SIDE_EXTERNAL_ORDER_TEST_EXECUTION_KIT_VALIDATED_REVIEW_ONLY_DISABLED`

This status means the operator-side kit, one-shot guard, redacted evidence exporter, no-secret scanner, package boundary, and fail-closed fixtures are valid. It does not mean that a signature, HTTP request, order-test call, signed-testnet order, P7 import, or live trade occurred.

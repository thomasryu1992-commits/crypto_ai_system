# P61 — Real Testnet `/fapi/v1/order/test` Dry Validation Adapter

P61 implements the external-runtime orchestration path for a future Binance USD-M Futures testnet `POST /fapi/v1/order/test` call. The package pins the testnet base URL, BTCUSDT-only scope, one-request limit, metadata-only credential reference, external process-memory credential boundary, exact operator approval contract, and redacted-response contract.

P61 does **not** include a credential reader, concrete network executor, raw credential value, concrete signer, or enabled endpoint caller. The default policy and activation template remain disabled.

## Implemented

- Testnet-only `/fapi/v1/order/test` adapter orchestration
- Canonical request descriptor and deterministic request hash
- External signed-order-test executor protocol
- Metadata-only credential reference and key fingerprint binding
- Exact operator approval contract
- External-runtime activation contract
- Redacted response validation
- No-network injected-executor self-test
- Real `/fapi/v1/order` submit endpoint hard block
- Negative fixtures for mainnet, wrong symbol, submit enablement, packaging violations, runtime authority, and secret/raw fields

## Default Disabled State

```text
external_runtime_order_test_adapter_enabled=false
external_runtime_order_test_network_calls_enabled=false
external_runtime_order_test_signing_enabled=false
real_order_test_endpoint_call_enabled=false
real_order_test_endpoint_call_performed=false
real_order_endpoint_enabled=false
real_order_endpoint_called=false
http_request_sent=false
signature_created=false
secret_value_accessed=false
actual_order_submission_performed=false
```

## Credential Boundary

P61 passes only:

- `credential_reference_id`
- `key_fingerprint_sha256`
- request descriptor metadata and hashes

A future external executor must keep credential values, signing, and request headers inside its own process memory and return only a redacted result contract. P61 does not read or persist credential values.

## Execution Boundary

The default package validates only a no-network injected-executor fixture. A future real order-test call requires all of the following outside the review package:

1. Separate explicit operator approval.
2. Exact approval phrase for one testnet order-test request only.
3. Non-fixture request descriptor with fresh runtime timestamp and venue-valid quantity.
4. External-runtime-only executor pinned to `https://demo-fapi.binance.com` and `POST /fapi/v1/order/test`.
5. Process-memory-only credential binding.
6. Redacted response output and no-secret evidence.

The real order submit endpoint `/fapi/v1/order` remains blocked by P61.

## Status

`P61_REAL_TESTNET_ORDER_TEST_DRY_VALIDATION_ADAPTER_VALIDATED_REVIEW_ONLY_DISABLED`

This status means the adapter contract, orchestration path, no-network self-test, and fail-closed guards are valid. It does not mean that a network request, signature, order-test call, or order submission occurred.

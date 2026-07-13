# P60 — External Signer & HTTP Transport Injection Harness

P60 implements a disabled-by-default external runtime injection harness for a future Binance Futures testnet adapter. It connects the P59 separate adapter package boundary to metadata-only external signer and HTTP transport contracts, and validates the `/fapi/v1/order/test` request plan without reading secrets, creating signatures, sending HTTP requests, or submitting orders.

## Scope

- Review-only harness implementation
- Testnet-only Binance USD-M Futures endpoint policy
- BTCUSDT-only dry validation intent
- Metadata-only key binding
- External process-memory signer metadata
- External HTTP transport metadata
- No-network `/fapi/v1/order/test` dry validation
- Negative fixture validation

## Explicitly Disabled

- Real signer implementation
- Concrete HTTP transport implementation
- API key or secret reading
- Signature creation
- Signed request creation
- HTTP request sending
- Order submit, status polling, and cancel calls
- Real signed-testnet evidence creation
- P7 import readiness
- Runtime mutation

## Status

`P60_EXTERNAL_SIGNER_HTTP_TRANSPORT_INJECTION_HARNESS_VALIDATED_REVIEW_ONLY_DISABLED`

A valid P60 result only means the harness structure and no-network dry validation are correct. It does not enable real order-test calls or order submission.

# P59 Binance Futures Testnet External Adapter Package

This package is intentionally separate from the default Crypto_AI_System runtime candidate.

It provides:
- a Binance USD-M Futures **testnet-only** endpoint policy,
- metadata-only key references and SHA-256 fingerprints,
- external process-memory signer and HTTP transport protocols,
- a disabled-by-default runner configuration,
- a no-network contract self-test,
- fail-closed validation fixtures.

It does **not** provide:
- an API key or API secret reader,
- a concrete signer,
- a concrete HTTP transport,
- an enabled order runner,
- order submission, status polling, or cancel execution,
- mainnet/live endpoints,
- withdrawal, transfer, leverage, margin, or admin mutations.

The package must remain disabled until a later separately approved external-runtime stage supplies a testnet-only signer/transport implementation and passes the full P6/P54/P58 safety chain.

## P61 Order-Test Adapter Contract

P61 adds `order_test_dry_validation_adapter.py`, which defines the external-runtime-only orchestration contract for one `POST /fapi/v1/order/test` request. The package passes only a credential reference and key fingerprint; credential values, signing, and request headers must remain inside a separately supplied external executor process. The default policy and activation remain disabled, and no concrete executor or credential reader is bundled.

## P62 Operator-side Execution Kit

`operator_order_test_execution_kit.py` adds a disabled-by-default one-shot operator wrapper around the P61 order-test adapter. It provides an exclusive replay guard, operator/P61 hash binding, redacted evidence export, no-secret scanning, and P58 bridge metadata. It does not include a credential reader, signer, transport, concrete executor, or enabled network path.

## P63 Concrete Executor Orchestrator

`concrete_external_order_test_executor.py` implements the concrete P61 executor orchestration layer. It validates the disabled-by-default P63 activation, P61 request hashes, P62 run hashes, one-shot nonce evidence, metadata-only credential reference, and an opaque external sender contract.

The package includes only a no-network fixture sender. It does not include a credential reader, concrete signer, or concrete network sender. Real credential access, signing, and HTTP transport must remain inside an independently supplied operator-side opaque sender process.

## P64 — Opaque Sender Subprocess Bridge

P64 adds a hardened subprocess boundary for an operator-installed sender program. It validates absolute launcher/program paths and SHA256 values, uses `shell=false`, disables inherited environment and stdin, writes only a temporary metadata request file with `0600` permissions, enforces timeout/output limits, and accepts one redacted JSON object on stdout. No concrete sender program, credential reader, signer, or network transport is bundled.

# P59 — Separate Testnet-only External Adapter Package

## Goal
Create a physically separate external-runtime adapter package without adding a concrete exchange write client, signer, secret reader, or enabled runner to the default Crypto_AI_System runtime candidate.

## Implemented
- Binance USD-M Futures testnet-only endpoint policy
- BTCUSDT-only and one-order-only scope
- Metadata-only key references and SHA-256 fingerprints
- External process-memory signer protocol
- External HTTP transport protocol
- Disabled-by-default runner configuration
- Unsigned request-plan builder
- No-network package self-test
- Fail-closed negative fixtures
- Separate adapter-package ZIP output
- Runtime-candidate exclusion rule

## Still Disabled / Absent
- Concrete HTTP transport
- Concrete signer
- API key or secret reader
- Secret file access
- Network calls
- Signature creation
- Order submission
- Status polling
- Cancel execution
- Real signed-testnet evidence generation
- P7 import

## Packaging Boundary
`external_runtime_packages/binance_futures_testnet_adapter/` is included in source handoff for review and testing, excluded from the default runtime candidate, and exported as its own `external_runtime_adapter_package.zip`.

## Safety Result
P59 proves package separation, endpoint allowlisting, metadata-only key binding, and disabled orchestration. It does not grant execution permission.

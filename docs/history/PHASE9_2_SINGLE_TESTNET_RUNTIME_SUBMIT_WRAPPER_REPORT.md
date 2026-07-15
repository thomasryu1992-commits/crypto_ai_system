# Phase 9.2 Single Testnet Runtime Submit Wrapper / Mocked by Default

This package adds a narrow one-order submit wrapper for Phase 9.2 while keeping the default behavior mocked and review-only.

## Boundary

- No real exchange order endpoint call is implemented in this package.
- No API key value, API secret value, private key, passphrase, or secret file may be stored.
- Mock submit evidence can be generated only when explicit approval text, testnet-only scope, max_order_count=1, fresh risk refresh, kill switch confirmation, and metadata-only key fingerprint are present.
- All runtime executor, endpoint, HTTP, and signature flags remain false.

## Next real runtime action

A real testnet endpoint adapter remains a separate, explicit runtime action and must be introduced only after operator approval, endpoint-time risk refresh, duplicate submit lock, post-submit relock guard, and evidence intake readiness are validated.

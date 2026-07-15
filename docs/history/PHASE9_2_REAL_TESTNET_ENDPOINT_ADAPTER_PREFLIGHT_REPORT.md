# Phase 9.2 Real Testnet Endpoint Adapter Preflight / No Submit

This phase adds a review-only preflight packet for a future real testnet endpoint adapter.

It records adapter metadata references for endpoint base URL, endpoint paths, timestamp/recvWindow, symbol rules, min notional, key reference, key fingerprint, and permission scope.

It does not call exchange endpoints, create signatures, send HTTP requests, submit orders, or grant runtime authority.

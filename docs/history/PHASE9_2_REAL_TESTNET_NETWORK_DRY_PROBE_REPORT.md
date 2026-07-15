# Phase 9.2 Real Testnet Network Dry Probe / No Order Submit

This package adds a public-metadata-only testnet network dry probe preparation layer.

It does not submit orders, call order/status/cancel endpoints, create signatures, read secrets, or enable executors. The only future command allowed by this packet is a separate public metadata reachability probe for testnet time/exchange-info/symbol-info endpoints.

# Phase 9.2 Public Metadata Probe Bridge / No Order Submit

This package adds a bridge that can connect an explicitly requested real public metadata probe result to the public metadata filled-validation input path.

The bridge remains no-order-submit by design. It does not call order, cancel, order-status, account, balance, position, private, or trade endpoints. It does not read API secrets, create signatures, create signed requests, enable executors, or mutate runtime settings.

A successful public metadata bridge can mark metadata evidence as ready for review only, but `real_testnet_submit_may_begin` remains false. A later single signed testnet order still requires separate explicit runtime approval and fresh hot-path risk validation.

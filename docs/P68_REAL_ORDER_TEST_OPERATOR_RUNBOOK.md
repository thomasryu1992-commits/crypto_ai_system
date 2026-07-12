# P68 Operator Runbook — One Real Binance Futures Testnet `/order/test`

## Boundary

This runbook prepares one external `/fapi/v1/order/test` validation. It does not submit an order and it must never call `/fapi/v1/order`.

## Before execution

1. Keep API key and API secret values outside Crypto_AI_System, chat, ZIPs, JSON artifacts, logs, and screenshots.
2. Prepare a real non-fixture P66 intake using the exact operator phrase.
3. Validate the P66 intake and retain the accepted validation receipt.
4. Verify the installed sender executable and launcher by absolute path and SHA256.
5. Verify the testnet-only scope: `https://demo-fapi.binance.com`, `POST /fapi/v1/order/test`, `BTCUSDT`, one request.
6. Verify local clock synchronization and a fresh one-shot nonce.
7. Confirm the output directory contains no previous receipt with the same nonce.

## External execution

The sender must be launched outside Crypto_AI_System. No credential value may be passed through CLI arguments, stdin, JSON, logs, or the parent process. The sender may use credentials only inside its own process-memory boundary and must output one redacted JSON receipt.

## After execution

1. Save the redacted receipt to the P67 receipt path.
2. Validate it with `scripts/validate_p67_real_order_test_redacted_evidence_receipt.py`.
3. Confirm the no-secret scan passes.
4. Confirm `order_created=false`, `actual_order_submission_performed=false`, and both P50/P7 eligibility flags remain false.
5. Archive only the redacted receipt, validation, no-secret scan, and bridge result.

## Stop conditions

Stop immediately on any mainnet URL, `/fapi/v1/order` path, unexpected symbol, duplicate nonce, executable hash mismatch, non-empty raw response persistence, credential exposure, HTTP ambiguity, or missing redaction evidence.

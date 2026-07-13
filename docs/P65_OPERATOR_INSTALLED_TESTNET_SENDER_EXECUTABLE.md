# P65 Operator-installed Testnet Sender Executable Package

P65 defines a disabled-by-default operator-installed sender executable package for Binance Futures testnet `/fapi/v1/order/test` only.

It may use OS environment credential provider only inside the operator-side process memory boundary. Crypto_AI_System receives metadata-only request inputs and redacted JSON evidence only.

Forbidden by default: real order submit, mainnet, status polling, cancel, secret-file reads/writes, raw credential persistence, raw request/response persistence, runtime authority, live execution.

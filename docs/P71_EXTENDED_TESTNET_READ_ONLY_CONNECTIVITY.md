# P71 Extended Testnet Read-only Connectivity

Current status: partially validated; P71 is not complete.

Validated on 2026-07-12 without credentials or write calls:

- Extended Starknet Sepolia public REST reachable
- BTC-USD market status `ACTIVE`
- trading configuration present
- orderbook bid/ask levels present
- no-secret scan passed
- POST/write probe blocked locally
- order endpoint calls: zero

Endpoint alignment note:

- the directive/API documentation showed `wss://starknet.sepolia...`
- the current official Starknet Python SDK uses `wss://api.starknet.sepolia...`
- P71 follows the current SDK configuration after the non-API host returned 403;
  the corrected API host is reachable but currently returns 503

Remaining blockers:

- current official-SDK WebSocket host returns HTTP 503 after three bounded attempts
- read-only private account evidence is unavailable because no external
  credential-bearing read process has been supplied

Official SDK verification:

- `x10-python-trading-starknet==2.4.0` installed and pinned
- SDK-compatible `websockets>=12,<14` pinned
- official SDK v1 stream independently returned HTTP 503
- official SDK v2 RPC stream independently returned HTTP 404

External private read boundary:

- package: `external_runtime_packages.extended_read_only_probe`
- API key is retrieved inside that process from Windows Credential Manager
- CLI accepts only a credential target name and metadata reference ID
- only four GET paths are allowlisted: account info, balance, BTC-USD positions,
  and BTC-USD open orders
- output contains endpoint response hashes and status metadata, never API key or
  raw response values

After an operator creates the Windows Generic Credential, run the external
probe with `python -m external_runtime_packages.extended_read_only_probe.run_windows_probe`.
Do not paste the API key into chat, JSON, command arguments, screenshots, or the
Crypto_AI_System process.

The public client never accepts API-key headers. Private account reads must be
implemented through the later external credential boundary; credential values
must not enter the core process.

Evidence is generated under `storage/p71/` and is excluded from clean source
handoff packages.

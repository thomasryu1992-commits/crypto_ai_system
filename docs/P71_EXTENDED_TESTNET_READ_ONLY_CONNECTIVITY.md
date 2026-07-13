# P71 Extended Testnet Read-only Connectivity

Current status: partially validated and fail-closed. P71 remains incomplete.

## Canonical status

- public REST evidence is valid
- private account REST evidence is valid
- public WebSocket contract is hardened, but public WebSocket live evidence is pending
- private account WebSocket contract is hardened, but private account WebSocket live evidence is pending
- `p71_complete=false`
- `ready_for_signed_testnet_execution=false`
- `testnet_order_submission_allowed=false`

The public REST and external private REST evidence already obtained remain useful historical evidence, but the new P71 v3 contract requires fresh, non-replayed v3/v2 evidence before closure. Existing v1 private receipts must not be promoted as P71-complete evidence.

## Public REST requirements

The public client is restricted to the pinned Extended Starknet Sepolia endpoint and BTC-USD. It performs GET-only reads for:

- market metadata and trading rules
- BTC-USD REST orderbook

The evidence contract now requires:

- HTTP 200 and Extended `status=OK`
- active BTC-USD market
- trading configuration present
- market/rule response age at or below 60 seconds
- REST orderbook response age at or below 5 seconds
- redirect blocking (`allow_redirects=false`)
- bounded HTTP 429 handling
- `Retry-After` support
- exponential backoff with jitter when `Retry-After` is unavailable
- response and evidence hashes

## Public WebSocket requirements

Endpoint:

`wss://api.starknet.sepolia.extended.exchange/stream.extended.exchange/v1/orderbooks/BTC-USD?depth=1`

The v1 stream is path-based; no post-connect subscribe payload is sent. This
matches the Extended orderbook stream contract documented as
`GET /stream.extended.exchange/v1/orderbooks/{market}?depth=1`.

The client requires:

- first application message is `SNAPSHOT`
- first sequence is `1`
- market is `BTC-USD`
- bid and ask levels are present
- all later sequences are contiguous
- any gap forces connection disposal, bounded reconnect, and a new `SNAPSHOT seq=1`
- reconnect reason and resync evidence are recorded
- REST and WebSocket midpoint divergence remains within the configured read-session tolerance
- server timestamp and client receive timestamp produce bounded clock-offset evidence

### Heartbeat evidence semantics

Extended documents a 15-second server Ping interval and a 10-second Pong deadline. The selected `websockets` sync API automatically handles control-frame Pong responses but does not expose direct server-Ping or client-Pong counters. Therefore P71 records heartbeat evidence honestly as:

- `heartbeat_evidence_mode=INFERRED_FROM_CONNECTION_SURVIVAL`
- `server_ping_observed_directly=false`
- `client_pong_observed_directly=false`
- a minimum 27-second continuous connection-survival window

This is not represented as direct control-frame telemetry.

## External private REST boundary

Package:

`external_runtime_packages.extended_read_only_probe`

The API key is retrieved inside the external Windows process from Windows Credential Manager. The Crypto_AI_System Core process receives only redacted evidence.

Allowed REST paths:

- `/user/account/info`
- `/user/balance`
- `/user/positions?market=BTC-USD`
- `/user/orders?market=BTC-USD`

The private evidence contract requires:

- active account schema and account ID
- validated balance schema, or documented balance 404 only after active account authentication succeeds
- BTC-USD-only position and open-order scope
- response SHA-256 values
- redirect blocking
- bounded 429 handling
- fresh session timestamps and a 10-minute TTL
- unique read-session ID
- receipt SHA-256 recomputation
- recursive no-secret scanning

## Private account WebSocket boundary

Endpoint:

`wss://api.starknet.sepolia.extended.exchange/stream.extended.exchange/v1/account`

The v1 private stream is also path-based; no post-connect subscribe payload is
sent. Only the external credential-bearing process may set `X-Api-Key`. The
initial account snapshot must include the balance, positions, and orders keys.
P71 validates:

- first application message is `SNAPSHOT`
- first sequence is `1`
- initial snapshot schema
- BTC-USD market scope
- sequence continuity
- sequence-gap reconnect and snapshot resync
- 27-second inferred heartbeat-survival evidence
- server/client clock evidence
- redacted message hashes only
- REST/stream balance-presence, position-count, and open-order-count consistency

Order updates, fills, fee changes, post-submit position/balance deltas, ambiguous submit recovery, and execution reconciliation remain P76/P78 work.

## Stream host diagnostic

Use the redacted host matrix when a WebSocket attempt is blocked before the
first snapshot:

```powershell
python scripts/check_p71_extended_stream_hosts.py
python scripts/check_p71_extended_stream_hosts.py --credential-target p71_extended_read_only
python scripts/probe_p71_official_sdk_stream.py
```

The diagnostic checks the pinned `api.starknet.sepolia.extended.exchange` v1
path stream, the documented non-api testnet host, and the SDK-provided v2 RPC
candidate. It also runs the installed official SDK public orderbook stream probe
against the SDK-resolved testnet stream URL. It prints only host, mode, HTTP
status, and redacted success fields. It never sends an order, creates a
signature, or prints an API key.

As of the latest local operator check, the path and no-subscribe contract were
correct, but Extended testnet WebSocket handshakes were blocked before the first
snapshot:

- `api.starknet.sepolia.extended.exchange` v1 public/private path streams: HTTP 503
- `starknet.sepolia.extended.exchange` v1 public/private path streams: HTTP 403
- `api.starknet.sepolia.extended.exchange` v2 RPC candidate: HTTP 404
- installed official SDK public orderbook stream: HTTP 503 on the SDK-resolved
  testnet stream URL

The public Extended SDK configuration example lists the Sepolia stream URL on
the non-api host, while the installed `x10-python-trading-starknet==2.4.0`
package resolves testnet to the `api.` host. P71 now probes both host forms and
the installed SDK stream client; all currently fail before first snapshot.

In that state P71 must remain blocked, because there is no valid WebSocket
snapshot evidence to seal.

## Evidence freshness, integrity, and replay protection

Public evidence and private receipts include:

- session/evidence ID
- canonical UTC creation time
- expiry time
- maximum evidence age
- SHA-256 seal

Validators recompute the seal, reject stale evidence, reject future-dated evidence beyond the clock allowance, and optionally reject already-seen session IDs.

## Safety invariants

The P71 complete gate revalidates all of the following instead of trusting summary booleans:

- venue is Extended Starknet Sepolia
- market is BTC-USD
- public v3 and private receipt v2 versions match
- evidence hashes match canonical payloads
- evidence is fresh
- public REST, public WebSocket, private REST, and private account WebSocket are valid
- REST/WebSocket consistency checks pass
- recursive no-secret scans pass
- write-block evidence is valid
- `network_write_call_performed=false`
- `order_endpoint_called=false`
- `cancel_endpoint_called=false`
- `signature_created=false`
- `stark_private_key_accessed=false`
- `testnet_order_submission_allowed=false`

P71 does not create a signature, read a Stark private key, submit an order, cancel an order, or grant signed-testnet/live execution authority.

## Live closure and evidence promotion

The canonical next action is the operator-controlled closure flow in `docs/P71_EXTENDED_TESTNET_READ_ONLY_CLOSURE_RUNBOOK.md`.

The closure builder accepts only fresh v3 public evidence and v2 private evidence, validates source hashes and anti-replay state, enforces a maximum 180-second source-time skew, emits redacted reports, and consumes successful source evidence IDs once. A successful closure still records `ready_for_signed_testnet_execution=false` and `testnet_order_submission_allowed=false`.

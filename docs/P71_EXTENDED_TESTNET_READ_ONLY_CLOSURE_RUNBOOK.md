# P71 Extended Testnet Read-only Closure Runbook

P71 remains incomplete until fresh public and private WebSocket evidence passes the v3/v2 contracts and the closure report records `p71_complete=true`.

This runbook validates read-only connectivity only. It never enables signing, order submission, cancellation, signed-testnet promotion, or live trading.

## Prerequisites

- P71 required-fixes package applied
- Windows host for the credential-bearing private process
- Extended Starknet Sepolia read-only API key stored in Windows Credential Manager
- Python dependencies installed, including `websockets>=12,<14`
- no API-key value pasted into chat, JSON, command arguments, screenshots, logs, or the Crypto_AI_System Core process

The Core public probe never receives the API-key value. The external private process reads it from Windows Credential Manager into its own process memory only.

## One-command operator flow

From the repository root in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_p71_live_readonly_closure.ps1 `
  -CredentialTarget "<WINDOWS_GENERIC_CREDENTIAL_TARGET>" `
  -CredentialReferenceId "os_credential_ref:p71/extended/read_only" `
  -TimeoutSeconds 35
```

The credential target is a metadata reference, not the credential value.

Optional stream override:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_p71_live_readonly_closure.ps1 `
  -CredentialTarget "<WINDOWS_GENERIC_CREDENTIAL_TARGET>" `
  -CredentialReferenceId "os_credential_ref:p71/extended/read_only" `
  -TimeoutSeconds 35 `
  -StreamUrlOverride "wss://starknet.sepolia.extended.exchange/stream.extended.exchange/v1"
```

The override may also be supplied with `EXTENDED_STREAM_URL_OVERRIDE`. It is
restricted to Extended Starknet Sepolia `wss://.../stream.extended.exchange/v1`
host forms and never carries a credential.

The runner performs these steps in order:

1. public Extended Sepolia REST and BTC-USD orderbook WebSocket evidence
2. external private account REST and authenticated account WebSocket evidence
3. fresh evidence hash, TTL, scope, sequence, heartbeat, clock, and REST/WS consistency validation
4. source-time correlation check with a maximum 180-second skew
5. redacted closure report and attestation generation
6. successful evidence IDs consumed once in the append-only anti-replay registry

## Canonical outputs

Session-local evidence:

- `storage/p71/live_sessions/<operator_session_id>/public_evidence.json`
- `storage/p71/live_sessions/<operator_session_id>/private_receipt.json`
- `storage/p71/live_sessions/<operator_session_id>/closure_report.json`

Canonical redacted outputs:

- `storage/latest/p71_extended_readonly_closure_report.json`
- `storage/latest/p71_extended_readonly_attestation.json`
- `storage/latest/P71_EXTENDED_READONLY_CLOSURE_HANDOFF.md`
- `storage/registries/p71_consumed_evidence_registry.jsonl`

Raw source payloads and credential values are never copied into the closure report or attestation.

## Success criteria

All of the following must be true:

```text
status=P71_EXTENDED_READONLY_CLOSURE_COMPLETE
p71_complete=true
public_rest_valid=true
public_websocket_valid=true
private_account_rest_valid=true
private_account_websocket_valid=true
closure_evidence_consumed=true
```

Safety remains unchanged after success:

```text
ready_for_signed_testnet_execution=false
testnet_order_submission_allowed=false
external_order_submission_allowed=false
external_order_submission_performed=false
place_order_enabled=false
cancel_order_enabled=false
signed_order_executor_enabled=false
```

P71 closure is connectivity evidence, not execution permission.

## Failure handling

A blocked closure report is expected when the upstream WebSocket endpoint returns 503, a sequence gap cannot resynchronize, the heartbeat-survival window is incomplete, evidence is stale, hashes are invalid, source evidence is replayed, REST/WS state mismatches, or the public and private source times differ by more than 180 seconds.

For host/path diagnosis, run:

```powershell
python scripts/check_p71_extended_stream_hosts.py
python scripts/check_p71_extended_stream_hosts.py --credential-target p71_extended_read_only
python scripts/check_p71_extended_stream_hosts.py --stream-url-override "wss://starknet.sepolia.extended.exchange/stream.extended.exchange/v1"
python scripts/probe_p71_official_sdk_stream.py
```

The checker is redacted and read-only. It distinguishes:

- pinned v1 path stream returning HTTP 502/503
- documented non-api testnet host returning HTTP 403
- SDK v2 RPC candidate returning HTTP 404
- installed official SDK public orderbook stream returning HTTP 503

The public and private probes now record stream endpoint source, host, HTTP
status, and failure reason for every attempted candidate. Public REST fallback
market data may be recorded for later operations work, but it is not accepted as
P71 WebSocket closure evidence.

If all WebSocket candidates are blocked before the first snapshot, do not treat
the failure as missing local evidence. Keep P71 blocked and rerun after the
upstream stream endpoint becomes available.

Do not manually edit evidence files to force completion. Generate a new operator session and rerun.

## Public-only GitHub Actions probe

The `p71-public-live-probe` workflow is manual (`workflow_dispatch`) and uses no repository secrets. It can recheck the public Extended REST/WebSocket endpoint and upload a redacted evidence artifact. It cannot complete P71 because private evidence must remain in the external Windows credential-bearing process.

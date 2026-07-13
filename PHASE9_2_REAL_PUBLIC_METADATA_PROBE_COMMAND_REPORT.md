# Phase 9.2 Real Public Metadata Probe Command / No Order Submit

This package adds a real public metadata probe command lane for Phase 9.2.

## Scope

- Public testnet metadata endpoints only.
- No order submit endpoint.
- No order status endpoint.
- No cancel endpoint.
- No private account, balance, or position endpoint.
- No API key value, API secret value, private key, passphrase, signature, or signed request.
- No executor enablement and no runtime settings mutation.

## Default behavior

The default command only generates the command template and result report. It does not execute network calls.

```powershell
python .\scripts\run_phase9_2_real_public_metadata_probe_command.py
```

The optional public-only network probe command is:

```powershell
python .\scripts\run_phase9_2_real_public_metadata_probe_command.py --execute-public-metadata-probe
```

This optional command is still no-order-submit and public-metadata-only.

## Safety posture

- `real_testnet_submit_may_begin=false`
- `actual_order_submission_performed=false`
- `order_endpoint_called=false`
- `order_status_endpoint_called=false`
- `cancel_endpoint_called=false`
- `private_account_endpoint_called=false`
- `signature_created=false`
- `signed_request_created=false`

Validated public metadata is evidence only. It does not unlock real testnet order submission.

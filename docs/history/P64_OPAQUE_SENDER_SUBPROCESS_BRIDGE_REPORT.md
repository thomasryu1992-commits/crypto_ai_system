# P64 Opaque Sender Subprocess Bridge Report

## Status

`P64_OPAQUE_SENDER_SUBPROCESS_BRIDGE_VALIDATED_REVIEW_ONLY_DISABLED`

## Completed

- Implemented a hardened subprocess boundary between P63 and an operator-installed sender program.
- Added absolute launcher/program path and SHA256 attestation.
- Enforced fixed argv, `shell=false`, minimal environment, disabled stdin, timeout, and output-size guards.
- Added metadata-only `0600` request-file IPC with cleanup after execution.
- Enforced one redacted JSON object on stdout and empty stderr.
- Added P63 source/request, P61 request, operator confirmation, and one-shot nonce hash bindings.
- Added no-network ephemeral sender-program self-test.
- Added fail-closed negative fixtures.
- Kept `POST /fapi/v1/order` permanently disabled.

## Not Performed

- No API key value was read.
- No API secret value was read.
- No secret file was read or created.
- No concrete sender program was bundled.
- No concrete signer was bundled.
- No signature was created.
- No HTTP request was sent.
- No `/fapi/v1/order/test` endpoint was called.
- No order was submitted.
- No P7 evidence was imported.
- No runtime authority was granted.

## Safety State

```text
p64_opaque_sender_subprocess_bridge_enabled=false
p64_subprocess_execution_enabled=false
p64_sender_program_injection_enabled=false
p64_concrete_network_sender_program_included=false
p64_external_runtime_network_calls_enabled=false
p64_external_runtime_signing_enabled=false
p64_order_test_endpoint_call_enabled=false
p64_order_test_endpoint_call_performed=false
p64_real_order_submit_enabled=false
p64_real_order_endpoint_called=false
http_request_sent=false
signature_created=false
secret_value_accessed=false
actual_order_submission_performed=false
```

## Next Boundary

The next meaningful action is not another internal review wrapper. It is installing a separately built sender program on the operator PC, validating its executable hash and testnet-only policy, then performing one separately approved `/fapi/v1/order/test` run. Until that external component and approval exist, all runtime flags remain false.

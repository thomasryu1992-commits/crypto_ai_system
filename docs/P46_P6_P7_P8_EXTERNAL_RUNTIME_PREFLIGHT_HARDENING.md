# P46 - P6/P7/P8 External Runtime Preflight Hardening

Date: 2026-07-09
Base package: `crypto_ai_system_p46_p45_closure_alignment_patched.zip`
Output posture: review-only / no-submit / signed-testnet-evidence-preparation

## Purpose

P46 stops expanding external review wrappers and starts tightening the first real signed-testnet evidence path:

```text
P6 external local runtime preflight
-> P7 real post-submit evidence intake
-> P8 repeated clean signed-testnet session validation
```

This patch does not submit orders, does not call endpoints, does not create signatures, and does not access secret values.

## P6 hardening

P6 now records:

- `adapter_boundary_evidence`
- `adapter_boundary_validation`
- `external_runtime_preflight_report`
- `storage/latest/p6_external_runtime_preflight_report.json`

The adapter boundary requires:

- testnet environment only
- BTCUSDT-only symbol scope
- disabled adapter available in review package
- real endpoint adapter only in separate local runtime
- no submit-by-default behavior
- process-memory-only request signing location
- no secret values accepted by the report
- no secret values logged by adapter
- idempotency key support
- duplicate submit lock support
- post-submit relock support
- redacted evidence export support

## P7 hardening

P7 order ID intake now requires:

- real signed-testnet external-runtime evidence origin
- request hash
- exchange response hash
- redacted response path
- hot-path PreOrderRiskGate ID/hash
- secret reference ID
- key fingerprint SHA-256
- no-secret-logged evidence hash

P7 rejects mock, fixture, synthetic, sample, fake, dummy, or mainnet-scoped evidence as real post-submit evidence.

## P8 hardening

P8 session evidence now requires:

- `evidence_origin=real_signed_testnet_external_runtime`
- `session_evidence_source=p7_real_post_submit_evidence`
- redacted evidence bundle hash
- `p7_real_evidence_validated=true`
- fixture/mock/synthetic markers all false

This prevents fixture-based repeated sessions from being promoted into real signed-testnet validation.

## Generated latest artifacts

```text
storage/latest/p6_single_signed_testnet_submit_runtime_action_report.json
storage/latest/p6_external_runtime_preflight_report.json
storage/latest/p7_post_submit_evidence_intake_report.json
storage/latest/p8_repeated_clean_signed_testnet_sessions_report.json
```

## Default safety state

```text
actual_testnet_order_submitted=false
actual_live_order_submitted=false
order_endpoint_called=false
http_request_sent=false
signature_created=false
signed_request_created=false
secret_value_accessed=false
runtime_scheduler_enabled=false
live_canary_execution_enabled=false
live_scaled_execution_enabled=false
```

## Next step

The next development step is a separately packaged local-runtime connector design for the real signed-testnet adapter. It must still fail closed before any endpoint call unless operator arming phrase, testnet-only key metadata, hot-path risk gate freshness, duplicate-submit lock, idempotency key, and preflight validations are all valid.

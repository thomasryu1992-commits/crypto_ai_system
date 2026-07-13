# P58 — External Runtime Signed-Testnet Evidence Acquisition Boundary

## Purpose
P58 moves beyond P7 review-wrapper expansion and implements the package-side execution boundary needed to acquire one future redacted signed-testnet evidence bundle from a separate local runtime.

The implemented code path is:

```text
P6 external runtime preflight
        ↓
P48 external adapter connector contract
        ↓
P58 external runtime runner
        ↓
external adapter protocol
        ↓
redacted evidence exporter
        ↓
no-secret scan
        ↓
P49/P7-compatible evidence handoff candidate
```

## Current Package Boundary
The review package contains:

- an external-runtime runner orchestration class;
- an external adapter protocol;
- an external adapter manifest contract;
- a no-network fixture adapter;
- a redacted evidence exporter;
- a no-secret scan path;
- a P7 bridge candidate exporter;
- fail-closed negative fixtures.

The review package does **not** contain:

- a Binance or other real exchange write client;
- a real adapter implementation;
- API key or API secret readers;
- secret files;
- a request signer;
- an enabled submit path;
- an enabled external-runtime runner.

## Validated Self-test Path
P58 exercises the real runner, adapter protocol, exporter, scanner, and manifest code path only under:

```text
operation_scope=p58_no_network_evidence_acquisition_self_test
```

The fixture adapter is explicitly marked:

```text
fixture_only=true
real_endpoint_adapter=false
network_call_capable=false
submit_enabled_by_default=false
```

All exported evidence is explicitly marked:

```text
real_signed_testnet_evidence=false
p7_import_eligible=false
fixture_evidence=true
```

## Real Acquisition Path
The future real path is reserved as:

```text
operation_scope=signed_testnet_real_evidence_acquisition
```

It remains disabled and raises a fail-closed exception until all of the following exist outside the review package:

1. a separately packaged testnet-only adapter implementation;
2. metadata-only secret reference and key fingerprint;
3. process-memory-only signing at operator runtime;
4. fresh P6 preflight evidence;
5. P48 connector hash match;
6. P49 redacted evidence schema match;
7. fresh hot-path PreOrderRiskGate evidence;
8. duplicate-submit lock and idempotency evidence;
9. a separate explicit operator submit approval;
10. one-order and low-notional constraints.

## Exported Self-test Artifacts
The ephemeral no-network self-test writes:

```text
p58_redacted_submit_response_bundle_NO_NETWORK_SELF_TEST.json
p58_external_runtime_execution_transcript_NO_NETWORK_SELF_TEST.json
p58_no_secret_log_scan_report_NO_NETWORK_SELF_TEST.json
p58_p7_intake_bridge_candidate_NO_NETWORK_SELF_TEST.json
p58_redacted_evidence_export_manifest_NO_NETWORK_SELF_TEST.json
```

The temporary directory is deleted after validation and is not packaged.

## Safety State

```text
external_runtime_runner_enabled=false
external_runtime_real_adapter_loaded=false
external_runtime_real_acquisition_enabled=false
external_runtime_real_acquisition_executed=false
real_signed_testnet_evidence_present=false
redacted_real_signed_testnet_evidence_exported=false
actual_p7_import_ready=false
p7_importer_enabled=false
actual_order_submission_performed=false
order_endpoint_called=false
http_request_sent=false
signature_created=false
secret_value_accessed=false
runtime_mutation_performed=false
live_canary_execution_enabled=false
live_scaled_execution_enabled=false
```

## Next Meaningful Progress
P58 is the last package-side preparation step before external-runtime adapter implementation. The next step should not add another P7 wrapper. It should create a **separate, testnet-only external adapter package** with a disabled-by-default runner and metadata-only secret binding. A real signed-testnet order still requires separate explicit operator approval and must not be submitted by the review package.

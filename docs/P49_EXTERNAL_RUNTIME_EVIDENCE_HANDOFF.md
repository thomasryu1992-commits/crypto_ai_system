# P49 External Runtime Evidence Handoff Skeleton

Status: `P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_READY_REVIEW_ONLY_NO_SUBMIT`

P49 defines the redacted evidence handoff shape required after a separately approved local runtime performs one signed testnet order submit. It does not attach a real adapter, read secrets, create signatures, send HTTP requests, or submit orders.

## Purpose

P48 created the metadata-only local-runtime adapter connector boundary. P49 adds the post-submit handoff skeleton that a separate local runtime must fill before P7 can validate real post-submit evidence.

The handoff includes:

- Redacted submit response bundle template
- External runtime execution transcript schema
- No-secret log scan template
- P7 intake bridge template
- Negative fixture results for unsafe handoff cases

## Runtime boundary

The review package remains no-submit:

```text
actual_order_submission_performed=false
actual_testnet_order_submitted=false
order_endpoint_called=false
order_status_endpoint_called=false
cancel_endpoint_called=false
http_request_sent=false
signature_created=false
signed_request_created=false
secret_value_accessed=false
runtime_scheduler_enabled=false
live_canary_execution_enabled=false
live_scaled_execution_enabled=false
```

## Required external-runtime evidence after actual submit

The separate local runtime must export redacted artifacts only:

```text
p6_submitted_report_redacted.json
redacted_submit_response_bundle.json
external_runtime_execution_transcript.json
no_secret_log_scan_report.json
status_polling_evidence.json
cancel_boundary_evidence.json
signed_testnet_reconciliation_evidence.json
signed_testnet_session_close_evidence.json
```

Required hash chain:

```text
p6_single_signed_testnet_submit_runtime_action_sha256
p48_local_runtime_adapter_connector_sha256
request_hash
exchange_response_hash
status_polling_hash_chain_sha256
reconciliation_evidence_sha256
session_close_evidence_sha256
no_secret_logged_evidence_hash
```

## Promotion rule

P49 cannot promote P7/P8/P9/P10. It only prepares the skeleton. P7 may validate real evidence only after a separately approved external runtime submit. P8 still requires repeated clean signed testnet sessions before any live canary preparation can move forward.

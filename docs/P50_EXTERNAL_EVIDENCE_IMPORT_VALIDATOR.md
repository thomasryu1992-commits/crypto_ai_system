# P50 External Evidence Import Validator

Status: `P50_EXTERNAL_EVIDENCE_IMPORT_VALIDATOR_READY_REVIEW_ONLY_NO_SUBMIT`

P50 adds a review-only validator between the P49 external-runtime evidence handoff skeleton and P7 post-submit evidence intake.

## Purpose

P49 defines what a separately approved local runtime must export after a real signed-testnet submit. P50 validates the import boundary before any redacted evidence is shaped for P7.

P50 does not submit orders, call endpoints, create signatures, read secrets, or mark P7 valid. It creates only:

- import manifest template
- P7 input preview template
- schema/hash/path/no-secret validators
- negative fixture report
- registry/summary artifacts

## Required import checks

The validator fails closed unless all relevant imported evidence satisfies:

- evidence origin is `real_signed_testnet_external_runtime`
- environment is `testnet`
- venue is `binance_futures_testnet`
- symbol is `BTCUSDT`
- order count is one
- exchange order id does not look mock/fixture/sample/synthetic/dummy/fake
- request hash and response hash are SHA256-shaped
- hot-path PreOrderRiskGate id/hash are present
- secret reference id is metadata-only
- key fingerprint is SHA256-shaped
- no-secret log scan report passed
- status polling, cancel boundary, reconciliation, and session close hashes are present
- import paths are relative and under approved external-runtime evidence roots
- no raw request body, raw signed payload, raw exchange payload, unredacted exchange response, or secret value is present

## Output boundary

P50 may build a P7 input preview. It must not:

- execute P7 intake
- write P7 valid status
- promote P8/P9/P10 readiness
- grant signed-testnet, live canary, or live scaled authority

## Required latest artifacts

```text
storage/latest/p50_external_evidence_import_validator_report.json
storage/latest/p50_external_evidence_import_manifest_TEMPLATE_NO_SUBMIT.json
storage/latest/p50_p7_import_preview_TEMPLATE_NO_SUBMIT.json
storage/latest/p50_external_evidence_import_validator_negative_fixture_results.json
storage/latest/p50_external_evidence_import_validator_summary.json
storage/latest/p50_external_evidence_import_validator_registry_record.json
```

## Next phase

P51 should add a P7 import bridge dry-run that consumes a P50-validated P7 input preview and verifies that P7 would accept or reject the evidence without writing runtime authority or submitting an order.

# P38 Operator Support Bundle / Troubleshooting Export Pack Report

Status: review-only support bundle export layer.

This phase aggregates P37 self-diagnosis, P36 onboarding wizard, P35 runbook, P34 command response snapshots, and P33 router validation artifacts into a redacted troubleshooting support bundle.

It does not enable runtime, scheduler, live/testnet order submission, endpoint calls, secret access, settings mutation, score-weight mutation, or auto-promotion.

Expected artifacts:

- `storage/latest/p38_operator_support_bundle_report.json`
- `storage/latest/p38_operator_support_bundle_summary.json`
- `storage/latest/p38_operator_support_bundle_pack.json`
- `storage/latest/p38_operator_support_bundle_manifest.json`
- `storage/latest/p38_operator_support_bundle_manifest.csv`
- `storage/latest/p38_operator_support_bundle.md`
- `storage/latest/p38_operator_support_bundle_share_packet.json`
- `storage/latest/p38_operator_support_bundle_paths.txt`
- `storage/latest/p38_operator_support_bundle_negative_fixture_results.json`
- `storage/latest/p38_operator_support_bundle_registry_record.json`

Allowed operator commands remain read-only: `status`, `matrix`, `waiting`, `no_go`, and `export_paths`.

Blocked command families remain: `enable`, `start`, `submit`, `order`, `live`, `trade`, `activate`, `scheduler`, `place`, `cancel`, and `runtime`.

# P20 External Evidence Template Generator / CI Artifact Export Pack

Status: review-only template/export pack layer.

This phase generates Docker build, Docker run self-test, and Launcher import external evidence templates for P19. It does not execute Docker, mutate Launcher state, enable a scheduler, call order endpoints, or access secrets.

Primary command:

```bash
PYTHONPATH=src:. python scripts/export_p20_ci_artifact_pack.py --print-paths
```

Generated latest artifacts:

- `storage/latest/p19_docker_build_evidence_external_TEMPLATE.json`
- `storage/latest/p19_docker_run_self_test_evidence_external_TEMPLATE.json`
- `storage/latest/p19_launcher_import_evidence_external_TEMPLATE.json`
- `storage/latest/p20_ci_artifact_export_manifest.json`
- `storage/latest/p20_ci_artifact_export_pack_review_only.zip`
- `storage/latest/p20_external_evidence_template_export_pack_report.json`
- `storage/latest/p20_external_evidence_template_export_pack_summary.json`
- `storage/latest/p20_external_evidence_template_export_pack_negative_fixture_results.json`
- `storage/latest/p20_external_evidence_template_export_pack_registry_record.json`

Runtime posture remains fail-closed:

- `limited_live_scaled_auto_trading_allowed=false`
- `live_scaled_execution_enabled=false`
- `live_order_submission_allowed=false`
- `runtime_scheduler_enabled=false`
- `order_endpoint_called=false`
- `secret_value_accessed=false`

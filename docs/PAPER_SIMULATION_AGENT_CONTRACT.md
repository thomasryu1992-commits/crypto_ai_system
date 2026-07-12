# Paper Simulation Agent Contract

Version: 0.286.0-agent.11
Contract: `paper_simulation_review_v1`

This document defines the Crypto AI System Agent Package wrapper contract for the `paper` command.

## Scope

`paper` creates a review-only paper simulation artifact for Thomas Agent OS. It is not a live, signed testnet, or exchange execution path.

The command may be used for local review and future paper-pipeline handoff, but this wrapper must not create real order intents, call exchange adapters, submit orders, poll order status, cancel orders, read secrets, create signed requests, or mutate runtime settings.

## Required stdout fields

The final stdout line must remain JSON and include:

- `artifact_type: paper_simulation`
- `artifact_format: markdown`
- `paper_simulation_contract_version: paper_simulation_review_v1`
- `paper_session_id`
- `paper_run_id`
- `simulation_scope_id`
- `source_artifact_sha256`
- `approval_required: true`
- `approval_satisfied_for_local_launcher_command`
- `approval_grants_real_execution: false`
- `paper_order_submission_performed: false`
- `paper_execution_adapter_called: false`
- `order_intent_created: false`
- `execution_permission_granted: false`
- `stage_transition_allowed: false`
- `live_candidate_eligible: false`
- `signed_testnet_candidate_eligible: false`
- `order_endpoint_called: false`
- `order_status_endpoint_called: false`
- `cancel_endpoint_called: false`
- `exchange_adapter_called: false`
- `signed_request_created: false`
- `secret_value_accessed: false`
- `runtime_settings_mutated: false`
- artifact registry fields: `artifact_id`, `artifact_sha256`, `artifact_metadata_path`, `artifact_metadata_sha256`, `artifact_index_path`, `latest_pointer_path`

## Approval semantics

`paper` remains an approval-required command in `config/command_map.json` and `agent_manifest.json`.

Dry-run mode may satisfy the local command wrapper check for testing, but this does not grant real execution permission. Approved paper mode still remains a review-only wrapper unless a later internal paper pipeline produces separate auditable paper execution evidence.

## Safety invariants

These values must remain false:

- `real_order_execution_allowed`
- `paper_order_submission_performed`
- `paper_execution_adapter_called`
- `order_intent_created`
- `execution_permission_granted`
- `stage_transition_allowed`
- `signed_testnet_candidate_eligible`
- `live_candidate_eligible`
- `order_endpoint_called`
- `order_status_endpoint_called`
- `cancel_endpoint_called`
- `exchange_adapter_called`
- `signed_request_created`
- `secret_value_accessed`
- `secret_file_read`
- `runtime_settings_mutated`
- `score_weights_mutated`

## Launcher boundary

Thomas Agent OS may route `/run crypto paper` to this package entrypoint. The Launcher owns routing, approval UX, registry updates, and Telegram response formatting. The Crypto AI System ZIP owns the command contract and generated artifacts only.

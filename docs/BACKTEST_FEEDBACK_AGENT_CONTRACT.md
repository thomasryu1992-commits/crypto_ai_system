# Backtest / Feedback Agent Artifact Contract

Version: 0.286.0-agent.11

This document defines the package-owned contract for the `backtest` and `feedback` commands in Thomas Agent OS Local Launcher mode.

## Scope

The commands are review-only wrappers. They may create Markdown artifacts under `data/reports`, but they must not submit orders, open positions, poll live order status, read secrets, or mutate runtime settings.

## Backtest artifact

`python scripts/run_command.py --command backtest --dry-run` creates a Markdown artifact whose stdout final JSON includes:

```json
{
  "artifact_type": "backtest",
  "artifact_format": "markdown",
  "backtest_contract_version": "backtest_review_v1",
  "backtest_id": "<stable id>",
  "source_artifact_sha256": "<sha256>",
  "historical_data_only": true,
  "review_only": true,
  "execution_permission_granted": false,
  "stage_transition_allowed": false
}
```

The wrapper output is not signed-testnet or live execution evidence. Metrics remain placeholder/not-computed unless an internal validated historical dataset is supplied by the research/backtest pipeline.

## Feedback artifact

`python scripts/run_command.py --command feedback --dry-run` creates a Markdown artifact whose stdout final JSON includes:

```json
{
  "artifact_type": "feedback",
  "artifact_format": "markdown",
  "feedback_contract_version": "feedback_review_v1",
  "feedback_cycle_id": "<stable id>",
  "outcome_review_id": "<stable id>",
  "source_artifact_sha256": "<sha256>",
  "runtime_mutation_allowed": false,
  "review_only": true,
  "execution_permission_granted": false,
  "stage_transition_allowed": false
}
```

Feedback may create reports, review notes, and future candidate drafts only. It must not directly change score weights, settings, risk limits, or execution state.

## Safety invariants

These values must remain false in command output and artifacts:

```text
live_trading_enabled=false
order_execution_enabled=false
auto_position_open_enabled=false
withdrawal_enabled=false
fund_transfer_enabled=false
execution_permission_granted=false
stage_transition_allowed=false
order_endpoint_called=false
secret_value_accessed=false
```

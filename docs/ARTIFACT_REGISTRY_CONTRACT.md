# Artifact Registry Contract

Version: 0.286.0-agent.11

This Crypto AI System Agent Package writes every command artifact with a package-owned registry contract. The Launcher does not need to infer artifact metadata from filenames alone.

## Scope

Commands covered:

- `daily`
- `scan`
- `signal`
- `backtest`
- `paper`
- `feedback`

Every successful command keeps stdout final-line JSON and adds hash-backed artifact registry fields.

## Files Written

For each generated artifact:

```text
<data/reports>/<artifact file>
<data/reports>/<artifact file>.metadata.json
<data/reports>/artifact_index.json
<data/reports>/latest/latest_<command>.json
```

If `--output-dir` is provided, the same structure is written under that output directory.

## stdout JSON Required Fields

Successful command responses include:

```json
{
  "artifact_id": "24-char deterministic id",
  "artifact_sha256": "64-char sha256",
  "artifact_metadata_path": "...metadata.json",
  "artifact_metadata_sha256": "64-char sha256",
  "artifact_index_path": "artifact_index.json",
  "latest_pointer_path": "latest/latest_<command>.json",
  "artifact_registry_updated": true,
  "review_only": true,
  "execution_permission_granted": false,
  "stage_transition_allowed": false
}
```

## Sidecar Metadata

The sidecar uses:

```text
sidecar_contract_version: agent_artifact_metadata_v1
artifact_registry_contract_version: agent_artifact_registry_v1
```

It records command, artifact type, format, job id, dry-run status, artifact path, artifact hash, and safety flags.

## Artifact Index

`artifact_index.json` uses:

```text
artifact_index_contract_version: agent_artifact_index_v1
```

It keeps recent artifact records and is package-owned. It does not grant execution authority.

## Latest Pointer

`latest/latest_<command>.json` uses:

```text
latest_pointer_contract_version: agent_artifact_latest_pointer_v1
```

It points to the latest artifact for a command and includes the same safety invariants.

## Safety Invariants

The registry and all pointers remain review-only:

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

Artifact registry entries are evidence of local command output only. They must not be interpreted as signed testnet or live order permission.

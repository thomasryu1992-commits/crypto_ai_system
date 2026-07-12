# Step317 Deployment Runbook Report

Status: review-only / deployment-disabled / live-execution-disabled.

Step317 adds `src/crypto_ai_system/execution/deployment_runbook.py`, `docs/DEPLOYMENT_RUNBOOK_STEP317.md`, runtime runbook manifest generation, and append-only `deployment_runbook_registry.jsonl` evidence. The runbook covers environment setup, metadata-only secret injection, process start/stop, manual kill switch, log paths, backup paths, incident response, rollback, daily review, and disabled runtime guards.

Safety invariants remain disabled: no server deployment, no process start/stop, no systemd/docker writes, no `.env` writes, no secret file reads/creation, no API key/secret value access, no testnet/live order submission, no `place_order`, no `cancel_order`, no settings mutation, no score-weight mutation, no external notification send, and no automatic promotion.

# Crypto AI System Agent OS Import Compatibility

This package is structured so Thomas Agent OS Local Launcher can import it, but the package does not implement the Launcher itself.

## Package-owned compatibility files

```text
agent_manifest.json
agent_import_manifest.json
config/defaults.json
config/command_map.json
scripts/run_command.py
scripts/self_test.py
scripts/validate_package.py
scripts/build_agent_os_release.py
scripts/validate_agent_os_import_package.py
```

## Launcher-owned responsibilities

The following remain outside this ZIP and belong to Thomas Agent OS Local Launcher:

```text
agents_zip_inbox scanning
0_IMPORT_ZIP.bat orchestration
agents_installed/current promotion or rollback
agent_registry.json mutation
Telegram routing and /status rendering
duplicate import policy
```

## Local validation commands

```bash
python scripts/validate_package.py
python scripts/self_test.py
python scripts/validate_agent_os_import_package.py
python scripts/build_agent_os_release.py --write-manifest-only --skip-self-test
```

## Release ZIP command

```bash
python scripts/build_agent_os_release.py --output-dir /path/to/out
```

The generated ZIP must contain exactly one top-level folder: `crypto_ai_system/`.

## Safety posture

The Agent Package contract does not grant trading permission. The following remain false:

```text
live_trading_enabled=false
order_execution_enabled=false
auto_position_open_enabled=false
withdrawal_enabled=false
fund_transfer_enabled=false
execution_permission_granted=false
stage_transition_allowed=false
```

The `live`, `execute_order`, `place_order`, `withdraw`, and `transfer` command families remain blocked in Local Launcher mode.

## Package-Owned Artifact Registry

Crypto AI System writes sidecar metadata, `artifact_index.json`, and `latest/latest_<command>.json` for each successful command. The Launcher may read these files after command completion, but the Launcher remains responsible for import, registry mutation, Telegram routing, and display.

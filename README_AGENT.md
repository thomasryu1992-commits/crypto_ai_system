# Crypto AI System Agent Package

## Agent ID

`crypto_ai_system`

## Version

`0.286.0-agent.14`

## Description

Crypto market data collection, research, signal generation, backtesting, paper trading, review-only execution readiness, and feedback agent for Thomas Agent OS.

This package is designed to be imported by Thomas Agent OS Local Launcher. It is safe by default: live trading, real order execution, automatic position opening, withdrawal, and fund transfer are disabled.

## Supported Commands

- `daily`
- `scan`
- `signal`
- `backtest`
- `paper`
- `feedback`

## MVP Required Commands

- `daily`
- `scan`

## Required API Keys

- `OPENAI_API_KEY`

The Local Launcher may inject API keys from `config/settings.simple.json`. Do not place API keys inside this ZIP.

## Optional API Keys

- `COINALYZE_API_KEY`
- `BINANCE_API_KEY`
- `BINANCE_API_SECRET`
- `OPENROUTER_API_KEY`
- `GEMINI_API_KEY`
- `GROQ_API_KEY`

## Safety Defaults

- `live_trading_enabled: false`
- `order_execution_enabled: false`
- `auto_position_open_enabled: false`
- `withdrawal_enabled: false`
- `fund_transfer_enabled: false`
- `paper_trading_enabled: true`

## Local Launcher Notes

Use Thomas Agent OS commands such as:

```text
/run crypto daily
/run crypto scan BTC
```

The standard entrypoint is:

```bash
python scripts/run_command.py --command daily --dry-run
python scripts/run_command.py --command scan --symbol BTC --dry-run
```

The last stdout line is always a JSON result object for the Local Launcher Telegram Operator.

Live trading is disabled in Local Launcher MVP. Commands such as `live`, `execute_order`, `place_order`, `withdraw`, and `transfer` are blocked by the package wrapper.

## Docker / Agent OS Attach Mode

This package now includes a minimal Docker attach layer for Thomas Agent OS launched mode.
It does not convert Crypto AI System into a Docker-only project. The Python package, standard `scripts/run_command.py` entrypoint, self-test, and Local Launcher JSON contract remain the canonical interface.

Included Docker files:

- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`
- `scripts/docker_smoke.py`

Safe Docker commands:

```bash
# Build container image
docker compose build crypto_ai_system

# Run package self-test inside container
docker compose --profile self-test run --rm crypto_ai_system_self_test

# Run daily dry-run inside container
docker compose --profile manual run --rm crypto_ai_system --command daily --dry-run

# Run BTC scan dry-run inside container
docker compose --profile manual run --rm crypto_ai_system --command scan --symbol BTC --dry-run
```

Docker safety constraints:

- No API keys are baked into the image.
- No `env_file` is used by the provided compose file.
- `.env`, `.env.*`, `secrets.json`, `api_keys.json`, and private key files are excluded by `.dockerignore`.
- Live trading remains disabled.
- Real order execution remains disabled.
- The default container command is `daily --dry-run`.
- Docker mode is an adapter for Thomas Agent OS, not execution permission.

## Thomas Agent OS Import Compatibility

This package provides the Crypto AI System side of the Agent Package contract only.

Included package-owned compatibility files:

- `agent_import_manifest.json`
- `scripts/build_agent_os_release.py`
- `scripts/validate_agent_os_import_package.py`

Expected external flow, owned by Thomas Agent OS Local Launcher:

```text
crypto_ai_system_v*.zip -> agents_zip_inbox -> 0_IMPORT_ZIP.bat -> self-test -> agents_installed/crypto_ai_system/current -> Telegram /run crypto daily
```

This ZIP does not implement the Launcher import manager, registry mutation, Telegram router, duplicate import policy, or rollback policy.

## Artifact Contracts

- `daily` and `scan` create Markdown report artifacts using `agent_report_v2`.
- `signal` creates a ResearchSignal v2 JSON artifact using `research_signal_v2_agent_package_contract`.
- `backtest` creates a review-only Markdown artifact using `backtest_review_v1`.
- `feedback` creates a review-only Markdown artifact using `feedback_review_v1`.

Backtest and feedback outputs are review-only. They do not create order intents, submit orders, poll order status, read secrets, mutate runtime settings, or grant stage transition authority.

## Package Boundary

This ZIP is the Crypto AI System Agent Package only. It provides the manifest, command entrypoint,
self-test, package validation, safe defaults, and optional Docker attach files required by Thomas
Agent OS. It does not implement the Launcher itself, `0_IMPORT_ZIP.bat`, global registry mutation,
Telegram routing, duplicate import policy, or rollback logic. Those remain Thomas Agent OS Local
Launcher responsibilities.

See `docs/AGENT_PACKAGE_BOUNDARY.md`.

## Artifact Registry

Every successful command writes a command artifact plus package-owned tracking files under `data/reports` or the supplied `--output-dir`:

```text
<artifact file>
<artifact file>.metadata.json
artifact_index.json
latest/latest_<command>.json
```

The stdout final-line JSON includes `artifact_id`, `artifact_sha256`, `artifact_metadata_path`, `artifact_index_path`, and `latest_pointer_path`. These fields are for Launcher/Telegram display and audit convenience only. They do not grant signed testnet or live execution permission.

## Paper Simulation Contract

The `paper` command emits a review-only `paper_simulation_review_v1` artifact. It remains approval-required and does not create order intents, call exchange adapters, or grant execution permission. See `docs/PAPER_SIMULATION_AGENT_CONTRACT.md`.


## Source Health

`source-health` generates a review-only source health JSON artifact. Price data is hard-required; optional missing sources are marked `neutral_due_to_missing`. This command never grants execution permission. See `docs/SOURCE_HEALTH_AGENT_CONTRACT.md`.


## Local Price CSV Dry-Run

`source-health` can inspect local OHLCV CSV files under `data/price_data` using the `price_csv_ohlcv_v1` schema. Required columns are `timestamp,symbol,open,high,low,close,volume`.

Sample, fixture, mock, synthetic, or fallback CSV files remain review-only and block candidate eligibility. A fresh real local CSV may set `price_data_connected=true` for reporting, but it still does not grant execution permission or stage transition authority.

See `docs/LOCAL_PRICE_DATA_DRY_RUN_CONTRACT.md`.

## Price Feature Snapshot Lineage

When a fresh, schema-valid, non-sample local OHLCV CSV is available, `source-health` creates a review-only `price_feature_snapshot_v1` lineage record:

```text
data_snapshot_id -> feature_snapshot_id -> feature_matrix_sha256 -> research_signal_id
```

Sample, stale, invalid, fallback, mock, or synthetic CSV inputs set `feature_snapshot_created=false` and remain blocked for signed testnet/live candidacy. See `docs/PRICE_FEATURE_SNAPSHOT_CONTRACT.md`.

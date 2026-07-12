# Crypto AI System Agent OS Docker Attach Guide

## Purpose

This guide describes the Docker attach layer added for Thomas Agent OS launched mode.

The goal is not to rebuild Crypto AI System as a Docker-only service. The goal is to keep the existing Agent Package interface and add a container runtime wrapper that Thomas Agent OS can build, self-test, and run safely.

## Added files

- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`
- `scripts/docker_smoke.py`

## Safe commands

```bash
docker compose build crypto_ai_system
docker compose --profile self-test run --rm crypto_ai_system_self_test
docker compose --profile manual run --rm crypto_ai_system --command daily --dry-run
docker compose --profile manual run --rm crypto_ai_system --command scan --symbol BTC --dry-run
```

## Runtime contract

The container uses the same standard entrypoint as the Agent Package:

```text
python scripts/run_command.py
```

The final stdout line remains a JSON object. Thomas Agent OS can continue parsing the final line exactly as it does in non-Docker Local Launcher mode.

## Safety constraints

- `live_trading_enabled=false`
- `order_execution_enabled=false`
- `auto_position_open_enabled=false`
- `withdrawal_enabled=false`
- `fund_transfer_enabled=false`
- No private order endpoint calls
- No status/cancel endpoint calls
- No secret value reads
- No `.env` or secret files included in the image build context

## Artifact persistence

The compose file mounts:

```text
./data/reports:/app/crypto_ai_system/data/reports
./storage:/app/crypto_ai_system/storage
```

This keeps generated reports and review-only storage artifacts available to the host Agent OS.

## Validation

Run the static Docker attach validator:

```bash
python scripts/docker_smoke.py
```

Run the full Agent Package validator:

```bash
python scripts/validate_package.py
```

Run import self-test:

```bash
python scripts/self_test.py
```

All three commands must end with JSON on the final stdout line.

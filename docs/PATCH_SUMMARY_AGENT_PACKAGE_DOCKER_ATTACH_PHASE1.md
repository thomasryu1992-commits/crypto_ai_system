# Patch Summary - Agent Package Docker Attach Phase 1

## Scope

Added a minimal Docker attach layer for Thomas Agent OS launched mode while preserving the standard Agent Package entrypoint.

## Added

- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`
- `scripts/docker_smoke.py`
- `tests/smoke/test_agent_package_docker_attach.py`
- `docs/AGENT_OS_DOCKER_ATTACH_GUIDE.md`

## Updated

- `agent_manifest.json`
- `config/defaults.json`
- `scripts/self_test.py`
- `scripts/validate_package.py`
- `README_AGENT.md`

## Safety posture

This patch does not enable live trading, signed testnet execution, real order submission, endpoint calls, secret reads, or runtime mutation.

Docker mode is an adapter for packaging and execution environment consistency only.

## Additional compatibility repair

During package collection, legacy research tests still imported missing canonical storage compatibility modules. The following thin wrappers were restored without adding runtime behavior:

- `src/crypto_ai_system/storage/jsonl.py`
- `src/crypto_ai_system/storage/latest.py`
- `src/crypto_ai_system/storage/csv_backup.py`
- `src/crypto_ai_system/storage/raw_store.py`
- `src/crypto_ai_system/storage/normalized_store.py`

These wrappers preserve append/read/write/storage compatibility for existing research and data modules. They do not enable endpoint calls, order submission, secret reads, or stage promotion.

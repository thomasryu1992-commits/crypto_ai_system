# Crypto AI System Agent Package Progress and Roadmap - Docker Attach Phase 1

## Baseline reviewed

Input package: `crypto_ai_system_v0.286.0-agent.1.zip`

Reference: `Crypto AI System Agent Package 변환 개발 지시서.pdf`

## Current completion against Agent Package phases

| Phase | Requirement | Status after this patch |
|---|---|---|
| Phase 1 | agent metadata, README_AGENT, defaults, command map | Complete |
| Phase 2 | standard run_command entrypoint, daily/scan dry-run, final-line JSON, artifacts | Complete |
| Phase 3 | self_test, safe defaults, dry-run validation, secrets scan | Complete |
| Phase 4 | validate_package, required/forbidden file checks, safe defaults | Complete |
| Phase 5 | Thomas Agent OS import compatibility | Locally prepared; real Agent OS import not executed in this container |
| Docker attach | Dockerfile, compose service, self-test service, dockerignore, static smoke | Added in this patch |

## Development performed in this patch

- Added Docker attach files without converting the project into a Docker-only architecture.
- Preserved `python scripts/run_command.py` as the canonical Agent OS entrypoint.
- Added `scripts/docker_smoke.py` static safety validator.
- Updated `scripts/self_test.py` and `scripts/validate_package.py` to include Docker attach checks.
- Added smoke tests for Docker attach files and safety.
- Restored missing storage compatibility wrappers required for collection and research pipeline compatibility.

## Safety posture

The package remains review-only / local-launcher safe by default:

- `live_trading_enabled=false`
- `order_execution_enabled=false`
- `auto_position_open_enabled=false`
- `withdrawal_enabled=false`
- `fund_transfer_enabled=false`
- `execution_permission_granted=false`
- `stage_transition_allowed=false`

Docker attach mode is not execution permission. It is only a packaging/runtime adapter.

## Validation performed

- `python scripts/docker_smoke.py` passed
- `python scripts/validate_package.py` passed
- `python scripts/self_test.py` passed
- `pytest tests/smoke tests/test_step289_signal_qa_agent.py tests/test_step290_legacy_signal_fallback_blocker.py tests/test_step291_decision_pipeline_registry.py` passed
- `pytest --collect-only` collected 917 tests
- Core config unsafe truthy flag count: 0

## Roadmap from here

1. Phase 5 import compatibility dry-run with actual Thomas Agent OS Import Manager.
2. Telegram command routing verification: `/run crypto daily`, `/run crypto scan BTC`.
3. Docker compose execution verification on a machine with Docker installed.
4. Add Agent OS import result artifact parser and registry handshake fixture.
5. Add package release builder that guarantees top-level `crypto_ai_system/` folder only.
6. Add versioned package checksum and import manifest for Agent OS registry.
7. Continue later execution roadmap only after Agent OS packaging is stable.

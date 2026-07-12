# ZIP Packaging Criteria — Step237

This file separates ZIP packaging rules from README execution instructions.

## 1. Source Handoff Package Criteria

A source handoff ZIP should include files required for a developer or Codex session to inspect, modify, and test the system.

Required inclusions:

- `src/crypto_ai_system/**`
- Root runner files, including `run_step209_237_v5_chain_bootstrap.py`
- `tests/**`
- `requirements.txt`
- `pytest.ini`
- `.env.example`
- `README.md`
- Step reports and validation summaries that explain current scope
- Packaging criteria document: `ZIP_PACKAGING_CRITERIA_STEP237.md`

Allowed inclusions:

- Small example CSV/JSON inputs
- Manual ETF CSV example files
- Historical Step reports needed for audit context
- Compatibility notes and merge manifests

Required exclusions:

- `.env`
- API keys, service account JSON, private credentials, or secrets
- `.git/**`
- `__pycache__/**`
- `.pytest_cache/**`
- Large transient runtime logs not needed for handoff
- Local virtual environments

## 2. Validation Handoff Package Criteria

A validation handoff ZIP should include the source handoff contents plus current validation outputs that prove the chain/artifact-generation check ran successfully.

Required additional inclusions:

- `VALIDATION_REPORT_STEP237.md`
- `VALIDATION_SUMMARY_STEP237.json`
- `storage/latest/step209_237_chain_bootstrap_latest.json`
- `storage/logs/step209_237_chain_bootstrap_runs.jsonl`
- `reports/step209_237_chain_bootstrap_report.md`

Validation wording must be:

```text
체인/산출물 생성 검증 통과
```

Validation wording must not be:

```text
운영/프로덕션 통과 표현
```

## 3. Runtime Output Separation

Runtime outputs should be separated by purpose:

```text
storage/latest/      latest state and latest validation JSON
storage/logs/        append-style JSONL logs
reports/             generated Markdown review reports
storage/features/    feature-store CSV outputs
storage/raw/         raw-data snapshots, when intentionally included
```

For source-only handoff packages, generated runtime outputs may be omitted unless they are small and required for deterministic tests.

For validation handoff packages, include only validation outputs that are directly tied to the current declared validation scope.

## 4. Naming Rules

Recommended naming:

```text
crypto_ai_system_step237_chain_bootstrap_packaged.zip
crypto_ai_system_step237_chain_artifact_validated.zip
```

Avoid names that imply production readiness, such as:

```text
*_production_validated.zip
*_operational_validated.zip
*_live_ready.zip
```

## 5. Safety Scope Rules

The Step209~237 ZIP may claim:

```text
Step209~Step237 chain/artifact-generation validation passed.
```

The Step209~237 ZIP may not claim:

```text
Production operation is validated.
Live trading is validated.
Exchange adapter routing is validated.
External API execution is validated.
Real Telegram send is validated.
```

## 6. Final Pre-ZIP Checklist

Before packaging, run:

```bash
python -m compileall -q src
python run_step209_237_v5_chain_bootstrap.py
python -m pytest -q tests
```

Then confirm:

- `requirements.txt` explicitly includes `pytest`.
- README contains current Step209~237 execution commands.
- Validation report uses `체인/산출물 생성 검증 통과` wording.
- ZIP filename does not imply production/live validation.
- No secrets or private environment files are included.

## Step237 Hardening Notes

- Step208 compatibility backfill is explicitly marked as `compat_stub`; it is only for Step209~237 artifact-chain validation.
- Fallback data profiles are separated into `config/fallback_data_profiles.yaml`; fallback sources remain research/backtest only and cannot authorize live execution.
- `config/settings.py` no longer creates directories, loads dotenv, or raises live-trading confirmation errors at import time. Runtime directory creation and live confirmation validation must be called explicitly.
- Step209~237 tests use `tmp_path`-isolated project roots for generated artifacts.


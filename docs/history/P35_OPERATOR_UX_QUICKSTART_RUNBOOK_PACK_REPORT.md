# P35 Operator UX Quickstart / Non-Developer Runbook

Status: `P35_OPERATOR_UX_QUICKSTART_RUNBOOK_PACK_GENERATED_REVIEW_ONLY`
Decision: `WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE`

This runbook is a review-only operator guide. It does not enable runtime, scheduler, live orders, testnet orders, or secret access.

## 1. Unpack and open the package

```bash
unzip crypto_ai_system_v0.286.0-agent.14-feature-snapshot_p35_operator_ux_quickstart_runbook_pack.zip -d crypto_ai_system
cd crypto_ai_system
```

## 2. Check the operator dashboard

Run these read-only commands only:

```bash
PYTHONPATH=src:. python scripts/run_command_response_snapshot_pack.py --print-telegram
PYTHONPATH=src:. python scripts/run_command_response_snapshot_pack.py --print-launcher
PYTHONPATH=src:. python scripts/run_operator_ux_quickstart_runbook_pack.py --print-checklist
```

## 3. Allowed dashboard commands

- `status`: read-only dashboard lookup
- `matrix`: read-only dashboard lookup
- `waiting`: read-only dashboard lookup
- `no_go`: read-only dashboard lookup
- `export_paths`: read-only dashboard lookup

## 4. Commands that must stay blocked

- `/crypto_enable`
- `/crypto_start`
- `/crypto_submit`
- `/crypto_order`
- `/crypto_live`
- `/crypto_activate`
- `/crypto_trade`
- `/crypto_scheduler_start`
- `/crypto_place_order`
- `/crypto_cancel_order`
- `enable live`
- `start runtime`

## 5. Operator interpretation

- `WAITING` means required external/operator evidence is missing.
- `NO-GO` means the package must not proceed until blockers are fixed.
- `GO-REVIEW-ONLY` still does not mean runtime authority.
- Runtime remains disabled unless a separate future runtime boundary performs activation after all required evidence is valid.

## 6. Safety invariants

- Do not paste API keys, API secrets, private keys, passphrases, or secret files into the package.
- Do not run enable/start/submit/order/live/trade/activate/scheduler commands.
- Do not edit settings.yaml or score_weights to force promotion.
- Do not treat mock, sample, fallback, or review-only evidence as exchange execution evidence.
- Keep runtime, scheduler, and order submission disabled.

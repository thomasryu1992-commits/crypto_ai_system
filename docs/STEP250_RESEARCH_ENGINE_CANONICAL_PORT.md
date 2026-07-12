# Step250 v5 Research Engine Canonical Port Batch

## Purpose

Step250 ports the research engine and decision engine modules to the canonical package.

## Ported Modules

- `research.research_engine` → `crypto_ai_system.research.research_engine`
- `research.decision_engine` → `crypto_ai_system.research.decision_engine`

## Support Modules

- `research.scoring` → `crypto_ai_system.research.scoring`
- `research.scenario` → `crypto_ai_system.research.scenario`

## Safety Rule

Research modules remain report/decision-generation only.

They must not enable trading execution, order routing, adapter routing, or live trading.

## Import Rewrite Scope

Only these files are rewritten for this batch:

- `run_full_cycle.py`
- `run_research_cycle.py`
- `run_research_decision.py`
- `research_bot/research_app.py`

## Expected Result

- Direct root import count decreases from 8 to 3.
- Canonical port group count decreases from 3 to 1.

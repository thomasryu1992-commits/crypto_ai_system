# Crypto AI System Inventory - Step120

## Core
- config/settings.py
- core/json_io.py
- core/time_utils.py
- core/console.py

## Data / Context
- collectors/market_data_collector.py
- builders/market_snapshot.py
- builders/market_context.py
- data_health/health_check.py

## Research / Trading
- research/research_engine.py
- research/decision_engine.py
- trading/signal_engine.py
- trading/paper_engine.py
- trading/trading_cycle.py
- bridge/research_trading_bridge.py

## Risk / Execution
- risk/risk_guard.py
- execution/live_guard.py
- execution/order_executor.py
- execution/mock_exchange.py
- execution/reconciler.py

## Reporting / Integrations
- integrations/spreadsheet_exporter.py
- notify/telegram_notifier.py
- analysis/live_shadow.py

## Validation Scripts
- run_step120_validation.py
- run_step120_dry_run.py
- run_data_health_check.py
- run_research_trading_bridge.py
- run_live_readiness_check.py
- run_live_shadow_report.py

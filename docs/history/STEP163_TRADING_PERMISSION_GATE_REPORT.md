# STEP163 Trading Bot Permission Gate Report

## Purpose
Step163 connects ResearchSignal v2 `trade_permission` directly to the Trading Bot before any new position can be opened.

The Trading Bot must now evaluate:

- `allow_long`
- `allow_short`
- `allow_new_position`
- `risk_level`: `normal | reduced | blocked`
- `position_size_multiplier`
- `block_reasons`
- `risk_warnings`

## Key Decision
ResearchSignal v2 is now the final permission gate before a Trading Bot trade candidate is allowed.

Price structure still controls Entry / SL / TP generation, but ResearchSignal controls whether the trade is allowed, reduced, or blocked.

## Added Files

- `src/crypto_ai_system/trading/permission_gate.py`
- `trading/permission_gate.py`
- `tests/test_step163_trading_permission_gate.py`

## Modified Files

- `src/crypto_ai_system/trading/signal.py`
- `src/crypto_ai_system/trading/trading_bot.py`
- `src/crypto_ai_system/research/research_signal.py`
- `src/crypto_ai_system/research/research_signal_builder.py`
- `src/crypto_ai_system/config.py`
- `trading/signal_engine.py`
- `trading/paper_engine.py`
- `trading/trading_cycle.py`
- `config/settings.py`
- `config/settings.yaml`
- `.env.example`
- `tests/test_step162_feature_store_signal.py`

## Behavior

### Normal

If ResearchSignal allows the side and risk level is `normal`, Trading Bot may create a full-size trade candidate.

### Reduced

If ResearchSignal allows the side but risk level is `reduced`, Trading Bot may create a trade candidate with reduced position size.

Default multiplier:

```env
RISK_LEVEL_REDUCED_POSITION_MULTIPLIER=0.50
```

### Blocked

If ResearchSignal says `risk_level=blocked`, `allow_new_position=false`, or the side-specific permission is false, the Trading Bot blocks the new position.

## Environment

New environment variables:

```env
USE_RESEARCH_SIGNAL_GATE=true
RISK_LEVEL_REDUCED_POSITION_MULTIPLIER=0.50
RISK_LEVEL_BLOCKED_POSITION_MULTIPLIER=0.00
```

## Validation

```bash
python -m pytest -q
# 42 passed

python run_step162_feature_research_validation.py
# STEP162_FEATURE_RESEARCH_VALIDATION_OK

python run_step161_extra_data_validation.py
# STEP161_EXTRA_DATA_VALIDATION_OK

python run_additional_data_collector.py
# ADDITIONAL_DATA_COLLECTOR_OK

python run_trading_cycle.py
# Trading cycle: NONE paper=BLOCKED_BY_PERMISSION_GATE
```

The `run_trading_cycle.py` result is expected in local validation mode because price-data-only ResearchSignal is not live-execution eligible.

## Next Step
Step164 should focus on Trading Bot execution integration improvements:

1. Add a dedicated permission-gate audit log.
2. Add Telegram signal messages that include permission gate status.
3. Add paper-trading reports split by `risk_level`.
4. Validate the permission gate with real Extended/Coinalyze/Binance API data.
5. Prepare controlled testnet execution flow, still blocked by default.

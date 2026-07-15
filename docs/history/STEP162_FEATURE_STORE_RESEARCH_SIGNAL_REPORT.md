# Step162 — Feature Store Integration + ResearchSignal v2 Foundation

## Scope
Step162 connects the extra BTC data collection layer to the Research Bot feature pipeline.

The Step161 collectors remain in place:

- Binance Futures Public API
- Coin Metrics Exchange Flow
- Farside BTC ETF Flow CSV
- DefiLlama Stablecoin Liquidity

Step162 adds the integration layer that turns these optional data sources into Research Engine features, score components, and trade-permission context.

## New / Updated Files

### New
- `src/crypto_ai_system/features/research_feature_matrix.py`
- `run_step162_feature_research_validation.py`
- `tests/test_step162_feature_store_signal.py`
- `STEP162_FEATURE_STORE_RESEARCH_SIGNAL_REPORT.md`

### Updated
- `src/crypto_ai_system/research/research_bot.py`
- `src/crypto_ai_system/research/raw_score_pipeline.py`
- `src/crypto_ai_system/research/research_signal_builder.py`
- `src/crypto_ai_system/data/additional_data_collector.py`
- `src/crypto_ai_system/analysis/weights.py`
- `src/crypto_ai_system/analysis/market_condition.py`
- `src/crypto_ai_system/research/report_renderer.py`
- `config/settings.yaml`
- `README.md`

## Step162 Logic

### 1. Research Feature Matrix

The system now builds a unified research feature matrix:

```text
price_features
+ coinalyze_derivatives_features
+ binance_futures_features
+ exchange_flow_features
+ etf_flow_features
+ stablecoin_liquidity_features
= research_feature_matrix
```

Optional extra data is merged using backward as-of joins. This allows slower daily data such as Exchange Flow and ETF Flow to be used with intraday price rows.

Missing optional data defaults to neutral scoring:

- `binance_derivatives_score = 0.0`
- `exchange_flow_score = 0.0`
- `etf_flow_score = 0.0`
- `stablecoin_liquidity_score = 0.0`

### 2. Feature Store Outputs

Feature Store files are written under:

```text
storage/features/
```

Expected outputs:

- `extra_derivatives_features.csv`
- `exchange_flow_features.csv`
- `etf_flow_features.csv`
- `stablecoin_liquidity_features.csv`
- `research_feature_matrix.csv`

Parquet output is attempted when a parquet engine is installed. CSV is always written.

### 3. Score Weight Redesign

The Research Engine weights were updated for the new data stack:

```yaml
structure: 0.20
momentum: 0.10
derivatives: 0.25
exchange_flow: 0.15
etf_flow: 0.15
stablecoin_liquidity: 0.10
risk: 0.05
onchain: 0.00
```

This keeps price structure important while giving flow/liquidity data enough influence to improve ResearchSignal quality.

### 4. ResearchSignal v2 Permission Gate Foundation

ResearchSignal now exposes:

```json
{
  "trade_permission": {
    "allow_long": false,
    "allow_short": false,
    "allow_new_position": false,
    "risk_level": "normal | reduced | blocked",
    "risk_warnings": [],
    "block_reasons": []
  }
}
```

Risk behavior:

- `normal`: trade is allowed with normal size
- `reduced`: setup may be allowed, but future Trading Bot logic should reduce position size
- `blocked`: new entries are blocked

### 5. Market Condition Update

Added support for conditions such as:

- `OVERLEVERAGED_WAIT`
- `RISK_OFF_WAIT`
- `WAIT_EXCHANGE_SELL_PRESSURE`

These conditions help separate price opportunity from permission/risk quality.

## Validation

Command:

```bash
PYTHONPATH=src:. pytest -q
```

Result:

```text
32 passed
```

Step162 validation runner:

```bash
PYTHONPATH=src:. python run_step162_feature_research_validation.py
```

Expected output:

```text
STEP162_FEATURE_RESEARCH_VALIDATION_OK
signal_version: research_signal_v2_step162_feature_store_gate
feature_matrix_rows: 500
```

## Next Step

Step163 should connect `ResearchSignal.trade_permission` directly to the Trading Bot permission gate.

Priority:

1. Trading Bot reads latest `research_signal.json`
2. Trading Bot checks `allow_long`, `allow_short`, `allow_new_position`
3. Trading Bot applies `risk_level`
4. `risk_level = reduced` lowers position size
5. `risk_level = blocked` blocks new entries
6. Entry / SL / TP still come from price structure and risk management

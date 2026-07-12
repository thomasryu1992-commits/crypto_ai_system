# Crypto AI System — Step1~157E Full Extended Package

This package is the consolidated Crypto_AI_System through Step157E.

Main direction:

- Extended is the primary exchange/data source.
- Internal canonical symbol: `BTC-PERP`.
- Extended market: `BTC-USD`.
- Quote/index price basis: USD.
- Settlement/margin asset: USDC.
- Binance main-flow collector has been removed/replaced by Extended.
- Spreadsheet-first architecture is preserved.
- Coinalyze enrichment seam is preserved.
- Live trading and signed testnet orders remain disabled.

## Included Functional Areas

```text
1. Extended market adapter and data collector
2. Raw data collection and raw CSV store
3. Spreadsheet backup writer and retry queue seam
4. Coinalyze derivatives enrichment seam
5. Feature Store / indicators / market regime
6. Research Bot
7. Weighted Score Engine
8. Market Condition Analyzer
9. Scenario Builder
10. Entry Policy v2
11. Exit Policy v2
12. Risk and position sizing
13. Extended-specific backtest engine
14. Parameter sweep through Step157E
15. Trading Bot signal-to-trade-plan bridge
16. Paper Watch scaffold
17. Telegram summary dry-run scaffold
18. Extended order payload dry-run scaffold for future Step159E
19. Safety flags and validation
```

## What was intentionally excluded

Intermediate one-off test files and temporary validation scripts from earlier development rounds were not included. The package keeps consolidated runners and regression-style validation scripts instead.

## Main Commands

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt

python run_step157e_full_validation.py
```

Other useful runners:

```bash
python run_collect_raw_data.py
python run_research_bot.py
python run_daily_research_report.py
python run_trading_cycle.py
python run_step151e_extended_market_check.py
python run_step152e_build_extended_features.py
python run_step154e_extended_backtest.py
python run_step157e_parameter_sweep.py
```

## Environment

Copy `.env.example` to `.env` and fill keys when needed.

```text
EXTENDED_API_KEY=
COINALYZE_API_KEY=
LIVE_TRADING_ENABLED=false
TESTNET_SIGNED_ORDER_ENABLED=false
```

The package runs with sample fallback data when API keys or network access are unavailable.

## Safety

This package is for data, research, backtest, parameter sweep, and dry-run trading decisions only.

```text
LIVE_TRADING_ENABLED=false
TESTNET_SIGNED_ORDER_ENABLED=false
```

Step159E should handle actual Extended testnet signed orders separately with Stark signing, websocket order tracking, cancel/replace handling, and idempotency.

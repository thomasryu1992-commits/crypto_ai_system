"""Strategy Factory backtesting (Phase S4).

A self-contained engine that evaluates a :class:`StrategySpec` on historical
data under a fixed cost model and reports R-based performance. Distinct from the
legacy ``crypto_ai_system.backtest`` package: strategies here define their own
single-stop / single-target / max-holding exit, evaluated bar-by-bar via the
shared spec evaluator, so backtest and live share one signal source.
"""

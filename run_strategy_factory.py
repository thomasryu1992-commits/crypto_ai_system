"""Strategy factory runner — generate, backtest, and populate the paper pool.

This is the entry point that *fills* the active strategy pool. Everything else
(the live router, the paper drive, the lifecycle feedback) only reads the pool;
without running this, the pool stays empty and no strategy ever trades.

    py run_strategy_factory.py                 # run one generation cycle
    py run_strategy_factory.py --cycles 4      # run several generations
    py run_strategy_factory.py --status        # show the current pool, no run

Each cycle generates a batch of candidate strategies, backtests them on the
cached real candles (storage/latest/coinalyze_market_data.json — refreshed by the
pipeline / scheduler), selects at most one champion that clears the absolute
gate, and adds it to the paper pool. Generation/strategy counters persist so ids
stay unique across runs.

Gate thresholds default to values suited to the ~200 cached candles; tighten them
toward the directive's §6.7 bar (>=100 trades, etc.) once you backtest on a
longer history. This runner adds only to the *paper* pool — testnet/live stay
manual.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Directive §6.7: a champion should clear >=100 backtest trades before it is
# statistically trustworthy. Runs below this are flagged provisional.
DIRECTIVE_MIN_TRADES_FLOOR = 100


def _bootstrap() -> None:
    root = Path(__file__).resolve().parent
    for p in (str(root / "src"), str(root)):
        if p not in sys.path:
            sys.path.insert(0, p)
    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env", override=True)
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    _bootstrap()
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    import config.settings as settings
    from core.json_io import read_json
    from core.time_utils import utc_now_iso
    from crypto_ai_system.backtesting.backtest_agent import AbsoluteGate
    from crypto_ai_system.backtesting.cost_model import CostModel
    from crypto_ai_system.strategy_factory.active_strategy_pool import load_pool, occupying_entries
    from crypto_ai_system.strategy_factory.factory_runner import load_counters, run_factory

    parser = argparse.ArgumentParser(description="Run the strategy factory to populate the paper pool.")
    parser.add_argument("--cycles", type=int, default=1, help="number of generation cycles to run")
    parser.add_argument("--status", action="store_true", help="show the current pool and exit")
    parser.add_argument("--cap", type=int, default=5, help="max paper-active strategies")
    parser.add_argument("--max-per-family", type=int, default=2, help="max active strategies of one family")
    parser.add_argument("--min-trades", type=int, default=8, help="absolute gate: min backtest trades")
    parser.add_argument("--min-expectancy", type=float, default=0.05, help="absolute gate: min expectancy R")
    parser.add_argument("--min-profit-factor", type=float, default=1.10)
    parser.add_argument("--min-wf-pass", type=float, default=0.5, help="min walk-forward pass rate")
    parser.add_argument("--max-drawdown", type=float, default=12.0, help="max drawdown R")
    parser.add_argument("--min-stability", type=float, default=0.2, help="min temporal stability")
    parser.add_argument("--min-trades-per-param", type=float, default=None,
                        help="overfitting gate: min backtest trades per fitted parameter (a spec "
                             "carries ~4-6). Off by default because short history cannot meet it; "
                             "~10 is where an estimate starts to mean something. Needs --history.")
    parser.add_argument("--min-robustness", type=float, default=None,
                        help="overfitting gate: min robustness score 0..1 (sample per parameter, "
                             "walk-forward consistency, regime breadth, parsimony, cost survival). "
                             "Off by default; the score is always reported.")
    parser.add_argument("--history", type=int, default=0,
                        help="use N recent klines from the public futures API instead of the "
                             "cached runtime candles (0 = use cache). Paged past the venue's "
                             "1500-per-call cap and cached on disk, so years of history are "
                             "practical: ~26000 1h bars is ~3 years. A strategy needs this depth "
                             "to clear the trade-count gate honestly.")
    parser.add_argument("--refresh-history", action="store_true",
                        help="ignore the on-disk history cache and refetch")
    parser.add_argument("--interval", default="1h", help="kline interval when --history is used")
    args = parser.parse_args(argv)

    pool_file = str(settings.ACTIVE_STRATEGY_POOL_PATH)
    state_file = str(settings.STRATEGY_FACTORY_STATE_PATH)

    if args.status:
        pool = load_pool(pool_file)
        counters = load_counters(state_file)
        print(f"=== strategy factory status ===")
        print(f"next generation: GEN-{counters['generation_seq']:03d} | next strategy id: S{counters['strategy_seq']:03d}")
        print(f"active pool ({len(occupying_entries(pool))}):")
        for e in pool.get("active_strategies", []):
            fam = (e.get("strategy_spec") or {}).get("strategy_family")
            print(f"  {e.get('strategy_id')} [{fam}] {e.get('status')} from {e.get('generation_id')}")
        return 0

    candles: list = []
    if args.history and args.history > 0:
        try:
            from collectors.real_market_data import to_binance_symbol
            from crypto_ai_system.data.candle_history import load_candle_history

            symbol = to_binance_symbol(getattr(settings, "SYMBOL", "BTC-PERP"))
            candles, source = load_candle_history(
                symbol,
                args.interval,
                args.history,
                cache_dir=settings.HISTORY_DIR,
                base_url=settings.BINANCE_FUTURES_PUBLIC_BASE_URL,
                refresh=args.refresh_history,
            )
            span = f"{candles[0]['timestamp']} -> {candles[-1]['timestamp']}" if candles else "empty"
            print(f"{source}: {len(candles)} {args.interval} klines for {symbol} [{span}]")
        except Exception as exc:  # noqa: BLE001
            print(f"history fetch failed ({type(exc).__name__}: {exc}); falling back to cached candles")
            candles = []

    if not candles:
        market = read_json(settings.MARKET_DATA_PATH, {}) or {}
        candles = market.get("candles", []) if isinstance(market, dict) else []
    if len(candles) < 60:
        print(f"NOT ENOUGH CANDLES: {len(candles)} (need >=60). Run the pipeline/scheduler first "
              f"to refresh {settings.MARKET_DATA_PATH.name}.")
        return 1

    gate = AbsoluteGate(
        min_trade_count=args.min_trades, min_expectancy_r=args.min_expectancy,
        min_profit_factor=args.min_profit_factor, min_walk_forward_pass_rate=args.min_wf_pass,
        max_drawdown_r=args.max_drawdown, min_temporal_stability=args.min_stability,
        min_trades_per_parameter=args.min_trades_per_param,
        min_robustness_score=args.min_robustness,
    )
    # Directive §6.7 wants >=100 backtest trades before a champion is trusted. The
    # shipped default is far lower so the factory can produce anything at all on the
    # short cached history — but a champion cleared on a thin sample is provisional,
    # not statistically sound. Make that loud instead of silent.
    thin_sample = args.min_trades < DIRECTIVE_MIN_TRADES_FLOOR
    if thin_sample:
        print(f"WARNING: --min-trades={args.min_trades} is below the directive floor of "
              f"{DIRECTIVE_MIN_TRADES_FLOOR}; champions selected here are PROVISIONAL "
              f"(thin-sample). Grow history (e.g. --history 1500) and raise --min-trades "
              f"toward {DIRECTIVE_MIN_TRADES_FLOOR} before trusting a champion.")
    # Generate specs on the timeframe of the candles being backtested — a spec's
    # timeframe is part of its contract (the router evaluates it on that frame).
    templates = None
    if args.interval != "1h":
        from crypto_ai_system.strategy_factory.strategy_template_library import templates_for_timeframe

        templates = templates_for_timeframe(args.interval)
        print(f"templates retimed to {args.interval} ({len(templates)} families)")

    result = run_factory(
        candles, pool_file=pool_file, state_file=state_file, cycles=args.cycles,
        cost=CostModel(), gate=gate, cap=args.cap, max_per_family=args.max_per_family,
        registry_file=str(settings.STRATEGY_ACTIVE_REGISTRY_PATH),
        candidate_registry_file=str(settings.STRATEGY_CANDIDATE_REGISTRY_PATH),
        templates=templates,
        now=utc_now_iso(),
    )
    if result.get("error"):
        print(f"factory error: {result['error']} (candles={result.get('candles')})")
        return 1

    provisional = " [PROVISIONAL: thin-sample gate]" if thin_sample else ""
    print(f"=== strategy factory: {result['cycles_run']} cycle(s) over {result['bars']} bars{provisional} ===")
    for r in result["reports"]:
        champ = r.get("selected_strategy_id") or "NONE"
        decision = (r.get("pool_decision") or {}).get("action") if r.get("pool_decision") else "-"
        rob = r.get("champion_robustness") or {}
        verdict = ""
        if rob:
            verdict = (f" | robustness {rob['verdict']} {rob['robustness_score']:.2f} "
                       f"({rob['trades_per_parameter']:.1f} trades/param over {rob['free_parameters']})")
        print(f"  {r['generation_id']} (seed {r['seed']}): {r['qualified_count']}/{r['batch_accepted']} qualified "
              f"-> champion {champ} [{decision}] | active pool: {r['active_pool_size']}{verdict}")
        for warning in rob.get("warnings") or []:
            print(f"      ! {warning}")
    print(f"active pool now ({result['active_pool_size']}):")
    for e in result["active_strategies"]:
        print(f"  {e['strategy_id']} [{e['strategy_family']}] {e['status']} from {e['generation_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

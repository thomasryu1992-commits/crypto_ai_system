"""Rule miner runner — evolve entry rules from data, gate honestly, fill the pool.

    py run_rule_miner.py --symbol BTCUSDT --history 2200 --interval 1d
    py run_rule_miner.py --symbol ETHUSDT --history 2200 --interval 1d --population 60

The search sees only the first 70% of the history (thresholds, fitness,
selection all come from that slice). A survivor must then pass, in order:

1. the S3 validator (structure, runtime-available features, exits);
2. a HOLDOUT gate on the untouched last 30% — positive expectancy, PF > 1, and
   enough trades to mean anything. The search never saw these bars, so this is
   genuine out-of-sample evidence, not a re-reading of the fit;
3. the directive's absolute gate + the robustness scorer on the FULL frame,
   exactly like a template champion.

Only then may it take a paper slot (same add_champion path, same audit
registry, same diversity guard). Mined specs carry ``search_evaluations`` — the
selection-bias denominator — and a family named after their feature combination.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


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
    from collectors.real_market_data import to_binance_symbol
    from core.time_utils import utc_now_iso
    from crypto_ai_system.backtesting.backtest_agent import AbsoluteGate, run_backtest_agent
    from crypto_ai_system.backtesting.cost_model import CostModel
    from crypto_ai_system.backtesting.execution_simulator import simulate_strategy
    from crypto_ai_system.data.candle_history import load_candle_history
    from crypto_ai_system.strategy_factory.active_strategy_pool import (
        ACTIVE_STRATEGY_REGISTRY_NAME,
        add_champion,
        load_pool,
        family_count,
        occupying_entries,
        save_pool,
    )
    from crypto_ai_system.registry.base_registry import append_registry_record
    from crypto_ai_system.strategy_factory.factory_runner import load_counters, save_counters
    from crypto_ai_system.strategy_factory.rule_miner import (
        mine_rule_sets,
        rule_set_to_spec_dict,
        spec_to_rule_set,
        split_train_holdout,
    )
    from crypto_ai_system.strategy_factory.runtime_feature_adapter import build_backtest_frame
    from crypto_ai_system.strategy_factory.strategy_registry import persist_strategy_spec
    from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec
    from crypto_ai_system.strategy_factory.strategy_validator_agent import validate_strategy

    parser = argparse.ArgumentParser(description="Mine entry rules from data and gate them honestly.")
    parser.add_argument("--symbol", default=None, help="venue symbol (default: runtime SYMBOL)")
    parser.add_argument("--history", type=int, default=2200, help="klines to mine over")
    parser.add_argument("--interval", default="1d", help="kline interval (1h is a cost trap: ~0.21R/trade)")
    parser.add_argument("--seed", type=int, default=1, help="evolution seed")
    parser.add_argument("--population", type=int, default=40)
    parser.add_argument("--generations", type=int, default=12)
    parser.add_argument("--top", type=int, default=5, help="distinct-family survivors to gate")
    parser.add_argument("--train-fraction", type=float, default=0.7)
    parser.add_argument("--holdout-min-trades", type=int, default=10)
    parser.add_argument("--cap", type=int, default=15, help="pool cap")
    parser.add_argument("--max-per-family", type=int, default=2)
    parser.add_argument("--min-trades", type=int, default=100, help="absolute gate (full frame)")
    parser.add_argument("--min-expectancy", type=float, default=0.1)
    parser.add_argument("--min-profit-factor", type=float, default=1.15)
    parser.add_argument("--min-wf-pass", type=float, default=0.7)
    parser.add_argument("--max-drawdown", type=float, default=10.0)
    parser.add_argument("--min-stability", type=float, default=0.3)
    parser.add_argument("--dry-run", action="store_true", help="mine and gate, but do not touch the pool")
    parser.add_argument("--no-seed-champions", action="store_true",
                        help="start from a fully random population instead of seeding the "
                             "adopted pool champions' rule sets into it")
    args = parser.parse_args(argv)

    symbol = to_binance_symbol(args.symbol or getattr(settings, "SYMBOL", "BTC-PERP"))
    candles, source = load_candle_history(
        symbol, args.interval, args.history,
        cache_dir=settings.HISTORY_DIR,
        base_url=settings.BINANCE_FUTURES_PUBLIC_BASE_URL,
    )
    frame = build_backtest_frame(candles)
    if len(frame) < 300:
        print(f"NOT ENOUGH BARS: {len(frame)} (need >=300 for a meaningful train/holdout split)")
        return 1

    train, holdout = split_train_holdout(frame, args.train_fraction)
    print(f"{source}: {len(frame)} {args.interval} bars for {symbol} "
          f"[train {len(train)} | holdout {len(holdout)} — search never sees the holdout]")

    cost = CostModel()

    def fitness(rule_set) -> float:
        """Train-slice t-statistic: mean R / standard error.

        Raw expectancy as fitness breeds six-trades-in-six-years rules — a huge
        mean over a tiny sample — which then die at every downstream sample-size
        gate. The t-statistic is the quantity the whole pipeline actually cares
        about (is the edge distinguishable from luck?), and it rewards edge and
        frequency in exactly the proportion the gates will later demand."""
        spec_dict = rule_set_to_spec_dict(
            rule_set, strategy_id="FIT", generation_id="FIT",
            symbol=symbol, timeframe=args.interval, search_evaluations=0,
        )
        try:
            spec = StrategySpec.from_dict(spec_dict)
        except Exception:  # noqa: BLE001 - unparseable candidate scores nothing
            return -10.0
        trades = simulate_strategy(spec, train, cost=cost)["trades"]
        n = len(trades)
        # The full-frame gate needs >=100 trades; the train slice is 70% of the
        # frame, so a rule needs ~75 train trades to have a chance of qualifying.
        if n < 75:
            return -5.0 + n * 0.05  # gradient toward "trades often enough"
        rs = [t["r_multiple"] for t in trades]
        mean = sum(rs) / n
        var = sum((r - mean) ** 2 for r in rs) / (n - 1)
        if var <= 0:
            return -10.0
        return mean / ((var ** 0.5) / (n ** 0.5))

    # Adopted champions seed the initial population (proven parents to breed
    # from); they earn no other privilege — same fitness, same gates. L-A2:
    # seeds are ordered by their shrunk live-blended score (best first, so the
    # population-budget truncation keeps the live-best) and carry weight 1+w
    # for the first breeding round. With no live data w=0 everywhere: original
    # order-agnostic equal-ticket behavior.
    from crypto_ai_system.strategy_factory.live_evidence import (
        load_live_stats,
        resolve_pseudo_trades,
        sls_for_entry,
    )

    live_stats = load_live_stats(str(settings.STRATEGY_ATTRIBUTED_OUTCOME_REGISTRY_PATH))
    pseudo_trades = resolve_pseudo_trades()
    seed_rule_sets = []
    seed_weights = []
    if not args.no_seed_champions:
        scored_seeds = []
        for entry in occupying_entries(load_pool(str(settings.ACTIVE_STRATEGY_POOL_PATH))):
            rule_set = spec_to_rule_set(entry.get("strategy_spec") or {})
            if rule_set is None:
                continue
            sls = sls_for_entry(entry, live_stats, pseudo_trades=pseudo_trades)
            sort_key = sls["score"] if sls["score"] is not None else float("-inf")
            weight = 1.0 + (sls["live_n"] / (sls["live_n"] + pseudo_trades))
            scored_seeds.append((sort_key, weight, rule_set))
        scored_seeds.sort(key=lambda item: item[0], reverse=True)
        seed_rule_sets = [item[2] for item in scored_seeds]
        seed_weights = [item[1] for item in scored_seeds]
        if seed_rule_sets:
            live_seeded = sum(1 for w in seed_weights if w > 1.0)
            print(f"seeding {len(seed_rule_sets)} pool champions into the initial population"
                  + (f" ({live_seeded} carrying live evidence)" if live_seeded else ""))

    mined = mine_rule_sets(
        train, fitness=fitness, seed=args.seed,
        population=args.population, generations=args.generations, top_n=args.top,
        seed_population=seed_rule_sets,
        seed_weights=seed_weights if seed_weights else None,
    )
    print(f"searched {mined['search_evaluations']} candidates "
          f"(condition pool {mined['condition_pool_size']}) -> {len(mined['survivors'])} distinct families")

    counters = load_counters(str(settings.STRATEGY_FACTORY_STATE_PATH))
    generation_id = f"MINE-{counters['generation_seq']:03d}"
    strategy_seq = counters["strategy_seq"]

    gate = AbsoluteGate(
        min_trade_count=args.min_trades, min_expectancy_r=args.min_expectancy,
        min_profit_factor=args.min_profit_factor, min_walk_forward_pass_rate=args.min_wf_pass,
        max_drawdown_r=args.max_drawdown, min_temporal_stability=args.min_stability,
    )

    pool_file = str(settings.ACTIVE_STRATEGY_POOL_PATH)
    pool = load_pool(pool_file)
    added = 0

    for survivor in mined["survivors"]:
        spec_dict = rule_set_to_spec_dict(
            survivor["rule_set"], strategy_id=f"S{strategy_seq:03d}",
            generation_id=generation_id, symbol=symbol, timeframe=args.interval,
            search_evaluations=mined["search_evaluations"],
        )
        strategy_seq += 1
        spec = StrategySpec.from_dict(spec_dict)
        label = f"{spec.strategy_id} [{spec.strategy_family} {spec.direction.value}]"

        verdict = validate_strategy(spec)
        if not verdict["approved_for_backtest"]:
            print(f"  {label} REJECTED validator: {verdict['block_reasons']}")
            continue

        # Holdout gate: the slice the search never saw.
        ho_trades = simulate_strategy(spec, holdout, cost=cost)["trades"]
        ho_rs = [t["r_multiple"] for t in ho_trades]
        ho_exp = (sum(ho_rs) / len(ho_rs)) if ho_rs else 0.0
        ho_pf_num = sum(r for r in ho_rs if r > 0)
        ho_pf_den = -sum(r for r in ho_rs if r < 0)
        ho_pf = (ho_pf_num / ho_pf_den) if ho_pf_den > 0 else 0.0
        if len(ho_trades) < args.holdout_min_trades or ho_exp <= 0 or ho_pf <= 1.0:
            why = ("too few holdout trades" if len(ho_trades) < args.holdout_min_trades
                   else "edge did not survive out-of-sample (the search overfit)")
            print(f"  {label} REJECTED holdout: n={len(ho_trades)} exp={ho_exp:+.3f} PF={ho_pf:.2f} — {why} "
                  f"(train fitness {survivor['train_fitness']:+.3f})")
            continue

        # Full-frame absolute gate + robustness, exactly like a template champion.
        record = run_backtest_agent(spec, frame, generation_id=generation_id, cost=cost, gate=gate)
        robustness = record.get("robustness") or {}
        if not record.get("qualified"):
            print(f"  {label} REJECTED absolute gate: {record.get('gate_failures')}")
            continue

        m = record["metrics"]
        print(f"  {label} QUALIFIED holdout(n={len(ho_trades)} exp={ho_exp:+.3f} PF={ho_pf:.2f}) "
              f"full(n={m['trade_count']} exp={m['expectancy_r']:+.3f} PF={m['profit_factor']:.2f}) "
              f"robustness {robustness.get('verdict')} {robustness.get('robustness_score')}")

        if args.dry_run:
            continue
        if family_count(pool, spec.strategy_family, symbol) >= args.max_per_family:
            print(f"    -> diversity guard: {spec.strategy_family} already at cap on {symbol}")
            continue

        champion_score = float(m["expectancy_r"])
        pool, decision = add_champion(
            pool, spec_dict, champion_score, generation_id=generation_id,
            cap=args.cap, robustness=robustness or None,
            live_stats=live_stats,
        )
        print(f"    -> pool: {decision.get('action')}")
        if decision.get("action") in {"ADDED", "REPLACED"}:
            added += 1
            persist_strategy_spec(spec, str(settings.STRATEGY_CANDIDATE_REGISTRY_PATH))
            append_registry_record(
                str(settings.STRATEGY_ACTIVE_REGISTRY_PATH),
                {"decision": decision, "generation_id": generation_id,
                 "strategy_id": decision.get("strategy_id"),
                 "search_evaluations": mined["search_evaluations"]},
                registry_name=ACTIVE_STRATEGY_REGISTRY_NAME,
                id_field="active_strategy_registry_record_id",
                hash_field="active_strategy_registry_record_sha256",
                id_prefix="active_strategy",
            )

    if not args.dry_run:
        save_pool(pool_file, pool)
        save_counters(
            str(settings.STRATEGY_FACTORY_STATE_PATH),
            generation_seq=counters["generation_seq"] + 1,
            strategy_seq=strategy_seq,
            now=utc_now_iso(),
        )
    print(f"done: {added} mined strateg{'y' if added == 1 else 'ies'} added to the pool"
          + (" (dry run: pool untouched)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

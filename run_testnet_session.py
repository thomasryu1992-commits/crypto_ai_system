"""Operator harness: run N signed-testnet open/close sessions with stats.

Each session opens a small long and closes it (reduceOnly), both through the
guarded path, and reconciles each leg. Prints per-session results and an
aggregate (fill/reconcile rate, slippage, latency, round-trip cost) and writes
a report. Stops early when the daily order cap is hit (the guard blocks).

    py scripts/check_testnet_readiness.py --probe    # verify setup first
    py run_testnet_session.py --sessions 3 --confirm

Each session uses 2 orders, so --sessions is bounded by
SIGNED_TESTNET_MAX_DAILY_ORDER_COUNT / 2. Testnet (fake) funds only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _bootstrap() -> None:
    root = Path(__file__).resolve().parent
    for p in (str(root / "src"), str(root)):
        if p not in sys.path:
            sys.path.insert(0, p)
    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env")
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
    from core.json_io import atomic_write_json
    from crypto_ai_system.data.binance_futures_collector import BinanceFuturesPublicClient
    from crypto_ai_system.execution.order_executor import execute_order_intent
    from crypto_ai_system.execution.signed_testnet_adapter import SignedTestnetAdapter
    from crypto_ai_system.execution.signed_testnet_preflight import (
        check_config_readiness,
        probe_auth,
    )
    from crypto_ai_system.execution.signed_testnet_reconciliation import (
        run_signed_testnet_reconciliation,
    )
    from crypto_ai_system.execution.testnet_session_harness import run_sessions

    parser = argparse.ArgumentParser(description="Run repeated signed-testnet sessions.")
    parser.add_argument("--confirm", action="store_true", help="required to actually trade")
    parser.add_argument("--sessions", type=int, default=1, help="number of open/close sessions")
    parser.add_argument("--notional", type=float, default=None,
                        help="target notional per order (default: the configured cap)")
    parser.add_argument("--symbol", default=None, help="override symbol")
    args = parser.parse_args(argv)

    readiness = check_config_readiness()
    if not readiness["ready"]:
        print("NOT READY:")
        for block in readiness["blocks"]:
            print(f"  - {block}")
        return 1
    probe = probe_auth()
    if not probe.get("ok"):
        print(f"auth probe FAILED — {probe.get('error') or probe.get('http_status')}")
        return 1
    print(f"preflight OK (USDT testnet balance: {probe.get('usdt_balance')})")

    if not args.confirm:
        print("dry preflight only. Re-run with --confirm to trade.")
        return 0

    symbol = to_binance_symbol(args.symbol or settings.SYMBOL)
    notional = args.notional if args.notional is not None else readiness["notional_cap_usdt"]

    public = BinanceFuturesPublicClient(base_url="https://fapi.binance.com")

    def price_fn() -> float:
        frame = public.klines(symbol, "1m", 1)
        return float(frame.iloc[-1]["close"])

    def balance_fn() -> float:
        adapter = SignedTestnetAdapter(
            api_key=settings.BINANCE_API_KEY,
            api_secret=settings.BINANCE_API_SECRET,
            base_url=settings.BINANCE_TESTNET_BASE_URL,
        )
        result = adapter.get_balance()
        for asset in (result.get("response") or []):
            if isinstance(asset, dict) and asset.get("asset") == "USDT":
                try:
                    return float(asset.get("balance"))
                except (TypeError, ValueError):
                    return 0.0
        return 0.0

    report = run_sessions(
        args.sessions, symbol, notional, price_fn,
        submit_fn=execute_order_intent,
        reconcile_fn=run_signed_testnet_reconciliation,
        balance_fn=balance_fn,
    )

    for session in report["sessions"]:
        o = session["open"]
        c = session["close"] or {}
        print(f"[{session['status']}] {session['session_id']} qty={session['quantity']} "
              f"open={o.get('reconcile_status')}({o.get('slippage_bps')}bps) "
              f"close={c.get('reconcile_status')}")

    print("=== aggregate ===")
    print(json.dumps(report["aggregate"], indent=2, default=str))

    report_path = settings.LATEST_DIR / "signed_testnet_session_report.json"
    atomic_write_json(report_path, report)
    print(f"report written: {report_path}")

    agg = report["aggregate"]
    ok = agg["orders_submitted"] > 0 and agg["reconcile_rate"] == 1.0
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

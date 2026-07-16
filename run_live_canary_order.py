"""Operator one-shot: place a SINGLE live-canary mainnet order and reconcile it.

This is the live-canary execution boundary — a separate approval + runtime from
the pipeline (which refuses live) and from the signed-testnet path. It signs and
submits ONE tiny order to Binance USD-M Futures **mainnet**, then queries the
exchange and prints the reconciliation (fill / position / balance).

Prerequisites, all fail-closed (any missing one blocks):
  * the read-only preparation gate is READY
      py scripts/check_live_canary_readiness.py --probe
  * env is set for a SEPARATE order-capable live key + the caps + the distinct
    live confirmation phrase:
      LIVE_CANARY_ENABLED=true
      LIVE_CANARY_PLACE_ORDER_ENABLED=true
      LIVE_CANARY_CONFIRMATION=I_UNDERSTAND_THIS_PLACES_A_REAL_LIVE_MAINNET_ORDER
      LIVE_CANARY_API_KEY=... / LIVE_CANARY_API_SECRET=...
      LIVE_CANARY_MAX_ORDER_NOTIONAL_USDT=150   # <= absolute ceiling (200)

BTCUSDT has a ~100 USDT minimum notional; the default cap (5) blocks on purpose.
This places a REAL order with REAL money — Claude does not run it. Operator only.

    py run_live_canary_order.py             # dry preflight (no order)
    py run_live_canary_order.py --confirm   # place ONE live order + reconcile
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


def _current_price(binance_symbol: str) -> float:
    from crypto_ai_system.data.binance_futures_collector import BinanceFuturesPublicClient

    client = BinanceFuturesPublicClient(base_url="https://fapi.binance.com")
    frame = client.klines(binance_symbol, "1m", 1)
    if frame is None or frame.empty:
        raise RuntimeError(f"could not fetch price for {binance_symbol}")
    return float(frame.iloc[-1]["close"])


def main(argv: list[str] | None = None) -> int:
    _bootstrap()
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    import config.settings as settings
    from collectors.real_market_data import to_binance_symbol
    from core.json_io import atomic_write_json
    from core.time_utils import utc_now_iso
    from crypto_ai_system.execution.idempotency import enrich_order_identity
    from crypto_ai_system.execution.live_canary_execution import (
        run_live_canary_reconciliation,
        submit_live_canary_order,
    )
    from crypto_ai_system.execution.live_canary_final_guard import evaluate_live_canary_final_guard

    parser = argparse.ArgumentParser(description="Place one live-canary mainnet order and reconcile.")
    parser.add_argument("--confirm", action="store_true", help="required to actually submit")
    parser.add_argument("--side", choices=["BUY", "SELL"], default="BUY")
    parser.add_argument("--reduce-only", action="store_true",
                        help="close/reduce an existing position (sends reduceOnly)")
    parser.add_argument("--notional", type=float, default=None,
                        help="target order notional in USDT (default: the configured cap)")
    parser.add_argument("--symbol", default=None, help="override symbol (canonical or Binance)")
    args = parser.parse_args(argv)

    # 1) Size a candidate order within the cap, so the guard sees a real notional.
    symbol = to_binance_symbol(args.symbol or settings.SYMBOL)
    price = _current_price(symbol)
    cap = float(settings.LIVE_CANARY_MAX_ORDER_NOTIONAL_USDT)
    ceiling = float(settings.LIVE_CANARY_ABSOLUTE_MAX_NOTIONAL_USDT)
    target_notional = args.notional if args.notional is not None else min(cap, ceiling)
    quantity = round(target_notional / price, 3)
    if quantity < 0.001:
        quantity = 0.001
    notional = round(quantity * price, 2)

    intent = {
        "created_at": utc_now_iso(),
        "status": "ORDER_INTENT_CREATED",
        "execution_stage": "live_canary",
        "decision_stage": "live_canary",
        "symbol": symbol,
        "direction": "LONG" if args.side == "BUY" else "SHORT",
        "side": args.side,
        "order_type": "MARKET_LIVE_CANARY",
        "order_type_exchange": "MARKET",
        "entry_price": price,
        "quantity": quantity,
        "order_notional_usdt": notional,
        "notional_usdt": notional,
        "reduce_only": args.reduce_only,
        # Connectivity-only: a canary verifies live signing/submission/reconciliation,
        # NOT a strategy signal. Marked so it can never be aggregated as performance.
        "connectivity_test": True,
        "risk_gate_id": f"live_canary_connectivity_{utc_now_iso()}",
        "order_intent_created": True,
    }
    intent = enrich_order_identity(intent)

    # 2) Dry guard evaluation first — always shows why it would block.
    guard = evaluate_live_canary_final_guard(intent)
    print(f"order: {args.side} {quantity} {symbol} @ ~{price} (notional ~{notional} USDT)")
    print(f"final guard: {guard['status']}")
    if not guard.get("approved"):
        for reason in (guard.get("blocks") or []) + (guard.get("repairs") or []):
            print(f"  - {reason}")

    if not args.confirm:
        print("dry preflight only. Re-run with --confirm to place ONE live canary order.")
        return 0 if guard.get("approved") else 1
    if not guard.get("approved"):
        print("refusing to submit: final guard did not approve.")
        return 1

    # 3) Submit exactly one order (guard re-runs inside), then reconcile.
    atomic_write_json(settings.ORDER_INTENT_PATH, intent)
    order_result = submit_live_canary_order(intent)
    print("=== order result ===")
    print(json.dumps({k: order_result.get(k) for k in
                      ("status", "state", "exchange_order_id", "client_order_id",
                       "external_order_submission_performed")}, indent=2, default=str))

    submit = order_result.get("submit_result")
    if submit and not submit.get("submitted"):
        print(f"exchange rejected the order: {submit.get('error')} (http {submit.get('http_status')})")

    reconciliation = run_live_canary_reconciliation()
    print("=== reconciliation ===")
    print(json.dumps({k: reconciliation.get(k) for k in
                      ("status", "filled", "mismatches", "actual")}, indent=2, default=str))

    return 0 if order_result.get("status") == "LIVE_CANARY_ORDER_SUBMITTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

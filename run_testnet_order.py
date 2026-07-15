"""Operator one-shot: place a single signed testnet order and reconcile it.

This is a connectivity/plumbing check for the signed-testnet path: it signs and
submits ONE small order to the Binance USD-M Futures **testnet**, then queries
the exchange and prints the reconciliation (fill / position / balance).

It is gated the same way as the pipeline (preflight + final guard + hard caps)
and requires --confirm. It uses testnet (fake) funds only.

    py scripts/check_testnet_readiness.py --probe     # verify setup first
    py run_testnet_order.py --confirm                 # place one order + reconcile

Notes:
  * Binance USD-M Futures BTCUSDT has a minimum notional (~100 USDT). Set
    SIGNED_TESTNET_MAX_ORDER_NOTIONAL_USDT high enough (e.g. 150) — it is
    testnet fake money — or the final guard will block the order.
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
    # Load .env before importing config (config reads env at import time).
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
    from crypto_ai_system.execution.order_executor import execute_order_intent
    from crypto_ai_system.execution.signed_testnet_preflight import (
        check_config_readiness,
        probe_auth,
    )
    from crypto_ai_system.execution.signed_testnet_reconciliation import (
        run_signed_testnet_reconciliation,
    )

    parser = argparse.ArgumentParser(description="Place one signed testnet order and reconcile.")
    parser.add_argument("--confirm", action="store_true", help="required to actually submit")
    parser.add_argument("--side", choices=["BUY", "SELL"], default="BUY")
    parser.add_argument("--notional", type=float, default=None,
                        help="target order notional in USDT (default: the configured cap)")
    parser.add_argument("--symbol", default=None, help="override symbol (canonical or Binance)")
    args = parser.parse_args(argv)

    # 1) Preflight (config + signed read-only auth probe).
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
        print("dry preflight only. Re-run with --confirm to place ONE testnet order.")
        return 0

    # 2) Size a single order within the cap.
    symbol = to_binance_symbol(args.symbol or settings.SYMBOL)
    price = _current_price(symbol)
    target_notional = args.notional if args.notional is not None else readiness["notional_cap_usdt"]
    quantity = round(target_notional / price, 3)
    if quantity < 0.001:
        quantity = 0.001
    notional = round(quantity * price, 2)
    print(f"order: {args.side} {quantity} {symbol} @ ~{price} (notional ~{notional} USDT)")

    # 3) Build a gate-approved connectivity-test intent.
    intent = {
        "created_at": utc_now_iso(),
        "status": "ORDER_INTENT_CREATED",
        "execution_stage": "signed_testnet",
        "decision_stage": "signed_testnet",
        "symbol": symbol,
        "direction": "LONG" if args.side == "BUY" else "SHORT",
        "side": args.side,
        "order_type": "MARKET_SIGNED_TESTNET",
        "order_type_exchange": "MARKET",
        "entry_price": price,
        "quantity": quantity,
        "order_notional_usdt": notional,
        "notional_usdt": notional,
        "pre_order_risk_gate_approved": True,
        "risk_gate_id": f"connectivity_test_{utc_now_iso()}",
        "order_intent_created": True,
    }
    intent = enrich_order_identity(intent)
    atomic_write_json(settings.ORDER_INTENT_PATH, intent)

    # 4) Submit (executor runs the final guard first), then reconcile.
    order_result = execute_order_intent(intent)
    print("=== order result ===")
    print(json.dumps({k: order_result.get(k) for k in
                      ("status", "state", "exchange_order_id", "client_order_id",
                       "external_order_submission_performed")}, indent=2, default=str))

    reconciliation = run_signed_testnet_reconciliation()
    print("=== reconciliation ===")
    print(json.dumps({k: reconciliation.get(k) for k in
                      ("status", "filled", "mismatches", "actual")}, indent=2, default=str))

    return 0 if order_result.get("status") == "SIGNED_TESTNET_ORDER_SUBMITTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

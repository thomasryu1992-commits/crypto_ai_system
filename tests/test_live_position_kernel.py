"""L5: live position kernel — real open/close lifecycle feeding the L1 ledger."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config.settings as settings
from crypto_ai_system.config import load_config
from crypto_ai_system.execution import live_position_kernel as kernel
from crypto_ai_system.execution import live_order_final_guard as guard_mod

CONFIRM = "I_UNDERSTAND_THIS_TRADES_LIVE_FUNDS_AUTONOMOUSLY"


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    c = load_config(".")
    c.settings.setdefault("storage", {})["latest_dir"] = str(tmp_path / "latest")
    # Ledger writes go to a tmp registry.
    monkeypatch.setattr(settings, "LIVE_OUTCOME_REGISTRY_PATH",
                        tmp_path / "live_outcome_registry.jsonl", raising=False)
    return c


def _order_result(entry=60000.0, qty=0.001, sl=59000.0, tp=62000.0):
    return {
        "external_order_submission_performed": True,
        "client_order_id": "c1",
        "exchange_order_id": 111,
        "intent": {
            "symbol": "BTCUSDT", "side": "BUY", "direction": "LONG",
            "entry_price": entry, "quantity": qty,
            "stop_loss": sl, "take_profit": tp,
            "strategy_id": "S001", "risk_gate_id": "rg1",
            "order_intent_id": "oi1", "research_signal_id": "rs1", "decision_id": "d1",
        },
    }


def _recon(entry=60000.0, qty=0.001, status="RECONCILED", order_status="FILLED"):
    return {"status": status, "actual": {"order_status": order_status,
                                         "avg_fill_price": entry, "executed_qty": qty}}


def _open(cfg, **kw):
    return kernel.open_from_live_execution(_order_result(**{k: v for k, v in kw.items() if k in {"entry", "qty", "sl", "tp"}}),
                                           _recon(entry=kw.get("entry", 60000.0), qty=kw.get("qty", 0.001)),
                                           cfg=cfg)


# -- open ---------------------------------------------------------------------

def test_open_from_filled_reconciled_entry(cfg):
    pos = _open(cfg)
    assert pos is not None and pos["status"] == "OPEN"
    assert kernel.has_open_live_position(cfg)
    assert kernel.open_live_notional_usdt(cfg) == pytest.approx(60.0)
    assert pos["strategy_id"] == "S001"


def test_open_refused_without_reconciliation(cfg):
    pos = kernel.open_from_live_execution(_order_result(), _recon(status="MISMATCH"), cfg=cfg)
    assert pos is None
    assert not kernel.has_open_live_position(cfg)


def test_open_refused_without_submission(cfg):
    result = _order_result()
    result["external_order_submission_performed"] = False
    assert kernel.open_from_live_execution(result, _recon(), cfg=cfg) is None


# -- settle: real close -------------------------------------------------------

def _fake_close(fill_price, order_status="FILLED"):
    submitted = {"n": 0}

    def submit(intent):
        submitted["n"] += 1
        return {"external_order_submission_performed": True,
                "client_order_id": "close1", "exchange_order_id": 222,
                "status": "LIVE_CLOSE_ORDER_SUBMITTED"}

    def query(symbol, client_order_id):
        return {"ok": True, "response": {"status": order_status,
                                         "avgPrice": str(fill_price), "executedQty": "0.001"}}

    return submit, query, submitted


def test_stop_loss_closes_for_real_and_feeds_ledger(cfg):
    _open(cfg)  # LONG 0.001 @ 60000, SL 59000
    submit, query, submitted = _fake_close(fill_price=58990.0)
    settlement = kernel.settle_open_live_position(
        {"high": 60100.0, "low": 58900.0},  # low breaches SL
        last_close=59000.0, cfg=cfg, submit_close=submit, query_order=query,
    )
    assert settlement["status"] == "CLOSED"
    assert settlement["close_reason"] == "stop_loss"
    assert submitted["n"] == 1
    # Realized P&L from the REAL fills: (58990 - 60000) * 0.001
    assert settlement["realized_pnl_usdt"] == pytest.approx(-1.01)
    assert not kernel.has_open_live_position(cfg)
    # The L1 ledger saw it (registry path patched to tmp).
    from crypto_ai_system.execution.live_pnl_ledger import live_daily_realized_pnl_usdt
    assert live_daily_realized_pnl_usdt() == pytest.approx(-1.01)


def test_take_profit_close(cfg):
    _open(cfg)
    submit, query, _ = _fake_close(fill_price=62010.0)
    settlement = kernel.settle_open_live_position(
        {"high": 62100.0, "low": 59900.0},
        last_close=62000.0, cfg=cfg, submit_close=submit, query_order=query,
    )
    assert settlement["close_reason"] == "take_profit"
    assert settlement["realized_pnl_usdt"] == pytest.approx(2.01)


def test_no_exit_keeps_position_open(cfg):
    _open(cfg)
    settlement = kernel.settle_open_live_position(
        {"high": 60500.0, "low": 59500.0},  # neither SL nor TP
        last_close=60200.0, cfg=cfg,
        submit_close=lambda i: pytest.fail("must not submit"),
        query_order=lambda s, c: pytest.fail("must not query"),
    )
    assert settlement is None
    assert kernel.has_open_live_position(cfg)


def test_blocked_close_keeps_position_open(cfg):
    _open(cfg)

    def blocked_submit(intent):
        return {"external_order_submission_performed": False,
                "status": "LIVE_CLOSE_BLOCKED", "final_guard": {"blocks": ["x"]}}

    settlement = kernel.settle_open_live_position(
        {"high": 60100.0, "low": 58900.0}, last_close=59000.0, cfg=cfg,
        submit_close=blocked_submit, query_order=lambda s, c: {},
    )
    assert settlement["status"] == "CLOSE_FAILED"
    assert kernel.has_open_live_position(cfg)  # never fabricate a close


def test_unconfirmed_fill_keeps_position_open(cfg):
    _open(cfg)
    submit, query, _ = _fake_close(fill_price=0.0, order_status="NEW")
    settlement = kernel.settle_open_live_position(
        {"high": 60100.0, "low": 58900.0}, last_close=59000.0, cfg=cfg,
        submit_close=submit, query_order=query,
    )
    assert settlement["status"] == "CLOSE_UNCONFIRMED"
    assert kernel.has_open_live_position(cfg)


# -- close guard exemptions -----------------------------------------------------

def _close_intent():
    return {"status": "ORDER_INTENT_CREATED", "symbol": "BTCUSDT", "quantity": 0.001,
            "reduce_only": True}


def _structural_env(monkeypatch):
    for name, val in {
        "LIVE_STRATEGY_ORDER_ENABLED": True,
        "LIVE_STRATEGY_PLACE_ORDER_ENABLED": True,
        "LIVE_STRATEGY_CONFIRMATION": CONFIRM,
        "LIVE_STRATEGY_CONFIRMATION_PHRASE": CONFIRM,
        "LIVE_STRATEGY_BASE_URL": "https://fapi.binance.com",
        "LIVE_STRATEGY_API_KEY": "k",
        "LIVE_STRATEGY_API_SECRET": "s",
    }.items():
        monkeypatch.setattr(settings, name, val, raising=False)


def test_close_guard_allows_flatten_under_kill_switch_and_breaker(monkeypatch):
    _structural_env(monkeypatch)
    # Kill switch engaged + loss breaker tripped + no promotion + zero caps:
    # a reduceOnly close must STILL be allowed (risk reduction).
    monkeypatch.setattr(settings, "LIVE_STRATEGY_MANUAL_KILL_SWITCH", True, raising=False)
    monkeypatch.setattr(settings, "LIVE_STRATEGY_DAILY_LOSS_LIMIT_USDT", 0.0, raising=False)
    verdict = guard_mod.evaluate_live_close_guard(_close_intent())
    assert verdict["approved"] is True, verdict["blocks"]


def test_close_guard_requires_reduce_only(monkeypatch):
    _structural_env(monkeypatch)
    intent = _close_intent()
    intent["reduce_only"] = False
    verdict = guard_mod.evaluate_live_close_guard(intent)
    assert verdict["approved"] is False


def test_close_guard_blocked_when_boundary_disabled():
    # Shipped defaults: the whole live boundary is off -> closes are manual.
    verdict = guard_mod.evaluate_live_close_guard(_close_intent())
    assert verdict["approved"] is False

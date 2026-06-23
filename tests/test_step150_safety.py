from __future__ import annotations

from execution.idempotency import make_client_order_id, make_idempotency_key
from execution.retry_policy import classify_exchange_error
from integrations.spreadsheet_writer import normalize_row
from trading.atr import stop_distance_bps_from_atr
from trading.paper_engine import build_paper_position, update_position_conservative


def test_spreadsheet_row_has_row_id():
    row = normalize_row("07_Trade_Decision", {
        "event_time": "2026-01-01T00:00:00+00:00",
        "symbol": "BTCUSDT",
        "event_type": "TRADE_DECISION",
        "final_decision": "WATCH_LONG",
    })
    assert row["row_id"]
    assert row["schema_version"] == "v3"


def test_atr_stop_has_min_max_guard():
    candles = []
    price = 100.0
    for i in range(20):
        candles.append({"open": price, "high": price + 0.01, "low": price - 0.01, "close": price, "volume": 100})
    info = stop_distance_bps_from_atr(price, candles)
    assert info["final_stop_distance_bps"] >= info["min_stop_loss_bps"]
    assert info["final_stop_distance_bps"] <= info["max_stop_loss_bps"]


def test_idempotency_client_order_id_is_stable():
    key1 = make_idempotency_key("BTCUSDT", "LONG", "s1", "t1", "sig1")
    key2 = make_idempotency_key("BTCUSDT", "LONG", "s1", "t1", "sig1")
    assert key1 == key2
    cid = make_client_order_id("BTCUSDT", "LONG", key1)
    assert cid.startswith("CAI_BTCUSDT_LONG_")
    assert len(cid) <= 36


def test_retry_policy_timeout_unknown():
    policy = classify_exchange_error(error_name="Network Timeout")
    assert policy["state"] == "UNKNOWN"
    assert "QUERY" in policy["action"]


def test_retry_policy_429_unknown_no_immediate_retry():
    policy = classify_exchange_error(status_code=429)
    assert policy["state"] == "UNKNOWN"
    assert policy["retry"] is False


def test_conservative_paper_engine_sl_first_for_long():
    position = build_paper_position("LONG", 100.0, "unit_test")
    candle = {"high": position["take_profit"] + 1, "low": position["stop_loss"] - 1, "close": 100}
    closed, active = update_position_conservative(position, candle)
    assert closed["result"] == "LOSS"
    assert active is None

"""L1: live realized-P&L ledger and daily-loss circuit breaker."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.execution import live_pnl_ledger as ledger


def _reg(tmp_path):
    return str(tmp_path / "live_outcome_registry.jsonl")


def test_record_and_sum_today(tmp_path):
    reg = _reg(tmp_path)
    ledger.record_live_outcome(realized_pnl_usdt=1.5, symbol="BTCUSDT", side="BUY",
                               quantity=0.001, registry_file=reg)
    ledger.record_live_outcome(realized_pnl_usdt=-0.7, symbol="BTCUSDT", side="BUY",
                               quantity=0.001, registry_file=reg)
    assert ledger.live_daily_realized_pnl_usdt(registry_file=reg) == 0.8


def test_only_todays_outcomes_counted(tmp_path):
    reg = _reg(tmp_path)
    ledger.record_live_outcome(realized_pnl_usdt=-5.0, symbol="BTCUSDT", side="BUY",
                               quantity=0.001, closed_at_utc="2000-01-01T00:00:00Z", registry_file=reg)
    ledger.record_live_outcome(realized_pnl_usdt=-2.0, symbol="BTCUSDT", side="BUY",
                               quantity=0.001, registry_file=reg)  # today
    # The old loss must not count toward today's total.
    assert ledger.live_daily_realized_pnl_usdt(registry_file=reg) == -2.0


def test_unconfigured_limit_is_failclosed(tmp_path):
    reg = _reg(tmp_path)
    # No limit / non-positive limit -> treated as breached (blocks live).
    assert ledger.daily_loss_limit_breached(None, registry_file=reg) is True
    assert ledger.daily_loss_limit_breached(0, registry_file=reg) is True
    assert ledger.daily_loss_limit_breached(-10, registry_file=reg) is True


def test_breaker_trips_at_limit(tmp_path):
    reg = _reg(tmp_path)
    ledger.record_live_outcome(realized_pnl_usdt=-9.0, symbol="BTCUSDT", side="BUY",
                               quantity=0.001, registry_file=reg)
    assert ledger.daily_loss_limit_breached(10.0, registry_file=reg) is False
    ledger.record_live_outcome(realized_pnl_usdt=-2.0, symbol="BTCUSDT", side="BUY",
                               quantity=0.001, registry_file=reg)
    # -11 <= -10 -> breached
    assert ledger.daily_loss_limit_breached(10.0, registry_file=reg) is True


def test_snapshot_written(tmp_path):
    reg = _reg(tmp_path)
    status = tmp_path / "live_risk_status.json"
    ledger.record_live_outcome(realized_pnl_usdt=-3.0, symbol="BTCUSDT", side="BUY",
                               quantity=0.001, registry_file=reg)
    snap = ledger.live_risk_snapshot(limit_usdt=10.0, registry_file=reg, status_path=status)
    assert snap["live_daily_pnl_usdt"] == -3.0
    assert snap["daily_loss_limit_configured"] is True
    assert snap["daily_loss_limit_breached"] is False
    assert status.exists()


def test_snapshot_unconfigured_limit_breached(tmp_path):
    reg = _reg(tmp_path)
    status = tmp_path / "live_risk_status.json"
    snap = ledger.live_risk_snapshot(limit_usdt=0.0, registry_file=reg, status_path=status)
    assert snap["daily_loss_limit_configured"] is False
    assert snap["daily_loss_limit_breached"] is True

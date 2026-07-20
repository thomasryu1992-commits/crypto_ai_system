"""Risk guard history read must fail CLOSED (QA fix).

Before this fix an unreadable outcome registry silently fell back to the
retired paper_trades.json, resetting every loss limit to zero history —
allow_new_position stayed True right after a string of real losses.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import risk.risk_guard as rg
from crypto_ai_system.registry import base_registry


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(rg, "RISK_STATUS_PATH", tmp_path / "risk_status.json")
    monkeypatch.setattr(rg, "log_event", lambda *a, **k: None)


def test_unreadable_registry_blocks_new_positions(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    def broken(*a, **k):
        raise base_registry.RegistryIntegrityError("torn line")

    monkeypatch.setattr(base_registry, "load_registry_records", broken)
    result = rg.run_risk_guard()
    assert result["allow_new_position"] is False
    assert result["status"] == "BLOCK_NEW_POSITION"
    assert "risk_history_unreadable" in result["problems"]


def test_readable_registry_computes_limits_normally(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(base_registry, "load_registry_records", lambda *a, **k: [])
    result = rg.run_risk_guard()
    assert result["allow_new_position"] is True
    assert result["problems"] == []


def _old_rows(r_values):
    # Timestamps far in the past so daily/weekly limits stay clear and only the
    # drawdown breaker is exercised.
    return [
        {"outcome_closed": True, "result_R": r, "created_at_utc": "2020-01-01T00:00:00Z",
         "win_loss": "LOSS" if r < 0 else "WIN"}
        for r in r_values
    ]


def test_drawdown_breaker_trips_on_current_drawdown(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    # 11 straight -1R: current drawdown -11R exceeds the default 10R limit
    # (-10% equity at 1% risk per trade).
    monkeypatch.setattr(
        base_registry, "load_registry_records", lambda *a, **k: _old_rows([-1.0] * 11)
    )
    result = rg.run_risk_guard()
    assert "max_drawdown_proxy_breached" in result["problems"]
    assert result["allow_new_position"] is False


def test_drawdown_breaker_unlatches_after_recovery(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    # Historical 11R dip, then a full recovery to a new peak: the breaker must
    # release (previously the all-time max latched it forever).
    rows = _old_rows([-1.0] * 11 + [4.0, 4.0, 4.0, 1.0])
    monkeypatch.setattr(base_registry, "load_registry_records", lambda *a, **k: rows)
    result = rg.run_risk_guard()
    assert "max_drawdown_proxy_breached" not in result["problems"]
    assert result["max_drawdown_r"] == -11.0  # history still reported
    assert result["drawdown_r"] == 0.0  # at a new peak now


def test_losses_in_registry_still_trip_the_limits(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    from core.time_utils import utc_now_iso

    rows = [
        {"outcome_closed": True, "result_R": -1.0, "created_at_utc": utc_now_iso(), "win_loss": "LOSS"}
        for _ in range(5)
    ]
    monkeypatch.setattr(base_registry, "load_registry_records", lambda *a, **k: rows)
    result = rg.run_risk_guard()
    assert result["allow_new_position"] is False
    assert "daily_loss_limit_breached" in result["problems"]

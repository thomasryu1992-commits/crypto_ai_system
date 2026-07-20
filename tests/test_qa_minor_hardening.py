"""Remaining QA minor items: signal staleness wiring, reconciler fallback
guard, research-agent artifact ordering."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.research.active_research_signal import build_active_research_signal


# -- research signal carries REAL staleness -------------------------------------

def _snapshot(**over):
    snap = {"symbol": "BTCUSDT", "timeframe": "1h", "last_close": 60000.0,
            "last_candle_time": "2026-07-20T00:00:00+00:00",
            "is_synthetic": False, "is_fallback": False, "is_stale": False}
    snap.update(over)
    return snap


def test_signal_stale_follows_snapshot_staleness():
    fresh = build_active_research_signal(_snapshot(is_stale=False), {"scenario": "Bullish"})
    assert fresh["stale"] is False and fresh["data_stale"] is False

    stale = build_active_research_signal(_snapshot(is_stale=True), {"scenario": "Bullish"})
    assert stale["stale"] is True and stale["data_stale"] is True


def test_signal_missing_staleness_defaults_to_fresh_not_crash():
    snap = _snapshot()
    snap.pop("is_stale")
    signal = build_active_research_signal(snap, {})
    assert signal["stale"] is False


# -- reconciler legacy fallback never fakes RECONCILED for external orders ------

def _wire_reconciler(monkeypatch, tmp_path, order):
    import crypto_ai_system.execution.reconciler as rec
    from core.json_io import atomic_write_json
    from crypto_ai_system.config import AppConfig

    order_path = tmp_path / "order_result.json"
    atomic_write_json(order_path, order)
    monkeypatch.setattr(rec, "ORDER_RESULT_PATH", order_path)
    monkeypatch.setattr(rec, "PAPER_STATE_PATH", tmp_path / "paper_state.json")
    monkeypatch.setattr(rec, "RECONCILIATION_PATH", tmp_path / "reconciliation.json")
    monkeypatch.setattr(rec, "log_event", lambda *a, **k: None)
    # run_reconciler imports load_config lazily from crypto_ai_system.config —
    # patch it THERE. No paper_execution_record in the tmp latest dir -> the
    # legacy fallback runs.
    monkeypatch.setattr(
        "crypto_ai_system.config.load_config",
        lambda root=".": AppConfig(root=tmp_path, settings={"storage": {"latest_dir": "latest"}}),
    )
    return rec


def test_fallback_reconciles_paper_orders(monkeypatch, tmp_path):
    rec = _wire_reconciler(monkeypatch, tmp_path,
                           {"status": "PAPER_FILLED", "external_order_submission_performed": False})
    result = rec.run_reconciler()
    assert result["status"] == "RECONCILED"


def test_fallback_refuses_to_fake_reconcile_external_submission(monkeypatch, tmp_path):
    rec = _wire_reconciler(monkeypatch, tmp_path,
                           {"status": "SIGNED_TESTNET_ORDER_SUBMITTED",
                            "external_order_submission_performed": True})
    result = rec.run_reconciler()
    assert result["status"] == "UNRECONCILED"
    assert "legacy_fallback_cannot_reconcile_external_submission" in result["notes"]


# -- research agent: a failed cycle emits NO signal artifact --------------------

def test_failed_research_cycle_does_not_emit_a_signal(monkeypatch):
    import crypto_ai_system.pipeline.research_agent as ra
    from crypto_ai_system.pipeline.contracts import PipelineContext, StageStatus

    monkeypatch.setattr(ra, "run_research_cycle", lambda: None)
    monkeypatch.setattr(
        ra, "run_active_research_signal",
        lambda **kw: (_ for _ in ()).throw(AssertionError("signal must not be emitted")),
    )

    result = ra.ResearchAgent().execute(PipelineContext())
    assert result.status is StageStatus.BLOCKED
    assert result.fatal is True


def test_failed_decision_still_blocks_after_signal(monkeypatch):
    import crypto_ai_system.pipeline.research_agent as ra
    from crypto_ai_system.pipeline.contracts import PipelineContext, StageStatus

    monkeypatch.setattr(ra, "run_research_cycle", lambda: {"scenario": "Bullish"})
    monkeypatch.setattr(ra, "run_active_research_signal", lambda **kw: {"signal": "x"})
    monkeypatch.setattr(ra, "run_research_decision", lambda: None)

    result = ra.ResearchAgent().execute(PipelineContext())
    assert result.status is StageStatus.BLOCKED

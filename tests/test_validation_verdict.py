"""P1: ValidationVerdict — the typed intra-cycle gate contract.

The verdict is produced once by the validation agent and consumed as a
required input by every decision builder (P2). A missing verdict must always
resolve to blocked, never to allowed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.pipeline.contracts import PipelineContext, ValidationVerdict


def test_fail_closed_blocks_everything():
    verdict = ValidationVerdict.fail_closed()
    assert verdict.allow_new_position is False
    assert verdict.data_health == {}
    assert verdict.risk_status == {}


def test_verdict_is_immutable():
    verdict = ValidationVerdict.fail_closed()
    with pytest.raises(Exception):
        verdict.allow_new_position = True  # type: ignore[misc]


def test_from_latest_files_fails_closed_on_missing_files(monkeypatch, tmp_path):
    import config.settings as settings

    monkeypatch.setattr(settings, "DATA_HEALTH_PATH", tmp_path / "missing_dh.json")
    monkeypatch.setattr(settings, "RISK_STATUS_PATH", tmp_path / "missing_risk.json")
    verdict = ValidationVerdict.from_latest_files()
    assert verdict.allow_new_position is False


def test_from_latest_files_reads_both_gates(monkeypatch, tmp_path):
    import config.settings as settings
    from core.json_io import atomic_write_json

    dh, rs = tmp_path / "dh.json", tmp_path / "rs.json"
    atomic_write_json(dh, {"allow_trading": True})
    atomic_write_json(rs, {"allow_new_position": True, "daily_pnl_r": -0.5})
    monkeypatch.setattr(settings, "DATA_HEALTH_PATH", dh)
    monkeypatch.setattr(settings, "RISK_STATUS_PATH", rs)

    verdict = ValidationVerdict.from_latest_files()
    assert verdict.allow_new_position is True
    assert verdict.risk_status["daily_pnl_r"] == -0.5

    # Either gate alone blocks.
    atomic_write_json(dh, {"allow_trading": False})
    assert ValidationVerdict.from_latest_files().allow_new_position is False


def test_validation_agent_populates_the_typed_slot(monkeypatch):
    import crypto_ai_system.pipeline.validation_agent as va

    monkeypatch.setattr(va, "run_data_health_check", lambda: {"allow_trading": True})
    monkeypatch.setattr(va, "run_risk_guard", lambda: {"allow_new_position": True, "daily_pnl_r": 0.0})

    ctx = PipelineContext()
    result = va.ValidationAgent().execute(ctx)

    assert ctx.verdict is not None
    assert ctx.verdict.allow_new_position is True
    assert ctx.verdict.risk_status["daily_pnl_r"] == 0.0
    # Legacy outputs stay identical until P3.
    assert result.outputs["allow_new_position"] is True


def test_validation_agent_verdict_blocks_when_a_gate_blocks(monkeypatch):
    import crypto_ai_system.pipeline.validation_agent as va

    monkeypatch.setattr(va, "run_data_health_check", lambda: {"allow_trading": True})
    monkeypatch.setattr(va, "run_risk_guard", lambda: {"allow_new_position": False})

    ctx = PipelineContext()
    va.ValidationAgent().execute(ctx)
    assert ctx.verdict.allow_new_position is False
    assert ctx.verdict.data_health["allow_trading"] is True  # raw reports carried


def test_routing_agent_populates_the_typed_slot_when_disabled():
    from crypto_ai_system.pipeline.strategy_routing_agent import StrategyRoutingAgent

    ctx = PipelineContext()
    StrategyRoutingAgent().execute(ctx)  # flag defaults False
    assert ctx.strategy_routing == {"status": "DISABLED", "order_candidate_count": 0}

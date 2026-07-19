"""Multibook M3: ranked candidates from the router, the trading agent's
budget-bounded entry walk, and the validation-stage capacity report."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config.settings as settings
from crypto_ai_system.config import load_config
from crypto_ai_system.execution import paper_book_kernel as books
from crypto_ai_system.pipeline import trading_agent as ta
from crypto_ai_system.strategy_factory.active_strategy_pool import add_champion, empty_pool
from crypto_ai_system.strategy_factory.entry_strategy_router_agent import (
    STATUS_ENTRY_CANDIDATE,
    route_entries,
)
from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec

NOW = "2026-07-19T00:00:00Z"


def _cfg(tmp_path):
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "storage" / "registries")
    cfg.settings.setdefault("storage", {})["latest_dir"] = str(tmp_path / "storage" / "latest")
    return cfg


# --- router: ranked candidates ------------------------------------------------


def _spec(strategy_id, score):
    spec = StrategySpec.from_dict({
        "schema_version": "strategy_spec.v1",
        "strategy_id": strategy_id,
        "strategy_version": "1.0",
        "generation_id": "GEN-001",
        "strategy_family": f"fam_{strategy_id}",
        "status": "GENERATED",
        "symbol_scope": ["BTCUSDT"],
        "timeframe": "1h",
        "direction": "long",
        "entry_rules": {"operator": "AND", "conditions": [
            {"feature": "rsi", "comparison": "<=", "value": 40.0}]},
        "exit_rules": {"stop_model": "atr", "stop_atr": 1.0, "target_atr": 2.0, "max_holding_bars": 24},
        "risk_constraints": {"max_risk_per_trade_R": 1.0},
    }).to_dict()
    return spec, score


def test_router_ranks_all_survivors_head_is_primary():
    pool = empty_pool()
    for sid, score in (("S001", 0.3), ("S002", 0.9), ("S003", 0.6)):
        pool, _ = add_champion(pool, *_spec(sid, score), now=NOW)
    result = route_entries(pool, {"rsi": 25}, now=NOW)
    assert result["status"] == STATUS_ENTRY_CANDIDATE
    ranked = [c["strategy_id"] for c in result["ranked_candidates"]]
    assert ranked == ["S002", "S003", "S001"]
    assert result["primary_strategy_id"] == "S002"


# --- kernel: capacity report --------------------------------------------------


def _open_book(cfg, direction, sid, eid):
    execution = {
        "execution_id": eid,
        "simulated_fill": {"avg_fill_price": 100.0, "filled_quantity": 0.1, "fill_status": "FILLED"},
        "expected_order_intent": {
            "side": "BUY" if direction == "LONG" else "SELL", "direction": direction,
            "entry_price": 100.0, "stop_loss": 98.0 if direction == "LONG" else 102.0,
            "take_profit": 104.0 if direction == "LONG" else 96.0,
            "quantity": 0.1, "strategy_id": sid,
        },
    }
    reconciliation = {"reconciliation_id": f"r_{eid}", "execution_id": eid,
                      "expected_order_intent": execution["expected_order_intent"],
                      "simulated_fill": execution["simulated_fill"]}
    pos, refusal = books.open_in_book(execution, reconciliation, cycle_id="c1", cfg=cfg, enabled=True)
    assert refusal is None, refusal
    return pos


def test_multibook_report_reflects_books_and_caps(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(settings, "MULTIBOOK_MAX_OPEN_BOOKS", 5, raising=False)
    monkeypatch.setattr(settings, "MULTIBOOK_MAX_SAME_DIRECTION", 3, raising=False)
    _open_book(cfg, "LONG", "S271", "e1")
    _open_book(cfg, "SHORT", "S1218", "e2")

    report = books.multibook_report(cfg, enabled=True)
    assert report["open_count"] == 2
    assert report["open_books"] == ["S1218", "S271"]
    assert report["same_direction_counts"] == {"LONG": 1, "SHORT": 1}
    assert report["remaining_capacity"] == 3
    assert report["at_capacity"] is False
    assert books.multibook_report(cfg, enabled=False) is None


# --- trading agent: the entry walk --------------------------------------------


class _Ctx:
    """Just enough PipelineContext for the entry walk."""

    def __init__(self, routing):
        self._d = {"strategy_routing": routing}
        self.cycle = None

    def get(self, key, default=None):
        return self._d.get(key, default)


def _wire_fake_execution(monkeypatch, cfg):
    """Executor/reconciler fakes that fill whatever decision was persisted."""
    state = {"decision": None, "executor_runs": 0}

    def fake_write(path, payload):
        state["decision"] = payload

    def fake_executor(stage):
        state["executor_runs"] += 1
        d = state["decision"] or {}
        intent = {
            "side": "BUY" if d.get("direction", "LONG") == "LONG" else "SELL",
            "direction": d.get("direction", "LONG"),
            "entry_price": 100.0, "stop_loss": 98.0, "take_profit": 104.0,
            "quantity": 0.1, "strategy_id": d.get("strategy_id"),
        }
        return {"filled": True, "order_intent_id": f"oi{state['executor_runs']}",
                "execution_id": f"e{state['executor_runs']}",
                "simulated_fill": {"avg_fill_price": 100.0, "filled_quantity": 0.1,
                                   "fill_status": "FILLED"},
                "expected_order_intent": intent}

    def fake_reconciler():
        return {"reconciliation_id": f"r{state['executor_runs']}",
                "expected_order_intent": (state["decision"] or {}),
                "simulated_fill": {"fill_status": "FILLED"}}

    def fake_builder(routing, *, execution_stage, open_positions, cycle_id, now):
        return {"allow_order_intent": True,
                "strategy_id": routing.get("primary_strategy_id"),
                "direction": routing.get("direction", "LONG")}

    monkeypatch.setattr(ta, "atomic_write_json", fake_write)
    monkeypatch.setattr(ta, "run_order_executor", fake_executor)
    monkeypatch.setattr(ta, "run_reconciler", fake_reconciler)
    import crypto_ai_system.strategy_factory.strategy_execution_bridge as bridge

    monkeypatch.setattr(bridge, "build_strategy_decision_for_cycle", fake_builder)
    monkeypatch.setattr(settings, "STRATEGY_FACTORY_ROUTING_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "STRATEGY_FACTORY_ROUTING_DRIVE_ENABLED", True, raising=False)
    return state


def _routing(*sids):
    return {
        "status": STATUS_ENTRY_CANDIDATE,
        "primary_strategy_id": sids[0],
        "direction": "LONG",
        "ranked_candidates": [
            {"strategy_id": s, "strategy_rule_hash": f"h_{s}", "direction": "LONG",
             "symbol": "BTCUSDT", "champion_score": 1.0 - i * 0.1}
            for i, s in enumerate(sids)
        ],
    }


def test_entry_walk_opens_one_book_per_candidate_up_to_budget(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _wire_fake_execution(monkeypatch, cfg)
    monkeypatch.setattr(settings, "MULTIBOOK_MAX_ENTRIES_PER_CYCLE", 2, raising=False)

    agent = ta.TradingAgent()
    entries, first = agent._run_multibook_entries(
        _Ctx(_routing("S271", "S1699", "S1809")), cfg, "cyc1", "paper",
        {"decision": "research"}, 0,
    )
    # budget 2: the two best candidates entered, the third and research did not
    assert [e["book"] for e in entries] == ["S271", "S1699"]
    assert all(e["filled"] for e in entries)
    assert set(books.open_books(cfg)) == {"S271", "S1699"}
    assert first is not None and first["strategy_id"] == "S271"


def test_entry_walk_skips_open_books_and_fills_research_default(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _wire_fake_execution(monkeypatch, cfg)
    monkeypatch.setattr(settings, "MULTIBOOK_MAX_ENTRIES_PER_CYCLE", 2, raising=False)
    _open_book(cfg, "LONG", "S271", "pre1")  # S271's book already open

    agent = ta.TradingAgent()
    entries, _ = agent._run_multibook_entries(
        _Ctx(_routing("S271", "S1699")), cfg, "cyc1", "paper",
        {"decision": "research"}, 1,
    )
    # S271 filtered (book open) -> S1699 enters, then research takes default
    assert [e["book"] for e in entries] == ["S1699", "default"]
    assert set(books.open_books(cfg)) == {"S271", "S1699", "default"}


def test_entry_walk_without_candidates_runs_research_once(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    state = _wire_fake_execution(monkeypatch, cfg)
    monkeypatch.setattr(settings, "STRATEGY_FACTORY_ROUTING_DRIVE_ENABLED", False, raising=False)

    agent = ta.TradingAgent()
    entries, first = agent._run_multibook_entries(
        _Ctx({"status": "NO_ENTRY"}), cfg, "cyc1", "paper", {"decision": "research"}, 0,
    )
    assert [e["book"] for e in entries] == ["default"]
    assert first is None
    assert state["executor_runs"] == 1

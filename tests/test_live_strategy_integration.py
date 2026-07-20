"""L6: full live-strategy chain integration (no network, nothing submitted).

Proves the whole autonomous path end to end: a routed strategy candidate builds a
live trade decision through the live PreOrderRiskGate (live profile + real live
risk inputs), the approved gate result is PERSISTED as a stage='live' RiskGate
record, the canonical order intent carries the chain, and the L2 final guard
verifies that persisted record and returns READY — while the same chain under
shipped defaults stays fully blocked.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config.settings as settings
from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from crypto_ai_system.research.live_profile import LIVE_PROFILE_ID, LIVE_PROFILE_SHA256
from crypto_ai_system.strategy_factory.active_strategy_pool import add_champion, empty_pool
from crypto_ai_system.strategy_factory.strategy_execution_bridge import build_strategy_decision_for_cycle
from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec

NOW = "2026-07-16T00:00:00Z"
CONFIRM = "I_UNDERSTAND_THIS_TRADES_LIVE_FUNDS_AUTONOMOUSLY"


def _spec_dict(sid="S010"):
    return StrategySpec.from_dict({
        "schema_version": "strategy_spec.v1", "strategy_id": sid, "strategy_version": "1.0",
        "generation_id": "GEN-001", "strategy_family": "trend_pullback", "status": "GENERATED",
        "symbol_scope": ["BTCUSDT"], "timeframe": "1h", "direction": "long",
        "entry_rules": {"operator": "AND", "conditions": [{"feature": "ma20", "comparison": ">", "value_from": "ma50"}]},
        "exit_rules": {"stop_model": "atr", "stop_atr": 1.0, "target_atr": 2.0, "max_holding_bars": 24},
        "risk_constraints": {"max_risk_per_trade_R": 1.0},
    }).to_dict()


def _candidate(primary="S010"):
    return {"status": "ENTRY_CANDIDATE", "direction": "LONG", "order_candidate_count": 1,
            "matched_strategy_ids": [primary], "matched_strategy_count": 1,
            "primary_strategy_id": primary, "primary_strategy_rule_hash": f"hash_{primary}",
            "strategy_pool_version": "active_strategy_pool.v1"}


def _candles(n=60):
    rows, base = [], 60000.0
    for i in range(n):
        base *= 1.002
        c = base * (1.005 if i % 2 == 0 else 0.997)
        rows.append({"timestamp": f"2026-07-10 {i:02d}:00:00+00:00", "open": c * 0.999,
                     "high": c * 1.004, "low": c * 0.996, "close": c, "volume": 1000 + i})
    return rows


def _live_signal():
    return {
        "research_signal_id": "rs_live_1",
        "profile_id": LIVE_PROFILE_ID,
        "profile_sha256": LIVE_PROFILE_SHA256,
        "profile_hash": LIVE_PROFILE_SHA256,
        "trade_permission": {"allow_long": True, "allow_short": True,
                             "allow_new_position": True, "risk_level": "normal"},
    }


def _wire_artifacts(tmp_path, monkeypatch, *, pool, signal):
    files = {
        "ACTIVE_STRATEGY_POOL_PATH": ("pool.json", pool),
        "MARKET_SNAPSHOT_PATH": ("snap.json", {"symbol": "BTCUSDT", "last_close": 65000.0}),
        "RESEARCH_SIGNAL_PATH": ("rs.json", signal),
        "RISK_STATUS_PATH": ("risk.json", {"allow_new_position": True}),
        # The bridge consumes the validation verdicts (QA fix) — wire them to
        # tmp so the test is hermetic instead of leaking real repo storage.
        "DATA_HEALTH_PATH": ("dh.json", {"allow_trading": True}),
        "MARKET_DATA_PATH": ("md.json", {"candles": _candles()}),
    }
    for attr, (name, payload) in files.items():
        p = tmp_path / name
        atomic_write_json(p, payload)
        monkeypatch.setattr(settings, attr, p, raising=False)


@pytest.fixture
def live_env(tmp_path, monkeypatch):
    for name, val in {
        "LIVE_STRATEGY_ORDER_ENABLED": True,
        "LIVE_STRATEGY_PLACE_ORDER_ENABLED": True,
        "LIVE_STRATEGY_MANUAL_KILL_SWITCH": False,
        "LIVE_STRATEGY_CONFIRMATION": CONFIRM,
        "LIVE_STRATEGY_CONFIRMATION_PHRASE": CONFIRM,
        "LIVE_STRATEGY_BASE_URL": "https://fapi.binance.com",
        "LIVE_STRATEGY_API_KEY": "k",
        "LIVE_STRATEGY_API_SECRET": "s",
        "LIVE_STRATEGY_MAX_ORDER_NOTIONAL_USDT": 60.0,
        "LIVE_STRATEGY_ABSOLUTE_MAX_NOTIONAL_USDT": 200.0,
        "LIVE_STRATEGY_MAX_DAILY_ORDER_COUNT": 5,
        "LIVE_STRATEGY_MAX_OPEN_NOTIONAL_USDT": 120.0,
        "LIVE_STRATEGY_DAILY_LOSS_LIMIT_USDT": 20.0,
        # Tmp ledger + counter so real repo state never leaks in.
        "LIVE_OUTCOME_REGISTRY_PATH": tmp_path / "live_outcome_registry.jsonl",
        "LATEST_DIR": tmp_path / "latest",
    }.items():
        monkeypatch.setattr(settings, name, val, raising=False)

    # Promotion evidence: 3 clean canary orders on record.
    import crypto_ai_system.execution.live_promotion as promo
    monkeypatch.setattr(settings, "LIVE_CANARY_ORDER_REGISTRY_PATH",
                        tmp_path / "live_canary_order_registry.jsonl", raising=False)
    for _ in range(3):
        promo.record_canary_order(reconcile_status="RECONCILED")

    # RiskGate registry in a tmp cfg so persisted records land in tmp storage.
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "registries")
    cfg.settings["storage"]["latest_dir"] = str(tmp_path / "latest")
    import crypto_ai_system.registry.risk_gate_registry as rgr
    monkeypatch.setattr(rgr, "load_config", lambda root=".": cfg)
    return cfg


def test_full_live_chain_reaches_ready(tmp_path, monkeypatch, live_env):
    pool, _ = add_champion(empty_pool(), _spec_dict("S010"), 0.7, now=NOW)
    _wire_artifacts(tmp_path, monkeypatch, pool=pool, signal=_live_signal())

    # 1) Routed candidate -> live trade decision through the live gate.
    decision = build_strategy_decision_for_cycle(
        _candidate("S010"), execution_stage="live", cycle_id="cycle_live", now=NOW,
    )
    assert decision is not None
    assert decision["allow_order_intent"] is True, decision.get("block_reasons")
    assert decision["risk_gate_id"]
    assert decision["profile_id"] == LIVE_PROFILE_ID
    # The live notional cap sized the order (not the paper MAX_ORDER_NOTIONAL).
    assert decision["order_notional_usdt"] == 60.0

    # 2) The approved gate result was PERSISTED as a stage='live' record.
    import crypto_ai_system.registry.risk_gate_registry as rgr
    record = rgr.get_risk_gate_record(decision["risk_gate_id"])
    assert record is not None and record["stage"] == "live"

    # 3) Decision -> canonical order intent carrying the chain.
    from crypto_ai_system.execution.order_executor import build_order_intent
    intent = build_order_intent(decision)
    assert intent["status"] == "ORDER_INTENT_CREATED"
    assert intent["execution_stage"] == "live"
    assert intent["risk_gate_id"] == decision["risk_gate_id"]

    # 4) The L2 final guard verifies the persisted record and returns READY.
    from crypto_ai_system.execution.live_order_final_guard import evaluate_live_order_final_guard
    guard = evaluate_live_order_final_guard(intent, current_open_notional_usdt=0.0)
    assert guard["status"] == "READY", guard["blocks"]
    assert guard["risk_gate_verified"] is True


def test_same_chain_fully_blocked_on_defaults(tmp_path, monkeypatch):
    # No live env at all: the decision must refuse order intent and the final
    # guard must block — the autonomous path cannot move under shipped defaults.
    pool, _ = add_champion(empty_pool(), _spec_dict("S010"), 0.7, now=NOW)
    _wire_artifacts(tmp_path, monkeypatch, pool=pool, signal=_live_signal())

    decision = build_strategy_decision_for_cycle(
        _candidate("S010"), execution_stage="live", cycle_id="cycle_live", now=NOW,
    )
    assert decision is not None
    assert decision["allow_order_intent"] is False

    from crypto_ai_system.execution.live_order_final_guard import evaluate_live_order_final_guard
    guard = evaluate_live_order_final_guard({
        "status": "ORDER_INTENT_CREATED", "symbol": "BTCUSDT", "quantity": 0.001,
        "order_notional_usdt": 60.0, "risk_gate_id": "rg_x", "profile_id": LIVE_PROFILE_ID,
    })
    assert guard["approved"] is False

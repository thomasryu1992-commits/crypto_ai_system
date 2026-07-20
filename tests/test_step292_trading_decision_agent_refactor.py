from __future__ import annotations

import json
from pathlib import Path

from bridge.research_trading_bridge import decide_trade_action
from crypto_ai_system.execution.order_executor import build_order_intent
from crypto_ai_system.trading.trading_decision_agent import (
    ORDER_INTENT_BLOCKED_UNTIL_PRE_ORDER_RISK_GATE,
    TRADING_DECISION_AGENT_VERSION,
    build_trading_decision,
)


def _research() -> dict:
    return {
        "decision_id": "decision_step292",
        "research_signal_id": "signal_step292",
        "profile_id": "profile_step292",
        "data_snapshot_id": "data_snapshot_step292",
        "feature_snapshot_id": "feature_snapshot_step292",
        "scenario": "Constructive",
        "signal_timing": "Early",
        "allow_long": True,
        "allow_short": False,
        "research_bias": "ALLOW_LONG_BIAS",
    }


def _trading() -> dict:
    return {
        "trading_signal": {
            "signal": "LONG",
            "confidence": 80,
            "allow_long": True,
            "allow_short": False,
            "allow_new_position": True,
            "risk_level": "normal",
            "permission_result": "allow_long",
        }
    }


def _health() -> dict:
    return {"allow_trading": True, "is_synthetic": False, "is_fallback": False}


def _risk() -> dict:
    return {"allow_new_position": True, "status": "NORMAL"}


def _market() -> dict:
    return {"symbol": "BTCUSDT", "last_close": 100.0, "atr": 2.0}


def _signal() -> dict:
    return {
        "research_signal_id": "signal_step292",
        "profile_id": "profile_step292",
        "data_snapshot_id": "data_snapshot_step292",
        "feature_snapshot_id": "feature_snapshot_step292",
        "feature_matrix_sha256": "f" * 64,
        "source_bundle_sha256": "b" * 64,
        "permission_result": "allow_long",
        "trade_permission": {"allow_long": True, "allow_short": False, "allow_new_position": True, "risk_level": "normal"},
        "entry_side": "LONG",
        "entry_allowed": True,
    }


def test_step292_trading_decision_separates_price_structure_permission_and_order_intent() -> None:
    decision = build_trading_decision(
        research=_research(),
        trading=_trading(),
        data_health=_health(),
        risk=_risk(),
        market_snapshot=_market(),
        research_signal=_signal(),
    )

    assert decision["trading_decision_agent_version"] == TRADING_DECISION_AGENT_VERSION
    assert decision["final_decision"] == "REVIEW_ONLY_LONG_CANDIDATE"
    assert decision["direction"] == "LONG"
    assert decision["price_structure"]["entry"] == 100.0
    assert decision["price_structure"]["stop_loss"] == 98.0
    assert decision["price_structure"]["take_profit"] == 104.0
    assert decision["price_structure"]["risk_reward"] == 2.0
    assert decision["research_permission"]["allow_long"] is True
    assert decision["allow_new_position"] is True
    assert decision["allow_order_intent"] is False
    assert decision["pre_order_risk_gate_required"] is True
    assert decision["pre_order_risk_gate_approved"] is False
    assert decision["order_intent_created"] is False
    assert decision["order_intent_block_reason"] == ORDER_INTENT_BLOCKED_UNTIL_PRE_ORDER_RISK_GATE
    assert decision["trade_approved"] is False
    assert decision["external_order_submission_performed"] is False


def test_step292_bridge_legacy_decide_trade_action_never_unlocks_order_intent_without_risk_gate() -> None:
    decision = decide_trade_action(
        _research(),
        _trading(),
        _health(),
        _risk(),
        market_snapshot=_market(),
        research_signal=_signal(),
    )

    assert decision["final_decision"] == "REVIEW_ONLY_LONG_CANDIDATE"
    assert decision["allow_order_intent"] is False
    assert decision["pre_order_risk_gate_required"] is True
    assert decision["order_intent_created"] is False


def test_step292_data_health_block_preserves_legacy_block_status_and_review_only_boundary() -> None:
    decision = decide_trade_action(
        _research(),
        _trading(),
        {"allow_trading": False, "is_synthetic": True, "is_fallback": True, "problems": ["synthetic_data_source_blocks_trading"]},
        _risk(),
        market_snapshot=_market(),
        research_signal=_signal(),
    )

    assert decision["final_decision"] == "BLOCK_DATA_HEALTH"
    assert decision["allow_order_intent"] is False
    assert decision["pre_order_risk_gate_required"] is True
    assert decision["trade_approved"] is False


def test_step292_order_executor_blocks_legacy_allow_order_intent_without_pre_order_risk_gate() -> None:
    intent = build_order_intent({
        "allow_order_intent": True,
        "direction": "LONG",
        "final_decision": "LEGACY_ALLOW",
        "pre_order_risk_gate_approved": False,
    })

    assert intent["status"] == "NO_ORDER_INTENT"
    assert intent["state"] == "REJECTED"
    assert intent["order_intent_created"] is False
    assert intent["order_intent_block_reason"] == ORDER_INTENT_BLOCKED_UNTIL_PRE_ORDER_RISK_GATE


def test_step292_run_bridge_writes_decision_pipeline_record(tmp_path: Path, monkeypatch) -> None:
    import bridge.research_trading_bridge as bridge

    research_path = tmp_path / "research_decision.json"
    trading_path = tmp_path / "trading_cycle.json"
    health_path = tmp_path / "data_health.json"
    risk_path = tmp_path / "risk.json"
    market_path = tmp_path / "market_snapshot.json"
    signal_path = tmp_path / "research_signal.json"
    trade_decision_path = tmp_path / "trade_decision.json"
    registry_dir = tmp_path / "storage" / "registries"

    research_path.write_text(json.dumps(_research()), encoding="utf-8")
    trading_path.write_text(json.dumps(_trading()), encoding="utf-8")
    health_path.write_text(json.dumps(_health()), encoding="utf-8")
    risk_path.write_text(json.dumps(_risk()), encoding="utf-8")
    market_path.write_text(json.dumps(_market()), encoding="utf-8")
    signal_path.write_text(json.dumps(_signal()), encoding="utf-8")

    from crypto_ai_system.config import AppConfig

    monkeypatch.setattr(bridge, "load_config", lambda _root: AppConfig(root=tmp_path, settings={"storage": {"registry_dir": "storage/registries"}}))
    monkeypatch.setattr(bridge, "RESEARCH_DECISION_PATH", research_path)
    monkeypatch.setattr(bridge, "TRADING_CYCLE_PATH", trading_path)
    monkeypatch.setattr(bridge, "MARKET_SNAPSHOT_PATH", market_path)
    monkeypatch.setattr(bridge, "RESEARCH_SIGNAL_PATH", signal_path)
    monkeypatch.setattr(bridge, "TRADE_DECISION_PATH", trade_decision_path)

    # P2: the validation verdicts are required inputs, not file re-reads.
    result = bridge.run_research_trading_bridge(data_health=_health(), risk=_risk())
    registry_path = registry_dir / "decision_pipeline_registry.jsonl"
    rows = [json.loads(line) for line in registry_path.read_text(encoding="utf-8").splitlines()]

    assert result["final_decision"] == "REVIEW_ONLY_LONG_CANDIDATE"
    assert result["allow_order_intent"] is False
    assert result["decision_pipeline_registry_record_id"]
    assert rows[-1]["allow_order_intent"] is False
    assert rows[-1]["order_intent_created"] is False

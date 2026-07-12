from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.order_executor import build_order_intent, execute_order_intent
from crypto_ai_system.execution.paper_execution_engine_v2 import (
    PAPER_EXECUTION_ENGINE_VERSION,
    STATUS_PAPER_PENDING_RECONCILIATION,
    build_paper_execution_registry_record,
    execute_and_persist_paper_order,
    simulate_paper_execution,
    validate_paper_order_intent,
)
from crypto_ai_system.registry.base_registry import registry_path


def _cfg(tmp_path: Path):
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "storage" / "registries")
    cfg.settings.setdefault("storage", {})["latest_dir"] = str(tmp_path / "storage" / "latest")
    return cfg


def _intent(**overrides):
    payload = {
        "status": "ORDER_INTENT_CREATED",
        "state": "CREATED",
        "decision_stage": "paper",
        "execution_stage": "paper",
        "order_intent_created": True,
        "order_intent_id": "order_intent_step294",
        "decision_id": "decision_step294",
        "risk_gate_id": "risk_gate_step294",
        "research_signal_id": "signal_step294",
        "profile_id": "profile_step294",
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "side": "BUY",
        "entry_price": 100.0,
        "quantity": 0.1,
        "order_notional_usdt": 10.0,
        "adapter_called": False,
        "live_order_executed": False,
        "external_order_submission_performed": False,
    }
    payload.update(overrides)
    return payload


def _risk_gate(**overrides):
    payload = {
        "approved": True,
        "status": "PASS_PAPER",
        "risk_gate_id": "risk_gate_step294",
        "decision_id": "decision_step294",
        "research_signal_id": "signal_step294",
        "profile_id": "profile_step294",
    }
    payload.update(overrides)
    return payload


def test_step294_validates_paper_order_intent_and_blocks_missing_chain() -> None:
    valid, blockers = validate_paper_order_intent(_intent(), _risk_gate())
    invalid, invalid_blockers = validate_paper_order_intent(_intent(risk_gate_id=""), _risk_gate())

    assert valid is True
    assert blockers == []
    assert invalid is False
    assert "RISK_GATE_ID_MISSING" in invalid_blockers


def test_step294_simulates_full_fill_lifecycle_without_external_side_effects() -> None:
    record = simulate_paper_execution(_intent(), risk_gate_report=_risk_gate(), execution_config={"fee_bps": 4.0, "slippage_bps": 2.0}).to_dict()

    assert record["paper_execution_engine_version"] == PAPER_EXECUTION_ENGINE_VERSION
    assert record["status"] == STATUS_PAPER_PENDING_RECONCILIATION
    assert record["state"] == "PENDING_RECONCILIATION"
    assert record["execution_id"].startswith("execution_")
    assert record["lifecycle_states"] == ["ORDER_INTENT_CREATED", "PAPER_SUBMITTED", "PAPER_ACCEPTED", "PAPER_FILLED", "PENDING_RECONCILIATION"]
    assert record["simulated_fill"]["fill_status"] == "FILLED"
    assert record["simulated_fill"]["filled_quantity"] == 0.1
    assert record["fee_model"]["fee_model_used"] is True
    assert record["slippage_model"]["slippage_model_used"] is True
    assert record["position_delta"]["position_opened"] is True
    assert record["pending_reconciliation"] is True
    assert record["reconciliation_required"] is True
    assert record["adapter_called"] is False
    assert record["live_order_executed"] is False
    assert record["external_order_submission_performed"] is False
    assert record["runtime_settings_mutated"] is False
    assert record["score_weights_mutated"] is False
    assert record["paper_execution_record_sha256"]


def test_step294_partial_fill_and_cancel_paths_are_explicit() -> None:
    partial = simulate_paper_execution(_intent(), risk_gate_report=_risk_gate(), execution_config={"fill_ratio": 0.5}).to_dict()
    cancelled = simulate_paper_execution(_intent(), risk_gate_report=_risk_gate(), execution_config={"cancel_before_fill": True}).to_dict()

    assert "PAPER_PARTIALLY_FILLED" in partial["lifecycle_states"]
    assert partial["simulated_fill"]["fill_status"] == "PARTIALLY_FILLED"
    assert partial["simulated_fill"]["filled_quantity"] == 0.05
    assert cancelled["status"] == "PAPER_CANCELLED"
    assert cancelled["simulated_fill"]["fill_status"] == "NO_FILL"
    assert cancelled["position_delta"]["position_opened"] is False


def test_step294_rejected_intent_never_submits_paper_order() -> None:
    record = simulate_paper_execution(_intent(status="NO_ORDER_INTENT", order_intent_created=False), risk_gate_report=_risk_gate()).to_dict()

    assert record["status"] == "PAPER_REJECTED"
    assert record["paper_order_submitted"] is False
    assert "ORDER_INTENT_NOT_CREATED" in record["execution_blockers"]
    assert record["simulated_fill"]["fill_status"] == "NO_FILL"


def test_step294_persists_latest_record_events_and_append_only_registry(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    record = execute_and_persist_paper_order(_intent(), risk_gate_report=_risk_gate(), cfg=cfg)
    registry = registry_path(cfg, "paper_execution_registry")
    rows = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines()]

    assert (tmp_path / "storage" / "latest" / "paper_execution_record.json").exists()
    assert (tmp_path / "storage" / "latest" / "paper_execution_lifecycle_events.json").exists()
    assert (tmp_path / "storage" / "latest" / "paper_execution_registry_record.json").exists()
    assert len(rows) == 1
    assert rows[0]["registry_name"] == "paper_execution_registry"
    assert rows[0]["execution_chain_complete"] is True
    assert rows[0]["external_order_submission_performed"] is False
    assert record["paper_execution_registry_record_id"] == rows[0]["paper_execution_registry_record_id"]


def test_step294_registry_record_marks_missing_execution_chain_fields() -> None:
    record = simulate_paper_execution(_intent(decision_id=""), risk_gate_report=_risk_gate()).to_dict()
    registry_record = build_paper_execution_registry_record(record)

    assert registry_record["execution_chain_complete"] is False
    assert "decision_id" in registry_record["missing_execution_chain_fields"]


def test_step294_order_executor_routes_approved_paper_intent_to_paper_engine(tmp_path: Path, monkeypatch) -> None:
    import crypto_ai_system.execution.paper_execution_engine_v2 as paper_engine

    cfg = _cfg(tmp_path)
    monkeypatch.setattr(paper_engine, "load_config", lambda _root: cfg)
    trade_decision = {
        "allow_order_intent": True,
        "pre_order_risk_gate_approved": True,
        "risk_gate_id": "risk_gate_step294",
        "risk_gate_report": _risk_gate(),
        "decision_stage": "paper",
        "execution_stage": "paper",
        "decision_id": "decision_step294",
        "research_signal_id": "signal_step294",
        "profile_id": "profile_step294",
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "entry": 100.0,
        "quantity": 0.1,
        "order_notional_usdt": 10.0,
        "final_decision": "REVIEW_ONLY_LONG_CANDIDATE",
    }
    intent = build_order_intent(trade_decision)
    result = execute_order_intent(intent)

    assert intent["status"] == "ORDER_INTENT_CREATED"
    assert intent["order_intent_id"].startswith("order_intent_") or intent["order_intent_id"] == "order_intent_step294"
    assert result["mode"] == "PAPER_EXECUTION_ENGINE_V2"
    assert result["status"] == STATUS_PAPER_PENDING_RECONCILIATION
    assert result["filled"] is True
    assert result["exchange_order_id"] is None
    assert result["external_order_submission_performed"] is False

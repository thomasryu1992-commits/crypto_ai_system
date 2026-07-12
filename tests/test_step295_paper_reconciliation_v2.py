from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.paper_execution_engine_v2 import simulate_paper_execution, execute_and_persist_paper_order
from crypto_ai_system.execution.paper_reconciliation_v2 import (
    PAPER_RECONCILIATION_VERSION,
    PROMOTION_BLOCKER_MISMATCH,
    PROMOTION_BLOCKER_NONE,
    STATUS_RECONCILED,
    STATUS_RECONCILIATION_BLOCKED_NO_EXECUTION,
    STATUS_RECONCILIATION_MISMATCH,
    STATUS_UNSAFE_LIVE_SIDE_EFFECT,
    build_paper_reconciliation_registry_record,
    reconcile_and_persist_paper_execution,
    reconcile_latest_paper_execution,
    reconcile_paper_execution_record,
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
        "order_intent_id": "order_intent_step295",
        "decision_id": "decision_step295",
        "risk_gate_id": "risk_gate_step295",
        "research_signal_id": "signal_step295",
        "profile_id": "profile_step295",
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
        "risk_gate_id": "risk_gate_step295",
        "decision_id": "decision_step295",
        "research_signal_id": "signal_step295",
        "profile_id": "profile_step295",
    }
    payload.update(overrides)
    return payload


def _paper_record(**intent_overrides):
    return simulate_paper_execution(
        _intent(**intent_overrides),
        risk_gate_report=_risk_gate(),
        execution_config={"fee_bps": 4.0, "slippage_bps": 2.0},
    ).to_dict()


def test_step295_reconciles_matching_paper_execution_evidence() -> None:
    result = reconcile_paper_execution_record(_paper_record())

    assert result["paper_reconciliation_version"] == PAPER_RECONCILIATION_VERSION
    assert result["status"] == STATUS_RECONCILED
    assert result["reconciled"] is True
    assert result["reconciliation_mismatch"] is False
    assert result["mismatch_reasons"] == []
    assert result["promotion_blocked"] is False
    assert result["promotion_blocker"] == PROMOTION_BLOCKER_NONE
    assert result["reconciliation_id"].startswith("reconciliation_")
    assert result["reconciliation_evidence_hash"]
    assert result["live_position_sync_enabled_by_this_module"] is False
    assert result["external_execution_sync_performed"] is False
    assert result["external_order_submission_performed"] is False
    assert result["runtime_settings_mutated"] is False
    assert result["score_weights_mutated"] is False


def test_step295_detects_order_intent_id_mismatch_and_blocks_promotion() -> None:
    record = _paper_record()
    record["simulated_fill"]["order_intent_id"] = "wrong_order_intent"
    result = reconcile_paper_execution_record(record)

    assert result["status"] == STATUS_RECONCILIATION_MISMATCH
    assert result["reconciliation_mismatch"] is True
    assert "ORDER_INTENT_ID_MATCH" in result["mismatch_reasons"]
    assert result["promotion_blocked"] is True
    assert result["promotion_blocker"] == PROMOTION_BLOCKER_MISMATCH


def test_step295_detects_position_delta_mismatch() -> None:
    record = _paper_record()
    record["position_delta"]["quantity_delta"] = 0.2
    result = reconcile_paper_execution_record(record)

    assert result["status"] == STATUS_RECONCILIATION_MISMATCH
    assert "POSITION_DELTA_MATCHES_FILL" in result["mismatch_reasons"]
    assert result["promotion_blocked"] is True


def test_step295_blocks_unsafe_live_side_effect_flags() -> None:
    record = _paper_record()
    record["simulated_execution"]["adapter_called"] = True
    result = reconcile_paper_execution_record(record)

    assert result["status"] == STATUS_UNSAFE_LIVE_SIDE_EFFECT
    assert "NO_LIVE_SIDE_EFFECTS" in result["mismatch_reasons"]
    assert result["promotion_blocked"] is True


def test_step295_missing_paper_execution_evidence_fails_closed() -> None:
    result = reconcile_paper_execution_record({})

    assert result["status"] == STATUS_RECONCILIATION_BLOCKED_NO_EXECUTION
    assert result["reconciled"] is False
    assert result["promotion_blocked"] is True
    assert "PAPER_EXECUTION_RECORD_EXISTS" in result["mismatch_reasons"]


def test_step295_persists_latest_reconciliation_and_append_only_registry(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    result = reconcile_and_persist_paper_execution(_paper_record(), cfg=cfg)
    registry = registry_path(cfg, "paper_reconciliation_registry")
    rows = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines()]

    assert (tmp_path / "storage" / "latest" / "paper_reconciliation_record.json").exists()
    assert (tmp_path / "storage" / "latest" / "paper_reconciliation_registry_record.json").exists()
    assert len(rows) == 1
    assert rows[0]["registry_name"] == "paper_reconciliation_registry"
    assert rows[0]["reconciliation_chain_complete"] is True
    assert rows[0]["status"] == STATUS_RECONCILED
    assert result["paper_reconciliation_registry_record_id"] == rows[0]["paper_reconciliation_registry_record_id"]


def test_step295_registry_record_marks_missing_chain_fields() -> None:
    result = reconcile_paper_execution_record(_paper_record(decision_id=""))
    registry_record = build_paper_reconciliation_registry_record(result)

    assert registry_record["reconciliation_chain_complete"] is False
    assert "decision_id" in registry_record["missing_reconciliation_chain_fields"]


def test_step295_reconcile_latest_consumes_step294_latest_record(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    execute_and_persist_paper_order(_intent(), risk_gate_report=_risk_gate(), cfg=cfg)
    result = reconcile_latest_paper_execution(cfg=cfg)

    assert result["status"] == STATUS_RECONCILED
    assert (tmp_path / "storage" / "latest" / "paper_reconciliation_record.json").exists()
    assert (tmp_path / "storage" / "registries" / "paper_reconciliation_registry.jsonl").exists()

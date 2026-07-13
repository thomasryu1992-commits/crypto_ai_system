from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.paper_execution_engine_v2 import simulate_paper_execution, execute_and_persist_paper_order
from crypto_ai_system.execution.paper_reconciliation_v2 import reconcile_and_persist_paper_execution, reconcile_paper_execution_record
from crypto_ai_system.feedback.outcome_analytics_v2 import (
    NEXT_EXPAND_TEST_COVERAGE,
    NEXT_REPEAT_IN_PAPER,
    OUTCOME_ANALYTICS_VERSION,
    STATUS_OUTCOME_BLOCKED_RECONCILIATION_EVIDENCE_MISSING,
    STATUS_OUTCOME_BLOCKED_RECONCILIATION_MISMATCH,
    STATUS_OUTCOME_RECORDED,
    STATUS_OUTCOME_REVIEW_ONLY_OPEN_POSITION,
    analyze_and_persist_paper_outcome,
    analyze_paper_reconciliation_outcome,
    build_outcome_feedback_registry_record,
    run_outcome_analytics_latest,
    summarize_outcomes,
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
        "order_intent_id": "order_intent_step296",
        "decision_id": "decision_step296",
        "risk_gate_id": "risk_gate_step296",
        "research_signal_id": "signal_step296",
        "profile_id": "profile_step296",
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "side": "BUY",
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "take_profit": 115.0,
        "quantity": 0.1,
        "order_notional_usdt": 10.0,
        "permission_result": "allow_long",
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
        "risk_gate_id": "risk_gate_step296",
        "decision_id": "decision_step296",
        "research_signal_id": "signal_step296",
        "profile_id": "profile_step296",
    }
    payload.update(overrides)
    return payload


def _reconciliation(**intent_overrides):
    record = simulate_paper_execution(
        _intent(**intent_overrides),
        risk_gate_report=_risk_gate(),
        execution_config={"fee_bps": 4.0, "slippage_bps": 2.0, "fill_latency_ms": 123.0},
    ).to_dict()
    return reconcile_paper_execution_record(record)


def test_step296_records_closed_outcome_metrics_beyond_pnl() -> None:
    rec = _reconciliation()
    outcome = analyze_paper_reconciliation_outcome(
        rec,
        outcome_context={"exit_price": 110.0, "regime": "trend", "stale_data_rate": 0.1, "api_error_rate": 0.02},
    )

    assert outcome["outcome_analytics_version"] == OUTCOME_ANALYTICS_VERSION
    assert outcome["status"] == STATUS_OUTCOME_RECORDED
    assert outcome["outcome_closed"] is True
    assert outcome["result_R"] == 2.0
    assert outcome["pnl"] == 1.0
    assert outcome["expectancy"] == 2.0
    assert outcome["win_loss"] == "win"
    assert outcome["average_R"] == 2.0
    assert outcome["max_drawdown"] == 0.0
    assert outcome["slippage"] == 2.0
    assert outcome["latency_ms"] == 123.0
    assert outcome["stale_data_rate"] == 0.1
    assert outcome["api_error_rate"] == 0.02
    assert outcome["manual_override_count"] == 0
    assert outcome["paper_live_gap"] == "not_applicable"
    assert outcome["outcome_record_sha256"]
    assert outcome["live_trading_allowed_by_this_module"] is False
    assert outcome["runtime_settings_mutated"] is False
    assert outcome["score_weights_mutated"] is False
    assert outcome["auto_promotion_allowed"] is False


def test_step296_open_reconciled_position_is_review_only_repeat_in_paper() -> None:
    outcome = analyze_paper_reconciliation_outcome(_reconciliation())

    assert outcome["status"] == STATUS_OUTCOME_REVIEW_ONLY_OPEN_POSITION
    assert outcome["outcome_closed"] is False
    assert outcome["result_R"] == 0.0
    assert outcome["next_action"] == NEXT_REPEAT_IN_PAPER
    assert "OUTCOME_NOT_CLOSED" in outcome["outcome_quality_warnings"]


def test_step296_blocks_reconciliation_mismatch_and_keeps_metrics_neutral() -> None:
    rec = _reconciliation()
    rec["reconciled"] = False
    rec["reconciliation_mismatch"] = True
    rec["mismatch_reasons"] = ["ORDER_INTENT_ID_MATCH"]
    outcome = analyze_paper_reconciliation_outcome(rec, outcome_context={"exit_price": 110.0})

    assert outcome["status"] == STATUS_OUTCOME_BLOCKED_RECONCILIATION_MISMATCH
    assert outcome["outcome_closed"] is False
    assert outcome["result_R"] == 0.0
    assert outcome["pnl"] == 0.0
    assert outcome["next_action"] == NEXT_EXPAND_TEST_COVERAGE
    assert "RECONCILIATION_NOT_RECONCILED" in outcome["outcome_quality_warnings"]


def test_step296_missing_reconciliation_evidence_fails_closed() -> None:
    outcome = analyze_paper_reconciliation_outcome({})

    assert outcome["status"] == STATUS_OUTCOME_BLOCKED_RECONCILIATION_EVIDENCE_MISSING
    assert outcome["next_action"] == NEXT_EXPAND_TEST_COVERAGE
    assert "RECONCILIATION_EVIDENCE_MISSING" in outcome["outcome_quality_warnings"]


def test_step296_registry_record_preserves_full_outcome_chain() -> None:
    outcome = analyze_paper_reconciliation_outcome(_reconciliation(), outcome_context={"result_R": -0.5, "pnl": -0.25})
    registry_record = build_outcome_feedback_registry_record(outcome)

    assert registry_record["outcome_chain_complete"] is True
    assert registry_record["missing_outcome_chain_fields"] == []
    assert registry_record["outcome_id"].startswith("out_")
    assert registry_record["feedback_cycle_id"].startswith("fbc_")
    assert registry_record["outcome_feedback_registry_record_sha256"]


def test_step296_persists_latest_outcome_and_append_only_registry(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    result = analyze_and_persist_paper_outcome(_reconciliation(), outcome_context={"result_R": 1.25}, cfg=cfg)
    registry = registry_path(cfg, "outcome_feedback_registry")
    rows = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines()]

    assert (tmp_path / "storage" / "latest" / "outcome_analytics_record.json").exists()
    assert (tmp_path / "storage" / "latest" / "outcome_feedback_registry_record.json").exists()
    assert len(rows) == 1
    assert rows[0]["registry_name"] == "outcome_feedback_registry"
    assert rows[0]["status"] == STATUS_OUTCOME_RECORDED
    assert result["outcome_feedback_registry_record_id"] == rows[0]["outcome_feedback_registry_record_id"]


def test_step296_run_latest_consumes_step295_reconciliation_record(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    paper = execute_and_persist_paper_order(_intent(), risk_gate_report=_risk_gate(), cfg=cfg)
    reconciliation = reconcile_and_persist_paper_execution(paper, cfg=cfg)
    result = run_outcome_analytics_latest(cfg=cfg, outcome_context={"exit_price": 110.0})

    assert reconciliation["status"] == "RECONCILED"
    assert result["status"] == STATUS_OUTCOME_RECORDED
    assert (tmp_path / "storage" / "latest" / "outcome_analytics_record.json").exists()
    assert (tmp_path / "storage" / "registries" / "outcome_feedback_registry.jsonl").exists()


def test_step296_summarizes_multiple_outcomes() -> None:
    rows = [
        analyze_paper_reconciliation_outcome(_reconciliation(), outcome_context={"result_R": 1.0}),
        analyze_paper_reconciliation_outcome(_reconciliation(order_intent_id="order_intent_step296_b"), outcome_context={"result_R": -0.5}),
        analyze_paper_reconciliation_outcome(_reconciliation(order_intent_id="order_intent_step296_c"), outcome_context={"result_R": 0.0}),
    ]
    summary = summarize_outcomes(rows)

    assert summary["outcome_count"] == 3
    assert summary["closed_count"] == 3
    assert summary["win_count"] == 1
    assert summary["loss_count"] == 1
    assert summary["breakeven_count"] == 1
    assert summary["expectancy"] == 0.16666667
    assert summary["max_drawdown"] == 0.5

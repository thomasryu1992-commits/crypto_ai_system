from __future__ import annotations

from crypto_ai_system.execution.paper_execution_dry_run_bridge import (
    STEP211_VALIDATION_OK,
    execute_paper_execution_dry_run_bridge,
    validate_paper_execution_dry_run_bridge,
)
from crypto_ai_system.execution.simulated_paper_order_lifecycle import (
    STEP212_VALIDATION_OK,
    execute_simulated_paper_order_lifecycle,
    validate_simulated_paper_order_lifecycle,
)
from crypto_ai_system.feedback.paper_lifecycle_outcome_store import (
    STEP213_VALIDATION_OK,
    execute_paper_lifecycle_outcome_store,
    validate_paper_lifecycle_outcome_store,
)
from crypto_ai_system.trading.order_id_chain import ORDER_ID_CHAIN_VERSION, chain_complete
from crypto_ai_system.trading.pre_order_risk_gate import evaluate_pre_order_risk_gate


def test_step271_order_intents_have_canonical_upstream_id_chain(isolated_project_root):
    result = execute_paper_execution_dry_run_bridge(isolated_project_root, write_output=True)
    assert result.dry_run_intent_count > 0
    intent = result.sample_dry_run_order_intents[0]

    assert intent["order_id_chain_version"] == ORDER_ID_CHAIN_VERSION
    assert intent["research_signal_id"]
    assert intent["decision_id"].startswith("decision_")
    assert intent["risk_gate_id"].startswith("risk_gate_")
    assert intent["order_intent_id"].startswith("order_intent_")
    assert chain_complete(intent, through="order_intent") is True

    validation = validate_paper_execution_dry_run_bridge(isolated_project_root)
    assert validation.status == STEP211_VALIDATION_OK
    assert validation.canonical_order_id_chain_complete is True


def test_step271_lifecycle_carries_execution_and_reconciliation_chain(isolated_project_root):
    result = execute_simulated_paper_order_lifecycle(isolated_project_root, write_output=True)
    assert result.lifecycle_summary_count > 0
    summary = result.summaries[0]

    assert summary["order_id_chain_version"] == ORDER_ID_CHAIN_VERSION
    assert summary["order_intent_id"].startswith("order_intent_")
    assert summary["execution_id"].startswith("execution_")
    assert summary["reconciliation_id"].startswith("rec_")
    assert chain_complete(summary, through="reconciliation") is True

    event = result.sample_lifecycle_events[0]
    assert event["execution_id"] == summary["execution_id"]
    assert event["reconciliation_id"] == summary["reconciliation_id"]

    validation = validate_simulated_paper_order_lifecycle(isolated_project_root)
    assert validation.status == STEP212_VALIDATION_OK
    assert validation.canonical_order_id_chain_complete is True


def test_step271_outcome_completes_full_feedback_chain(isolated_project_root):
    result = execute_paper_lifecycle_outcome_store(
        isolated_project_root,
        write_output=True,
        allow_source_regeneration=True,
    )
    assert result.outcome_record_count > 0
    record = result.sample_outcome_records[0]

    assert record["order_id_chain_version"] == ORDER_ID_CHAIN_VERSION
    assert record["research_signal_id"]
    assert record["decision_id"].startswith("decision_")
    assert record["risk_gate_id"].startswith("risk_gate_")
    assert record["order_intent_id"].startswith("order_intent_")
    assert record["execution_id"].startswith("execution_")
    assert record["reconciliation_id"].startswith("rec_")
    assert record["outcome_id"].startswith("out_")
    assert record["feedback_cycle_id"].startswith("fbc_")
    assert record["order_id_chain_complete"] is True
    assert record["missing_order_id_chain_fields"] == []
    assert chain_complete(record, through="outcome") is True

    validation = validate_paper_lifecycle_outcome_store(isolated_project_root)
    assert validation.status == STEP213_VALIDATION_OK
    assert validation.canonical_order_id_chain_complete is True


def test_step271_pre_order_risk_gate_blocks_missing_canonical_ids():
    result = evaluate_pre_order_risk_gate(
        decision={"side": "LONG"},
        research_signal={
            "trade_permission": {"allow_long": True, "allow_short": False, "allow_new_position": True, "risk_level": "normal"},
        },
        profile={"approved": True},
        runtime_state={"open_positions": 0, "daily_pnl_r": 0, "consecutive_losses": 0, "api_error_rate": 0, "manual_kill_switch": False},
        market_state={"spread_bps": 1, "slippage_bps": 1},
    )

    assert result.approved is False
    assert result.risk_level == "blocked"
    assert "CHAIN_DECISION_ID_MISSING_BLOCKED" in result.block_reasons
    assert "CHAIN_RESEARCH_SIGNAL_ID_MISSING_BLOCKED" in result.block_reasons
    assert "CHAIN_PROFILE_ID_MISSING_BLOCKED" in result.block_reasons

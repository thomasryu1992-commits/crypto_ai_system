from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.execution.simulated_paper_order_lifecycle import (
    STEP212_RECONCILIATION_EVIDENCE_VERSION,
    STEP212_VALIDATION_OK,
    execute_simulated_paper_order_lifecycle,
    validate_simulated_paper_order_lifecycle,
)
from crypto_ai_system.feedback.paper_lifecycle_outcome_store import (
    STEP213_RECONCILIATION_EVIDENCE_VERSION,
    STEP213_VALIDATION_OK,
    execute_paper_lifecycle_outcome_store,
    validate_paper_lifecycle_outcome_store,
)


def test_step272_lifecycle_summary_contains_reconciliation_evidence(isolated_project_root):
    result = execute_simulated_paper_order_lifecycle(isolated_project_root, write_output=True)
    assert result.lifecycle_summary_count > 0
    summary = result.summaries[0]

    assert summary["reconciliation_evidence_version"] == STEP212_RECONCILIATION_EVIDENCE_VERSION
    assert summary["reconciliation_status"] == "RECONCILIATION_MATCHED"
    assert summary["reconciliation_mismatch"] is False
    assert summary["mismatch_reasons"] == []
    assert summary["reconciliation_evidence_hash"]

    expected = summary["expected_order_intent"]
    fill = summary["simulated_fill"]
    position_delta = summary["position_delta"]
    fee_model = summary["fee_model"]
    slippage_model = summary["slippage_model"]

    assert expected["order_intent_id"] == summary["order_intent_id"]
    assert expected["quantity"] == summary["quantity"]
    assert fill["fill_status"] == "FILLED"
    assert fill["fill_quantity"] == summary["quantity"]
    assert fill["fill_price"] == summary["entry_price"]
    assert position_delta["position_opened"] is True
    assert position_delta["position_closed_by_simulation"] is True
    assert fee_model["fee_bps"] >= 0
    assert fee_model["fee_usd"] >= 0
    assert slippage_model["within_tolerance"] is True
    assert summary["slippage_bps"] == slippage_model["actual_slippage_bps"]
    assert summary["fee_usd"] == fee_model["fee_usd"]

    validation = validate_simulated_paper_order_lifecycle(isolated_project_root)
    assert validation.status == STEP212_VALIDATION_OK
    assert validation.reconciliation_evidence_complete is True
    assert validation.reconciliation_evidence_hash_valid is True
    assert validation.no_reconciliation_mismatch is True


def test_step272_outcome_store_carries_reconciliation_evidence(isolated_project_root):
    result = execute_paper_lifecycle_outcome_store(
        isolated_project_root,
        write_output=True,
        allow_source_regeneration=True,
    )
    assert result.outcome_record_count > 0
    record = result.sample_outcome_records[0]

    assert record["reconciliation_evidence_version"] == STEP213_RECONCILIATION_EVIDENCE_VERSION
    assert record["reconciliation_status"] == "RECONCILIATION_MATCHED"
    assert record["reconciliation_evidence_complete"] is True
    assert record["reconciliation_evidence_hash_valid"] is True
    assert record["reconciliation_mismatch"] is False
    assert record["expected_order_intent"]["order_intent_id"] == record["order_intent_id"]
    assert record["simulated_execution"]["execution_id"] == record["execution_id"]
    assert record["simulated_fill"]["fill_status"] == "FILLED"
    assert record["position_delta"]["position_opened"] is True
    assert record["fee_model"]["fee_usd"] >= 0
    assert record["slippage_model"]["within_tolerance"] is True

    aggregate = result.aggregates[0]
    assert aggregate["reconciliation_mismatch_count"] == 0
    assert aggregate["reconciliation_matched_count"] > 0

    validation = validate_paper_lifecycle_outcome_store(isolated_project_root)
    assert validation.status == STEP213_VALIDATION_OK
    assert validation.reconciliation_evidence_complete is True
    assert validation.reconciliation_evidence_hash_valid is True
    assert validation.no_reconciliation_mismatch is True


def test_step272_lifecycle_validator_fails_on_tampered_evidence_hash(isolated_project_root):
    execute_simulated_paper_order_lifecycle(isolated_project_root, write_output=True)
    latest_path = Path(isolated_project_root) / "storage/latest/step212_simulated_paper_order_lifecycle_latest.json"
    payload = json.loads(latest_path.read_text(encoding="utf-8"))
    payload["summaries"][0]["simulated_fill"]["fill_price"] = payload["summaries"][0]["simulated_fill"]["fill_price"] + 1.0
    payload["result_sha256"] = "tampered"
    latest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    validation = validate_simulated_paper_order_lifecycle(isolated_project_root)
    assert validation.status != STEP212_VALIDATION_OK
    assert "result_hash_valid" in validation.blocking_failures
    assert "reconciliation_evidence_hash_valid" in validation.blocking_failures


def test_step272_outcome_blocks_reconciliation_mismatch(isolated_project_root):
    execute_simulated_paper_order_lifecycle(isolated_project_root, write_output=True)
    summary_path = Path(isolated_project_root) / "data/reports/step212_simulated_paper_order_lifecycle_summary.json"
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    summary_payload["summaries"][0]["reconciliation_mismatch"] = True
    summary_payload["summaries"][0]["mismatch_reasons"] = ["TEST_FORCED_RECONCILIATION_MISMATCH"]
    summary_path.write_text(json.dumps(summary_payload, indent=2, sort_keys=True), encoding="utf-8")

    result = execute_paper_lifecycle_outcome_store(isolated_project_root, write_output=True)
    record = result.sample_outcome_records[0]
    assert record["reconciliation_mismatch"] is True
    assert record["reconciliation_evidence_hash_valid"] is False
    assert "RECONCILIATION_MISMATCH_PRESENT" in result.blocker_summary
    assert "RECONCILIATION_EVIDENCE_HASH_INVALID" in result.blocker_summary

    validation = validate_paper_lifecycle_outcome_store(isolated_project_root)
    assert validation.status != STEP213_VALIDATION_OK
    assert "reconciliation_evidence_hash_valid" in validation.blocking_failures
    assert "no_reconciliation_mismatch" in validation.blocking_failures

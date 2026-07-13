from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase7_3_disabled_signed_testnet_executor_review import (
    persist_phase7_3_disabled_signed_testnet_executor_review_report,
)
from crypto_ai_system.validation.phase7_4_disabled_execution_reconciliation_session_close import (
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase7_4_disabled_execution_reconciliation_session_close_report,
    persist_phase7_4_disabled_execution_reconciliation_session_close_report,
)


def test_phase7_4_records_disabled_reconciliation_and_session_close() -> None:
    report = persist_phase7_4_disabled_execution_reconciliation_session_close_report()

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["phase7_4_reconciliation_session_close_ready"] is True
    assert report["disabled_execution_reconciled_review_only"] is True
    assert report["session_closed_review_only"] is True
    assert report["reconciliation_mismatch"] is False
    assert report["observed_fill_count"] == 0
    assert report["observed_position_delta"] == 0.0
    assert report["observed_balance_delta"] == 0.0
    assert report["actual_order_submission_performed"] is False
    assert report["external_order_submission_performed"] is False
    assert report["exchange_endpoint_called"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["auto_promotion_allowed"] is False
    assert Path("storage/latest/phase7_4_disabled_execution_reconciliation_session_close_report.json").exists()
    assert Path("storage/latest/disabled_execution_reconciliation_report_review_only.json").exists()
    assert Path("storage/latest/disabled_execution_session_close_report_review_only.json").exists()
    assert Path("storage/latest/PHASE7_4_DISABLED_EXECUTION_RECONCILIATION_SESSION_CLOSE_HANDOFF_REVIEW_ONLY.md").exists()


def test_phase7_4_reconciliation_report_confirms_no_fill_position_or_balance_delta() -> None:
    persist_phase7_4_disabled_execution_reconciliation_session_close_report()
    reconciliation = json.load(open("storage/latest/disabled_execution_reconciliation_report_review_only.json", encoding="utf-8"))

    assert reconciliation["report_type"] == "disabled_execution_reconciliation_report_review_only"
    assert reconciliation["execution_reconciled_review_only"] is True
    assert reconciliation["blocked_execution_evidence_linked"] is True
    assert reconciliation["expected_fill_count"] == 0
    assert reconciliation["observed_fill_count"] == 0
    assert reconciliation["expected_position_delta"] == 0.0
    assert reconciliation["observed_position_delta"] == 0.0
    assert reconciliation["expected_balance_delta"] == 0.0
    assert reconciliation["observed_balance_delta"] == 0.0
    assert reconciliation["reconciliation_mismatch"] is False
    assert reconciliation["promotion_blocked_if_mismatch"] is True
    assert reconciliation["actual_order_submission_performed"] is False
    assert reconciliation["external_order_submission_performed"] is False
    assert reconciliation["exchange_endpoint_called"] is False


def test_phase7_4_session_close_keeps_promotion_and_execution_disabled() -> None:
    persist_phase7_4_disabled_execution_reconciliation_session_close_report()
    session = json.load(open("storage/latest/disabled_execution_session_close_report_review_only.json", encoding="utf-8"))

    assert session["report_type"] == "disabled_execution_session_close_report_review_only"
    assert session["session_closed_review_only"] is True
    assert session["session_close_blocked"] is False
    assert session["session_close_blockers"] == []
    assert session["signed_testnet_promotion_allowed"] is False
    assert session["ready_for_signed_testnet_execution"] is False
    assert session["testnet_order_submission_allowed"] is False
    assert session["place_order_enabled"] is False
    assert session["cancel_order_enabled"] is False
    assert session["signed_order_executor_enabled"] is False
    assert session["runtime_settings_mutated"] is False
    assert session["score_weights_mutated"] is False
    assert session["auto_promotion_allowed"] is False


def test_phase7_4_blocks_if_phase7_3_source_is_not_ready() -> None:
    persist_phase7_3_disabled_signed_testnet_executor_review_report()
    path = Path("storage/latest/phase7_3_disabled_signed_testnet_executor_review_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["status"] = "PHASE7_3_DISABLED_SIGNED_TESTNET_EXECUTOR_REVIEW_BLOCKED_REVIEW_ONLY"
    source["phase7_3_disabled_executor_review_ready"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _reconciliation, _session = build_phase7_4_disabled_execution_reconciliation_session_close_report(
        cfg=cfg, run_phase7_3_first=False
    )

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "PHASE7_3_DISABLED_EXECUTOR_REVIEW_NOT_READY" in report["block_reasons"]
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False


def test_phase7_4_blocks_on_reconciliation_mismatch_evidence() -> None:
    persist_phase7_3_disabled_signed_testnet_executor_review_report()
    path = Path("storage/latest/disabled_signed_testnet_blocked_execution_evidence_review_only.json")
    evidence = json.load(open(path, encoding="utf-8"))
    evidence["exchange_endpoint_called"] = True
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, reconciliation, session = build_phase7_4_disabled_execution_reconciliation_session_close_report(
        cfg=cfg, run_phase7_3_first=False
    )

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["reconciliation_mismatch"] is True
    assert "EXCHANGE_ENDPOINT_CALLED_UNEXPECTEDLY" in report["block_reasons"]
    assert reconciliation["reconciliation_mismatch"] is True
    assert "EXCHANGE_ENDPOINT_CALLED_UNEXPECTEDLY" in reconciliation["reconciliation_mismatch_reasons"]
    assert session["session_closed_review_only"] is False
    assert report["external_order_submission_performed"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False

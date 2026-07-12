from __future__ import annotations

import json
from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase8_2_exchange_adapter_write_path_dry_validation import (
    build_phase8_2_exchange_adapter_write_path_dry_validation_report,
)
from crypto_ai_system.validation.phase8_3_hot_path_preorder_risk_gate import (
    CANONICAL_ID_CHAIN_FIELDS,
    REQUIRED_HOT_PATH_CHECKS,
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase8_3_hot_path_preorder_risk_gate_report,
    persist_phase8_3_hot_path_preorder_risk_gate_report,
    validate_hot_path_preorder_risk_gate,
)
from tests.agents.test_phase8_2_exchange_adapter_write_path_dry_validation import _write_ready_phase8_1_sources


def _write_ready_phase8_2_sources() -> None:
    _write_ready_phase8_1_sources()
    cfg = load_config()
    latest = Path("storage/latest")
    latest.mkdir(parents=True, exist_ok=True)
    report, dry_validation, guard = build_phase8_2_exchange_adapter_write_path_dry_validation_report(
        cfg=cfg,
        run_phase8_1_first=False,
    )
    atomic_write_json(latest / "phase8_2_exchange_adapter_write_path_dry_validation_report.json", report)
    atomic_write_json(latest / "exchange_adapter_write_path_dry_validation_review_only.json", dry_validation)
    atomic_write_json(latest / "exchange_adapter_write_path_dry_validation_guard_report.json", guard)


def test_phase8_3_builds_fresh_hot_path_risk_gate_still_disabled() -> None:
    _write_ready_phase8_2_sources()
    cfg = load_config()
    report, hot_path_gate, guard = build_phase8_3_hot_path_preorder_risk_gate_report(
        cfg=cfg,
        run_phase8_2_first=False,
    )

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["phase8_3_hot_path_risk_gate_ready"] is True
    assert report["phase8_4_final_guard_may_begin"] is True
    assert hot_path_gate["gate_type"] == "phase8_3_hot_path_preorder_risk_gate_review_only"
    assert hot_path_gate["review_only"] is True
    assert hot_path_gate["hot_path_review_only"] is True
    assert hot_path_gate["pre_submit_check_only"] is True
    assert hot_path_gate["no_order_endpoint_calls"] is True
    assert hot_path_gate["required_hot_path_checks"] == REQUIRED_HOT_PATH_CHECKS
    assert all(hot_path_gate["check_results"][check] is True for check in REQUIRED_HOT_PATH_CHECKS)
    assert set(CANONICAL_ID_CHAIN_FIELDS) == set(hot_path_gate["canonical_id_chain"].keys())
    assert guard["guard_passed"] is True
    assert report["exchange_endpoint_called"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
    assert report["block_reasons"] == []


def test_phase8_3_persist_writes_review_only_artifacts() -> None:
    _write_ready_phase8_2_sources()
    report = persist_phase8_3_hot_path_preorder_risk_gate_report(run_phase8_2_first=False)

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert Path("storage/latest/phase8_3_hot_path_preorder_risk_gate_report.json").exists()
    assert Path("storage/latest/hot_path_preorder_risk_gate_review_only.json").exists()
    assert Path("storage/latest/hot_path_preorder_risk_gate_guard_report.json").exists()
    assert Path("storage/signed_testnet/hot_path_preorder_risk_gate_review_only.json").exists()
    assert Path("storage/phase8_3_hot_path_preorder_risk_gate/PHASE8_3_HOT_PATH_PREORDER_RISK_GATE_HANDOFF_REVIEW_ONLY.md").exists()


def test_phase8_3_validator_blocks_stale_price_spread_kill_switch_and_missing_chain() -> None:
    _write_ready_phase8_2_sources()
    cfg = load_config()
    _report, hot_path_gate, _guard = build_phase8_3_hot_path_preorder_risk_gate_report(
        cfg=cfg,
        run_phase8_2_first=False,
    )
    hot_path_gate["market_data_snapshot"]["price_age_ms"] = 5000
    hot_path_gate["spread_slippage_evidence"]["observed_spread_bps"] = "99.0"
    hot_path_gate["kill_switch_evidence"]["kill_switch_active"] = True
    del hot_path_gate["canonical_id_chain"]["research_signal_id"]
    hot_path_gate["order_endpoint_called"] = True

    result = validate_hot_path_preorder_risk_gate(hot_path_gate)

    assert result["hot_path_preorder_risk_gate_valid_review_only"] is False
    assert result["hot_path_preorder_risk_gate_blocked_fail_closed"] is True
    assert "order_endpoint_called" in result["unsafe_truthy_fields"]
    blockers = result["hot_path_preorder_risk_gate_blockers"]
    assert "PRICE_STALENESS_LIMIT_BREACHED" in blockers
    assert "SPREAD_LIMIT_BREACHED" in blockers
    assert "KILL_SWITCH_BLOCK_ACTIVE_OR_UNCHECKED" in blockers
    assert any(item.startswith("CANONICAL_ID_CHAIN_MISSING_FIELDS:research_signal_id") for item in blockers)


def test_phase8_3_blocks_if_phase8_2_not_ready() -> None:
    _write_ready_phase8_2_sources()
    path = Path("storage/latest/phase8_2_exchange_adapter_write_path_dry_validation_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["status"] = "PHASE8_2_EXCHANGE_ADAPTER_WRITE_PATH_DRY_VALIDATION_BLOCKED_REVIEW_ONLY"
    source["blocked"] = True
    source["fail_closed"] = True
    source["phase8_2_write_path_dry_validation_ready"] = False
    source["phase8_3_hot_path_risk_gate_may_begin"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _hot_path_gate, _guard = build_phase8_3_hot_path_preorder_risk_gate_report(
        cfg=cfg,
        run_phase8_2_first=False,
    )

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "PHASE8_3_PHASE8_2_EVIDENCE_NOT_READY:phase8_2_report" in report["block_reasons"]
    assert report["exchange_endpoint_called"] is False
    assert report["order_endpoint_called"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["signed_order_executor_enabled"] is False


def test_phase8_3_blocks_loss_caps_api_error_and_reconciliation_mismatch() -> None:
    _write_ready_phase8_2_sources()
    cfg = load_config()
    _report, hot_path_gate, _guard = build_phase8_3_hot_path_preorder_risk_gate_report(
        cfg=cfg,
        run_phase8_2_first=False,
    )
    hot_path_gate["account_risk_state"]["projected_order_notional"] = "999.0"
    hot_path_gate["account_risk_state"]["daily_realized_loss"] = "999.0"
    hot_path_gate["account_risk_state"]["consecutive_losses"] = 9
    hot_path_gate["api_health_evidence"]["recent_api_error_rate"] = "0.99"
    hot_path_gate["reconciliation_evidence"]["open_reconciliation_mismatch"] = True

    result = validate_hot_path_preorder_risk_gate(hot_path_gate)
    blockers = result["hot_path_preorder_risk_gate_blockers"]

    assert result["hot_path_preorder_risk_gate_valid_review_only"] is False
    assert "MAX_SINGLE_ORDER_NOTIONAL_BREACHED" in blockers
    assert "DAILY_LOSS_LIMIT_BREACHED" in blockers
    assert "MAX_CONSECUTIVE_LOSS_LIMIT_BREACHED" in blockers
    assert "API_ERROR_RATE_LIMIT_BREACHED" in blockers
    assert "RECONCILIATION_MISMATCH_PRESENT_OR_UNCHECKED" in blockers

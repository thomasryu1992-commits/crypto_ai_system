from __future__ import annotations

import json
from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase8_1_secret_manager_key_handling_design import (
    build_phase8_1_secret_manager_key_handling_design_report,
)
from crypto_ai_system.validation.phase8_2_exchange_adapter_write_path_dry_validation import (
    REQUIRED_WRITE_PATH_CHECKS,
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase8_2_exchange_adapter_write_path_dry_validation_report,
    persist_phase8_2_exchange_adapter_write_path_dry_validation_report,
    validate_exchange_adapter_write_path_dry_validation,
)
from tests.agents.test_phase8_1_secret_manager_key_handling_design import _write_ready_phase7_17_sources


def _write_ready_phase8_1_sources() -> None:
    _write_ready_phase7_17_sources()
    cfg = load_config()
    latest = Path("storage/latest")
    latest.mkdir(parents=True, exist_ok=True)
    report, design, guard = build_phase8_1_secret_manager_key_handling_design_report(
        cfg=cfg,
        run_phase7_17_first=False,
    )
    atomic_write_json(latest / "phase8_1_secret_manager_key_handling_design_report.json", report)
    atomic_write_json(latest / "secret_manager_key_handling_design_review_only.json", design)
    atomic_write_json(latest / "secret_key_handling_design_guard_report.json", guard)


def test_phase8_2_builds_write_path_dry_validation_still_disabled_no_endpoint_calls() -> None:
    _write_ready_phase8_1_sources()
    cfg = load_config()
    report, dry_validation, guard = build_phase8_2_exchange_adapter_write_path_dry_validation_report(
        cfg=cfg,
        run_phase8_1_first=False,
    )

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["phase8_2_write_path_dry_validation_ready"] is True
    assert report["phase8_3_hot_path_risk_gate_may_begin"] is True
    assert dry_validation["dry_validation_type"] == "phase8_2_exchange_adapter_write_path_dry_validation_review_only"
    assert dry_validation["review_only"] is True
    assert dry_validation["dry_validation_only"] is True
    assert dry_validation["no_order_endpoint_calls"] is True
    assert dry_validation["required_write_path_checks"] == REQUIRED_WRITE_PATH_CHECKS
    assert all(dry_validation["check_results"][check] is True for check in REQUIRED_WRITE_PATH_CHECKS)
    assert dry_validation["order_payload_candidate"]["clientOrderId"]
    assert dry_validation["signing_preimage_dry_validation"]["preimage_sha256"]
    assert dry_validation["signing_preimage_dry_validation"]["signature_created"] is False
    assert dry_validation["duplicate_submit_prevention"]["same_id_blocks_second_submit"] is True
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


def test_phase8_2_persist_writes_review_only_artifacts() -> None:
    _write_ready_phase8_1_sources()
    report = persist_phase8_2_exchange_adapter_write_path_dry_validation_report(run_phase8_1_first=False)

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert Path("storage/latest/phase8_2_exchange_adapter_write_path_dry_validation_report.json").exists()
    assert Path("storage/latest/exchange_adapter_write_path_dry_validation_review_only.json").exists()
    assert Path("storage/latest/exchange_adapter_write_path_dry_validation_guard_report.json").exists()
    assert Path("storage/signed_testnet/exchange_adapter_write_path_dry_validation_review_only.json").exists()
    assert Path("storage/phase8_2_exchange_adapter_write_path_dry_validation/PHASE8_2_EXCHANGE_ADAPTER_WRITE_PATH_DRY_VALIDATION_HANDOFF_REVIEW_ONLY.md").exists()


def test_phase8_2_validator_blocks_endpoint_call_signature_and_bad_precision() -> None:
    _write_ready_phase8_1_sources()
    cfg = load_config()
    _report, dry_validation, _guard = build_phase8_2_exchange_adapter_write_path_dry_validation_report(
        cfg=cfg,
        run_phase8_1_first=False,
    )
    dry_validation["order_endpoint_called"] = True
    dry_validation["http_request_sent"] = True
    dry_validation["signature_created"] = True
    dry_validation["signing_preimage_dry_validation"]["signature_created"] = True
    dry_validation["order_payload_candidate"]["quantity"] = "0.0015"
    dry_validation["order_payload_candidate"]["price"] = "100000.05"
    dry_validation["order_payload_candidate"]["api_secret_value"] = "sk-this-looks-like-a-secret-value-1234567890"

    result = validate_exchange_adapter_write_path_dry_validation(dry_validation)

    assert result["write_path_dry_validation_valid_review_only"] is False
    assert result["write_path_dry_validation_blocked_fail_closed"] is True
    assert "order_endpoint_called" in result["unsafe_truthy_fields"]
    assert "http_request_sent" in result["unsafe_truthy_fields"]
    assert "signature_created" in result["unsafe_truthy_fields"]
    assert any("QUANTITY_STEP_SIZE_NOT_ALIGNED" in item for item in result["write_path_dry_validation_blockers"])
    assert any("PRICE_TICK_SIZE_NOT_ALIGNED" in item for item in result["write_path_dry_validation_blockers"])
    assert result["secret_material_findings"]


def test_phase8_2_blocks_if_phase8_1_not_ready() -> None:
    _write_ready_phase8_1_sources()
    path = Path("storage/latest/phase8_1_secret_manager_key_handling_design_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["status"] = "PHASE8_1_SECRET_MANAGER_KEY_HANDLING_DESIGN_BLOCKED_REVIEW_ONLY"
    source["phase8_1_secret_key_design_ready"] = False
    source["phase8_2_write_path_dry_validation_may_begin"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _dry_validation, _guard = build_phase8_2_exchange_adapter_write_path_dry_validation_report(
        cfg=cfg,
        run_phase8_1_first=False,
    )

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "PHASE8_2_PHASE8_1_EVIDENCE_NOT_READY:phase8_1_report" in report["block_reasons"]
    assert report["exchange_endpoint_called"] is False
    assert report["order_endpoint_called"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["signed_order_executor_enabled"] is False

from __future__ import annotations

import json
from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase7_17_final_pre_executor_review_packet import (
    build_phase7_17_final_pre_executor_review_packet_report,
)
from crypto_ai_system.validation.phase8_1_secret_manager_key_handling_design import (
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase8_1_secret_manager_key_handling_design_report,
    persist_phase8_1_secret_manager_key_handling_design_report,
    validate_secret_key_handling_design,
)
from tests.agents.test_phase7_17_final_pre_executor_review_packet import _write_ready_phase7_16_sources


def _write_ready_phase7_17_sources() -> None:
    _write_ready_phase7_16_sources()
    cfg = load_config()
    latest = Path("storage/latest")
    latest.mkdir(parents=True, exist_ok=True)
    phase7_17_report, packet, guard = build_phase7_17_final_pre_executor_review_packet_report(
        cfg=cfg, run_phase7_16_first=False
    )
    atomic_write_json(latest / "phase7_17_final_pre_executor_review_packet_report.json", phase7_17_report)
    atomic_write_json(latest / "phase7_final_pre_executor_review_packet_review_only.json", packet)
    atomic_write_json(latest / "phase7_final_pre_executor_review_guard_report.json", guard)


def test_phase8_1_builds_metadata_only_secret_key_design_still_disabled() -> None:
    _write_ready_phase7_17_sources()
    cfg = load_config()
    report, design, guard = build_phase8_1_secret_manager_key_handling_design_report(
        cfg=cfg, run_phase7_17_first=False
    )

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["phase8_1_secret_key_design_ready"] is True
    assert report["phase8_2_write_path_dry_validation_may_begin"] is True
    assert design["design_type"] == "phase8_1_secret_manager_key_handling_design_review_only"
    assert design["review_only"] is True
    assert design["design_only"] is True
    assert design["metadata_only_key_handling"] is True
    assert design["secret_values_never_logged"] is True
    assert design["secret_values_never_persisted"] is True
    assert design["secret_files_not_read_or_created"] is True
    assert guard["guard_passed"] is True
    assert report["secret_value_accessed"] is False
    assert report["secret_file_read"] is False
    assert report["secret_file_created"] is False
    assert report["actual_executor_enablement_performed"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
    assert report["block_reasons"] == []


def test_phase8_1_persist_writes_review_only_artifacts() -> None:
    _write_ready_phase7_17_sources()
    report = persist_phase8_1_secret_manager_key_handling_design_report(run_phase7_17_first=False)

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert Path("storage/latest/phase8_1_secret_manager_key_handling_design_report.json").exists()
    assert Path("storage/latest/secret_manager_key_handling_design_review_only.json").exists()
    assert Path("storage/latest/secret_key_handling_design_guard_report.json").exists()
    assert Path("storage/signed_testnet/secret_manager_key_handling_design_review_only.json").exists()
    assert Path("storage/phase8_1_secret_manager_key_handling_design/PHASE8_1_SECRET_MANAGER_KEY_HANDLING_DESIGN_HANDOFF_REVIEW_ONLY.md").exists()


def test_phase8_1_design_validator_blocks_secret_values_and_execution_flags() -> None:
    _write_ready_phase7_17_sources()
    cfg = load_config()
    _report, design, _guard = build_phase8_1_secret_manager_key_handling_design_report(
        cfg=cfg, run_phase7_17_first=False
    )
    design["api_secret_value"] = "sk-this-looks-like-a-secret-value-1234567890"
    design["ready_for_signed_testnet_execution"] = True
    design["signed_order_executor_enabled"] = True

    result = validate_secret_key_handling_design(design)

    assert result["secret_key_handling_design_valid_review_only"] is False
    assert result["secret_key_handling_design_blocked_fail_closed"] is True
    assert "ready_for_signed_testnet_execution" in result["unsafe_truthy_fields"]
    assert "signed_order_executor_enabled" in result["unsafe_truthy_fields"]
    assert result["secret_material_findings"]


def test_phase8_1_blocks_if_phase7_17_not_ready() -> None:
    _write_ready_phase7_17_sources()
    path = Path("storage/latest/phase7_17_final_pre_executor_review_packet_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["status"] = "PHASE7_17_FINAL_PRE_EXECUTOR_REVIEW_PACKET_BLOCKED_REVIEW_ONLY"
    source["phase7_final_pre_executor_review_ready"] = False
    source["phase8_preparation_review_may_begin"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _design, _guard = build_phase8_1_secret_manager_key_handling_design_report(
        cfg=cfg, run_phase7_17_first=False
    )

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "PHASE8_1_PHASE7_17_EVIDENCE_NOT_READY:phase7_17_report" in report["block_reasons"]
    assert report["secret_value_accessed"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["signed_order_executor_enabled"] is False

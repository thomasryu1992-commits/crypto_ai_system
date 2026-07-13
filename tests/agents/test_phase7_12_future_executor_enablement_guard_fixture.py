from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase7_12_future_executor_enablement_guard_fixture import (
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase7_12_future_executor_enablement_guard_fixture_report,
    persist_phase7_12_future_executor_enablement_guard_fixture_report,
    validate_enablement_guard_fixture,
)


def _write_json(path: str, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_ready_phase7_11_sources() -> None:
    _write_json(
        "storage/latest/phase7_11_future_executor_enablement_design_review_report.json",
        {
            "phase7_11_future_executor_enablement_design_review_id": "phase7_11_ready_fixture",
            "status": "PHASE7_11_FUTURE_EXECUTOR_ENABLEMENT_DESIGN_REVIEW_RECORDED_REVIEW_ONLY",
            "blocked": False,
            "fail_closed": False,
            "review_only": True,
            "phase7_11_enablement_design_ready": True,
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "phase7_11_report_sha256": "phase7_11_hash_fixture",
        },
    )
    _write_json(
        "storage/latest/future_signed_testnet_executor_enablement_design_packet_review_only.json",
        {
            "packet_type": "future_signed_testnet_executor_enablement_design_packet_review_only",
            "review_only": True,
            "enablement_design_only": True,
            "not_runtime_authority": True,
            "metadata_only_key_reference_validated_review_only": True,
            "prerequisite_packet_hash_matches": True,
            "future_executor_approval_intake_validated_review_only": True,
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "future_executor_enablement_design_packet_sha256": "design_packet_hash_fixture",
        },
    )
    _write_json(
        "storage/latest/future_signed_testnet_executor_enablement_design_guard_report.json",
        {
            "guard_type": "future_signed_testnet_executor_enablement_design_guard_review_only",
            "review_only": True,
            "guard_passed": True,
            "blocks_executor_enablement": True,
            "blocks_order_submission": True,
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "future_executor_enablement_design_guard_report_sha256": "design_guard_hash_fixture",
        },
    )


def test_phase7_12_records_guard_fixture_from_ready_sources() -> None:
    _write_ready_phase7_11_sources()
    cfg = load_config()
    report, _fixture, _guard, _invalid = build_phase7_12_future_executor_enablement_guard_fixture_report(cfg=cfg, run_phase7_11_first=False)

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["review_only"] is True
    assert report["guard_fixture_only"] is True
    assert report["phase7_12_guard_fixture_ready"] is True
    assert report["valid_enablement_guard_fixture_passed_review_only_validation"] is True
    assert report["invalid_enablement_guard_fixtures_blocked_fail_closed"] is True
    assert report["enablement_guard_fixture_guard_passed"] is True
    assert report["actual_executor_enablement_performed"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
    assert report["block_reasons"] == []


def test_phase7_12_persist_writes_artifacts() -> None:
    _write_ready_phase7_11_sources()
    report = persist_phase7_12_future_executor_enablement_guard_fixture_report(run_phase7_11_first=False)

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert Path("storage/latest/phase7_12_future_executor_enablement_guard_fixture_report.json").exists()
    assert Path("storage/latest/future_signed_testnet_executor_enablement_guard_valid_fixture_review_only.json").exists()
    assert Path("storage/latest/future_signed_testnet_executor_enablement_guard_fixture_guard_report.json").exists()


def test_phase7_12_validator_blocks_unsafe_flags() -> None:
    _write_ready_phase7_11_sources()
    cfg = load_config()
    _report, fixture, _guard, _invalid = build_phase7_12_future_executor_enablement_guard_fixture_report(cfg=cfg, run_phase7_11_first=False)
    fixture["signed_order_executor_enabled"] = True
    fixture["testnet_order_submission_allowed"] = True
    result = validate_enablement_guard_fixture(fixture)

    assert result["fixture_valid_review_only"] is False
    assert result["fixture_blocked_fail_closed"] is True
    assert "signed_order_executor_enabled" in result["unsafe_truthy_fields"]
    assert "testnet_order_submission_allowed" in result["unsafe_truthy_fields"]


def test_phase7_12_blocks_if_phase7_11_not_ready() -> None:
    _write_ready_phase7_11_sources()
    path = Path("storage/latest/phase7_11_future_executor_enablement_design_review_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["status"] = "PHASE7_11_FUTURE_EXECUTOR_ENABLEMENT_DESIGN_REVIEW_BLOCKED_REVIEW_ONLY"
    source["phase7_11_enablement_design_ready"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _fixture, _guard, _invalid = build_phase7_12_future_executor_enablement_guard_fixture_report(cfg=cfg, run_phase7_11_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "PHASE7_11_ENABLEMENT_DESIGN_NOT_READY" in report["block_reasons"]
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["signed_order_executor_enabled"] is False


def test_phase7_12_blocks_if_design_guard_not_passed() -> None:
    _write_ready_phase7_11_sources()
    path = Path("storage/latest/future_signed_testnet_executor_enablement_design_guard_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["guard_passed"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _fixture, _guard, _invalid = build_phase7_12_future_executor_enablement_guard_fixture_report(cfg=cfg, run_phase7_11_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert "FUTURE_EXECUTOR_ENABLEMENT_DESIGN_GUARD_NOT_PASSED" in report["block_reasons"]
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False

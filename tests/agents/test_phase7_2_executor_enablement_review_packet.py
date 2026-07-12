from __future__ import annotations

from pathlib import Path

from crypto_ai_system.validation.phase7_2_executor_enablement_review_packet import (
    STATUS_RECORDED_REVIEW_ONLY,
    persist_phase7_2_executor_enablement_review_packet_report,
)


def test_phase7_2_records_enablement_review_packet_and_keeps_executor_disabled() -> None:
    report = persist_phase7_2_executor_enablement_review_packet_report()

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["phase7_2_executor_enablement_review_ready"] is True
    assert report["executor_enablement_review_packet_created"] is True
    assert report["disabled_executor_enablement_guard_created"] is True
    assert report["actual_executor_enablement_performed"] is False
    assert report["phase7_execution_authority"] is False
    assert report["phase7_order_submission_authority"] is False
    assert report["signed_testnet_executor_enablement_authority"] is False
    assert report["signed_testnet_order_submission_authority"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
    assert report["external_order_submission_performed"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["auto_promotion_allowed"] is False
    assert Path("storage/latest/phase7_2_executor_enablement_review_packet_report.json").exists()
    assert Path("storage/latest/signed_testnet_executor_enablement_review_packet_review_only.json").exists()
    assert Path("storage/latest/signed_testnet_executor_enablement_disabled_guard_report.json").exists()
    assert Path("storage/latest/PHASE7_2_EXECUTOR_ENABLEMENT_REVIEW_HANDOFF_REVIEW_ONLY.md").exists()


def test_phase7_2_packet_is_review_only_and_forbids_executor_enablement() -> None:
    persist_phase7_2_executor_enablement_review_packet_report()
    import json

    packet = json.load(open("storage/latest/signed_testnet_executor_enablement_review_packet_review_only.json", encoding="utf-8"))
    guard = json.load(open("storage/latest/signed_testnet_executor_enablement_disabled_guard_report.json", encoding="utf-8"))

    assert packet["review_only"] is True
    assert packet["executor_enablement_review_only"] is True
    assert packet["actual_executor_enablement_performed"] is False
    assert packet["signed_testnet_execution_authority"] is False
    assert packet["signed_testnet_order_submission_authority"] is False
    assert "signed_executor_enablement" in packet["forbidden_scope"]
    assert guard["guard_passed"] is True
    assert guard["actual_executor_enablement_performed"] is False
    assert guard["signed_order_executor_enabled"] is False

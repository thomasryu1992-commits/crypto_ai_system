from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.execution.disabled_signed_testnet_executor import DisabledSignedTestnetExecutor
from crypto_ai_system.validation.phase7_2_executor_enablement_review_packet import (
    persist_phase7_2_executor_enablement_review_packet_report,
)
from crypto_ai_system.validation.phase7_3_disabled_signed_testnet_executor_review import (
    STATUS_RECORDED_REVIEW_ONLY,
    persist_phase7_3_disabled_signed_testnet_executor_review_report,
)


def _valid_payload() -> dict:
    persist_phase7_2_executor_enablement_review_packet_report()
    return json.load(open("storage/latest/signed_testnet_would_submit_payload_FIXTURE_REVIEW_ONLY.json", encoding="utf-8"))


def test_phase7_3_records_disabled_executor_review_and_keeps_execution_disabled() -> None:
    report = persist_phase7_3_disabled_signed_testnet_executor_review_report()

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["phase7_3_disabled_executor_review_ready"] is True
    assert report["disabled_executor_interface_added"] is True
    assert report["submit_order_blocked_review_only"] is True
    assert report["cancel_order_blocked_review_only"] is True
    assert report["blocked_execution_evidence_created"] is True
    assert report["blocked_cancel_evidence_created"] is True
    assert report["actual_order_submission_performed"] is False
    assert report["actual_cancel_performed"] is False
    assert report["exchange_endpoint_called"] is False
    assert report["endpoint_call_count"] == 0
    assert report["phase7_execution_authority"] is False
    assert report["phase7_order_submission_authority"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
    assert report["external_order_submission_performed"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["auto_promotion_allowed"] is False
    assert Path("storage/latest/phase7_3_disabled_signed_testnet_executor_review_report.json").exists()
    assert Path("storage/latest/disabled_signed_testnet_blocked_execution_evidence_review_only.json").exists()
    assert Path("storage/latest/disabled_signed_testnet_blocked_cancel_evidence_review_only.json").exists()
    assert Path("storage/latest/PHASE7_3_DISABLED_SIGNED_TESTNET_EXECUTOR_HANDOFF_REVIEW_ONLY.md").exists()


def test_disabled_executor_submit_order_always_returns_blocked_evidence() -> None:
    payload = _valid_payload()
    executor = DisabledSignedTestnetExecutor()
    evidence = executor.submit_order(payload)

    assert evidence["status"] == "SIGNED_TESTNET_ORDER_SUBMISSION_BLOCKED_EXECUTOR_DISABLED_REVIEW_ONLY"
    assert evidence["blocked"] is True
    assert evidence["fail_closed"] is True
    assert evidence["submit_order_blocked_review_only"] is True
    assert evidence["payload_valid_review_only"] is True
    assert evidence["exchange_endpoint_called"] is False
    assert evidence["endpoint_call_count"] == 0
    assert evidence["actual_order_submission_performed"] is False
    assert evidence["external_order_submission_performed"] is False
    assert evidence["ready_for_signed_testnet_execution"] is False
    assert evidence["testnet_order_submission_allowed"] is False
    assert evidence["place_order_enabled"] is False
    assert evidence["signed_order_executor_enabled"] is False


def test_disabled_executor_blocks_missing_idempotency_key_fail_closed() -> None:
    payload = _valid_payload()
    payload["idempotency_key"] = ""
    evidence = DisabledSignedTestnetExecutor().submit_order(payload)

    assert evidence["blocked"] is True
    assert evidence["fail_closed"] is True
    assert evidence["submit_order_blocked_review_only"] is True
    assert evidence["payload_valid_review_only"] is False
    assert "MISSING_REQUIRED_PAYLOAD_FIELDS:idempotency_key" in evidence["payload_validation"]["payload_blockers"]
    assert evidence["exchange_endpoint_called"] is False
    assert evidence["external_order_submission_performed"] is False


def test_disabled_executor_blocks_missing_canonical_id_chain_fail_closed() -> None:
    payload = _valid_payload()
    payload["canonical_id_chain"] = {}
    evidence = DisabledSignedTestnetExecutor().submit_order(payload)

    assert evidence["blocked"] is True
    assert evidence["fail_closed"] is True
    assert evidence["payload_valid_review_only"] is False
    assert any(item.startswith("MISSING_CANONICAL_ID_CHAIN_FIELDS:") for item in evidence["payload_validation"]["payload_blockers"])
    assert evidence["exchange_endpoint_called"] is False
    assert evidence["external_order_submission_performed"] is False


def test_disabled_executor_blocks_unsafe_testnet_order_flag_fail_closed() -> None:
    payload = _valid_payload()
    payload["testnet_order_submission_allowed"] = True
    evidence = DisabledSignedTestnetExecutor().submit_order(payload)

    assert evidence["blocked"] is True
    assert evidence["fail_closed"] is True
    assert evidence["payload_valid_review_only"] is False
    assert any("UNSAFE_WOULD_SUBMIT_PAYLOAD_FLAG" in item for item in evidence["payload_validation"]["payload_blockers"])
    assert evidence["testnet_order_submission_allowed"] is False
    assert evidence["exchange_endpoint_called"] is False
    assert evidence["external_order_submission_performed"] is False


def test_disabled_executor_blocks_unsafe_place_order_flag_fail_closed() -> None:
    payload = _valid_payload()
    payload["place_order_enabled"] = True
    evidence = DisabledSignedTestnetExecutor().submit_order(payload)

    assert evidence["blocked"] is True
    assert evidence["fail_closed"] is True
    assert evidence["payload_valid_review_only"] is False
    assert any("UNSAFE_WOULD_SUBMIT_PAYLOAD_FLAG" in item for item in evidence["payload_validation"]["payload_blockers"])
    assert evidence["place_order_enabled"] is False
    assert evidence["exchange_endpoint_called"] is False
    assert evidence["external_order_submission_performed"] is False


def test_disabled_executor_blocks_hard_cap_breach_fail_closed() -> None:
    payload = _valid_payload()
    payload["notional"] = float(payload.get("max_testnet_notional_usd") or 25.0) + 1000.0
    evidence = DisabledSignedTestnetExecutor().submit_order(payload)

    assert evidence["blocked"] is True
    assert evidence["fail_closed"] is True
    assert evidence["payload_valid_review_only"] is False
    assert "HARD_CAP_EXCEEDED_MAX_TESTNET_NOTIONAL" in evidence["payload_validation"]["payload_blockers"]
    assert evidence["exchange_endpoint_called"] is False
    assert evidence["external_order_submission_performed"] is False


def test_disabled_executor_cancel_order_returns_blocked_cancel_evidence() -> None:
    payload = _valid_payload()
    executor = DisabledSignedTestnetExecutor()
    submit = executor.submit_order(payload)
    cancel = executor.cancel_order(execution_id=submit["execution_id"], payload={"execution_id": submit["execution_id"]})

    assert cancel["status"] == "SIGNED_TESTNET_CANCEL_BLOCKED_EXECUTOR_DISABLED_REVIEW_ONLY"
    assert cancel["blocked"] is True
    assert cancel["fail_closed"] is True
    assert cancel["cancel_order_blocked_review_only"] is True
    assert cancel["exchange_endpoint_called"] is False
    assert cancel["endpoint_call_count"] == 0
    assert cancel["actual_cancel_performed"] is False
    assert cancel["external_order_submission_performed"] is False
    assert cancel["cancel_order_enabled"] is False
    assert cancel["signed_order_executor_enabled"] is False

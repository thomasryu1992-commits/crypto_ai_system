from __future__ import annotations

from crypto_ai_system.governance.common import (
    canonical_utc_blockers,
    expected_value_blockers,
    required_field_blockers,
    review_only_permission_state,
    unsafe_field_blockers,
    verify_embedded_hash,
)
from crypto_ai_system.utils.audit import sha256_json


def test_required_fields_and_timestamp_block_fail_closed() -> None:
    payload = {
        "approval_packet_id": "packet_1",
        "canonical_utc_timestamp": "not-a-canonical-time",
    }

    blockers = required_field_blockers(
        payload,
        ["approval_packet_id", "approval_intake_id"],
        prefix="MANUAL_APPROVAL_FIELD_MISSING",
    )
    blockers.extend(
        canonical_utc_blockers(
            payload,
            "canonical_utc_timestamp",
            blocker="MANUAL_APPROVAL_TIMESTAMP_NOT_CANONICAL_UTC",
        )
    )

    assert blockers == [
        "MANUAL_APPROVAL_FIELD_MISSING:approval_intake_id",
        "MANUAL_APPROVAL_TIMESTAMP_NOT_CANONICAL_UTC",
    ]


def test_embedded_hash_verification_is_deterministic() -> None:
    payload = {"status": "REVIEW_ONLY"}
    payload["payload_sha256"] = sha256_json(payload)

    assert verify_embedded_hash(payload, "payload_sha256") is True

    tampered = dict(payload)
    tampered["status"] = "CHANGED"
    assert verify_embedded_hash(tampered, "payload_sha256") is False


def test_expected_values_and_unsafe_flags_are_blocked() -> None:
    payload = {
        "source_report_hash": "actual",
        "testnet_order_submission_allowed": True,
    }

    assert expected_value_blockers(
        payload,
        {"source_report_hash": "expected"},
        prefix="MANUAL_APPROVAL_HASH_CHAIN_MISMATCH",
    ) == [
        "MANUAL_APPROVAL_HASH_CHAIN_MISMATCH:source_report_hash"
    ]

    assert unsafe_field_blockers(
        payload,
        fields=["testnet_order_submission_allowed"],
        prefix="UNSAFE_MANUAL_APPROVAL_FIELD_TRUE",
    ) == [
        "UNSAFE_MANUAL_APPROVAL_FIELD_TRUE:"
        "testnet_order_submission_allowed"
    ]


def test_review_only_permission_state_is_complete_and_all_false() -> None:
    state = review_only_permission_state()

    assert state
    assert not any(state.values())
    assert state["approval_intake_validated"] is False
    assert state["ready_for_signed_testnet_execution"] is False
    assert state["testnet_order_submission_allowed"] is False
    assert state["external_order_submission_allowed"] is False
    assert state["place_order_enabled"] is False
    assert state["signed_order_executor_enabled"] is False

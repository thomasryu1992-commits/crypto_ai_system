from __future__ import annotations

from pathlib import Path

from crypto_ai_system.governance.readiness_common import (
    artifact_hash,
    manual_value_filled,
    positive_float,
    positive_int,
    positive_integer,
    positive_number,
    readiness_review_permission_state,
    source_summary,
    unsafe_flags_by_artifact,
)


def test_positive_hard_cap_parsers_fail_closed() -> None:
    assert positive_float("25.5") == 25.5
    assert positive_float(0) is None
    assert positive_float(True) is None
    assert positive_float("invalid") is None

    assert positive_int("2") == 2
    assert positive_int(0) is None
    assert positive_int(True) is None

    assert positive_number("10.0") is True
    assert positive_number("-1") is False

    assert positive_integer("3") is True
    assert positive_integer("3.5") is False
    assert positive_integer(True) is False


def test_manual_value_requires_non_placeholder_content() -> None:
    assert (
        manual_value_filled("operator_1")
        is True
    )

    assert (
        manual_value_filled(
            "MANUAL_REQUIRED_OPERATOR_ID"
        )
        is False
    )

    assert manual_value_filled("") is False
    assert manual_value_filled(None) is False


def test_artifact_hash_prefers_embedded_evidence_hash() -> None:
    payload = {
        "phase6_3_report_sha256": "a" * 64,
        "status": "BLOCKED_REVIEW_ONLY",
    }

    assert artifact_hash(payload) == "a" * 64

    summary = source_summary(
        "readiness_gate",
        {
            **payload,
            "blocked": True,
            "fail_closed": True,
        },
    )

    assert summary["present"] is True
    assert summary["blocked"] is True
    assert summary["sha256"] == "a" * 64


def test_unsafe_flags_are_collected_by_artifact() -> None:
    unsafe = unsafe_flags_by_artifact(
        {
            "safe": {
                "testnet_order_submission_allowed": False,
            },
            "unsafe": {
                "testnet_order_submission_allowed": True,
                "place_order_enabled": True,
            },
        }
    )

    assert "safe" not in unsafe

    assert unsafe["unsafe"] == [
        "place_order_enabled",
        "testnet_order_submission_allowed",
    ]


def test_readiness_permission_state_is_complete_and_all_false() -> None:
    state = readiness_review_permission_state()

    assert state
    assert not any(state.values())

    assert (
        state["ready_for_signed_testnet_execution"]
        is False
    )

    assert (
        state["testnet_order_submission_allowed"]
        is False
    )

    assert (
        state["external_order_submission_allowed"]
        is False
    )

    assert state["place_order_enabled"] is False

    assert (
        state["signed_order_executor_enabled"]
        is False
    )

    assert (
        state["api_key_value_access_allowed"]
        is False
    )

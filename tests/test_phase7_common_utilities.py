from __future__ import annotations

from crypto_ai_system.governance.common import (
    artifact_hash,
    artifact_summary,
    bool_value,
    canonical_utc_value,
    forbidden_secret_fields,
    hex_fingerprint_valid,
    is_zero_number,
    number_value,
    placeholder_value,
    positive_integer_within,
    positive_number_within,
    review_only_permission_state,
    unsafe_flags_by_artifact,
    unsafe_true_fields,
)


def test_boolean_and_numeric_normalization() -> None:
    assert bool_value(True) is True
    assert bool_value("YES") is True
    assert bool_value("off") is False
    assert bool_value(None) is False

    assert number_value("25") == 25.0
    assert number_value(True) is None
    assert number_value("nan") is None
    assert number_value("inf") is None

    assert positive_number_within(25, 25) is True
    assert positive_number_within(25.1, 25) is False
    assert positive_number_within(0, 25) is False

    assert positive_integer_within(1, 1) is True
    assert positive_integer_within(1.5, 2) is False
    assert positive_integer_within(2, 1) is False

    assert is_zero_number(0) is True
    assert is_zero_number("0.0") is True
    assert is_zero_number(0.01) is False


def test_placeholder_utc_and_fingerprint_contracts() -> None:
    assert placeholder_value(
        "MANUAL_REQUIRED_OPERATOR_ID"
    ) is True

    assert placeholder_value(
        "operator_thomas"
    ) is False

    assert canonical_utc_value(
        "2026-07-14T00:00:00Z"
    ) is True

    assert canonical_utc_value(
        "2026-07-14T00:00:00+09:00"
    ) is False

    assert hex_fingerprint_valid(
        "0123456789abcdef" * 4
    ) is True

    assert hex_fingerprint_valid(
        "not-a-fingerprint"
    ) is False


def test_artifact_hash_prefers_embedded_hash_and_falls_back() -> None:
    embedded = {
        "phase7_14_report_sha256": "a" * 64,
        "value": 1,
    }

    assert (
        artifact_hash(
            embedded
        )
        == "a" * 64
    )

    fallback = artifact_hash(
        {
            "value": 1,
        }
    )

    assert isinstance(
        fallback,
        str,
    )

    assert len(
        fallback
    ) == 64

    summary = artifact_summary(
        "sample",
        {
            "status": "READY",
            "blocked": False,
            "fail_closed": False,
            "report_sha256": "b" * 64,
        },
    )

    assert (
        summary["sha256"]
        == "b" * 64
    )

    assert (
        summary["blocked"]
        is False
    )


def test_unsafe_and_secret_field_helpers_fail_closed() -> None:
    payload = {
        "testnet_order_submission_allowed": True,
        "signed_order_executor_enabled": False,
    }

    assert (
        unsafe_true_fields(
            payload
        )
        == [
            "testnet_order_submission_allowed"
        ]
    )

    assert (
        unsafe_flags_by_artifact(
            {
                "sample": payload,
            }
        )
        == {
            "sample": [
                "testnet_order_submission_allowed"
            ]
        }
    )

    assert (
        forbidden_secret_fields(
            {
                "api_secret_value": "forbidden",
                "api_secret_value_access_allowed": False,
                "metadata_only_key_fingerprint": "abc",
            }
        )
        == [
            "api_secret_value"
        ]
    )


def test_review_only_permission_state_is_all_false() -> None:
    permissions = (
        review_only_permission_state()
    )

    assert permissions

    assert not any(
        permissions.values()
    )

    for field in (
        "ready_for_signed_testnet_execution",
        "testnet_order_submission_allowed",
        "external_order_submission_allowed",
        "place_order_enabled",
        "cancel_order_enabled",
        "signed_order_executor_enabled",
        "phase8_execution_allowed",
        "phase8_write_path_allowed",
        "phase8_executor_enablement_allowed",
        "phase8_order_submission_allowed",
    ):
        assert (
            permissions[
                field
            ]
            is False
        )

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig
from crypto_ai_system.utils.audit import (
    is_canonical_utc_timestamp,
    sha256_json,
)

DEFAULT_UNSAFE_APPROVAL_FIELDS: tuple[str, ...] = (
    "runtime_permission_source",
    "approval_intake_validated",
    "approval_packet_created",
    "signed_testnet_unlock_allowed",
    "signed_testnet_unlock_authority",
    "phase7_execution_authority",
    "phase7_order_submission_authority",
    "signed_testnet_executor_enablement_authority",
    "signed_testnet_executor_approval_authority",
    "signed_testnet_reconciliation_authority",
    "signed_testnet_session_close_authority",
    "signed_testnet_execution_authority",
    "signed_testnet_order_submission_authority",
    "signed_testnet_promotion_authority",
    "executor_approval_runtime_authority",
    "executor_approval_authority",
    "executor_enablement_authority",
    "operator_decision_runtime_authority",
    "stage_transition_authority",
    "actual_operator_decision_recorded",
    "actual_stage_transition_performed",
    "actual_executor_approval_created",
    "actual_executor_enablement_performed",
    "actual_order_submission_performed",
    "actual_cancel_performed",
    "actual_reconciliation_authority",
    "actual_session_close_authority",
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
    "live_trading_allowed",
    "live_trading_allowed_by_this_module",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "exchange_endpoint_called",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
    "secret_value_accessed",
    "secret_file_read",
    "secret_file_created",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "auto_promotion_allowed",
)

DEFAULT_ARTIFACT_HASH_FIELDS: tuple[str, ...] = (
    "pre_executor_review_sha256",
    "final_pre_executor_review_packet_sha256",
    "operator_decision_intake_validation_sha256",
    "operator_decision_intake_template_sha256",
    "stage_transition_review_sha256",
    "executor_approval_review_sha256",
    "session_review_sha256",
    "executor_review_sha256",
    "phase7_14_report_sha256",
    "phase7_13_report_sha256",
    "phase7_12_report_sha256",
    "phase7_11_report_sha256",
    "phase7_10_report_sha256",
    "phase7_9_report_sha256",
    "phase7_8_report_sha256",
    "phase7_7_report_sha256",
    "phase7_6_report_sha256",
    "phase7_5_report_sha256",
    "phase7_4_report_sha256",
    "phase7_3_report_sha256",
    "phase7_2_report_sha256",
    "phase7_1_1_report_sha256",
    "phase7_1_report_sha256",
    "phase7_report_sha256",
    "future_executor_operator_decision_packet_sha256",
    "future_executor_operator_decision_guard_report_sha256",
    "future_executor_enablement_review_packet_sha256",
    "future_executor_enablement_review_guard_report_sha256",
    "future_executor_enablement_design_packet_sha256",
    "future_executor_enablement_design_guard_report_sha256",
    "future_executor_approval_review_packet_sha256",
    "future_executor_approval_intake_validation_sha256",
    "future_executor_approval_packet_template_sha256",
    "signed_testnet_execution_record_sha256",
    "signed_testnet_execution_enablement_packet_sha256",
    "signed_testnet_pre_submit_validation_sha256",
    "real_read_only_venue_probe_sha256",
    "testnet_secret_metadata_intake_sha256",
    "report_sha256",
)

DEFAULT_FORBIDDEN_SECRET_FIELD_FRAGMENTS: tuple[str, ...] = (
    "api_key_value",
    "api_secret_value",
    "private_key",
    "secret_value",
    "passphrase",
    "seed_phrase",
    "mnemonic",
)


def latest_dir(
    cfg: AppConfig,
) -> Path:
    raw = cfg.get(
        "storage.latest_dir",
        "storage/latest",
    )

    path = Path(
        raw
    )

    if not path.is_absolute():
        path = (
            cfg.root
            / path
        )

    path.mkdir(
        parents=True,
        exist_ok=True,
    )

    return path.resolve()


def storage_dir(
    cfg: AppConfig,
    relative_path: str | Path,
) -> Path:
    path = Path(
        relative_path
    )

    if not path.is_absolute():
        path = (
            cfg.root
            / path
        )

    path.mkdir(
        parents=True,
        exist_ok=True,
    )

    return path.resolve()


def read_latest_json(
    cfg: AppConfig,
    name: str,
    *,
    default: Mapping[
        str,
        Any,
    ] | None = None,
) -> dict[str, Any]:
    payload = read_json(
        latest_dir(
            cfg
        )
        / name,
        default=dict(
            default
            or {}
        ),
    )

    return (
        dict(
            payload
        )
        if isinstance(
            payload,
            Mapping,
        )
        else dict(
            default
            or {}
        )
    )


def read_optional_json(
    path: str | Path,
    *,
    default: Mapping[
        str,
        Any,
    ] | None = None,
) -> dict[str, Any]:
    payload = read_json(
        Path(
            path
        ),
        default=dict(
            default
            or {}
        ),
    )

    return (
        dict(
            payload
        )
        if isinstance(
            payload,
            Mapping,
        )
        else dict(
            default
            or {}
        )
    )


def safe_text(
    value: Any,
    default: str = "",
) -> str:
    text = str(
        value
        or ""
    ).strip()

    return (
        text
        if text
        else default
    )


def bool_value(
    value: Any,
) -> bool:
    if isinstance(
        value,
        bool,
    ):
        return value

    if value is None:
        return False

    return (
        str(
            value
        )
        .strip()
        .lower()
        in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }
    )


def number_value(
    value: Any,
) -> float | None:
    if isinstance(
        value,
        bool,
    ):
        return None

    try:
        parsed = float(
            value
        )

    except (
        TypeError,
        ValueError,
        OverflowError,
    ):
        return None

    return (
        parsed
        if math.isfinite(
            parsed
        )
        else None
    )


def positive_number_within(
    value: Any,
    maximum: float,
) -> bool:
    parsed = number_value(
        value
    )

    return (
        parsed
        is not None
        and parsed > 0
        and parsed
        <= float(
            maximum
        )
    )


def positive_integer_within(
    value: Any,
    maximum: int,
) -> bool:
    parsed = number_value(
        value
    )

    return (
        parsed
        is not None
        and parsed.is_integer()
        and parsed > 0
        and parsed
        <= int(
            maximum
        )
    )


def is_zero_number(
    value: Any,
    *,
    tolerance: float = 1e-12,
) -> bool:
    parsed = number_value(
        value
    )

    return (
        parsed
        is not None
        and abs(
            parsed
        )
        <= tolerance
    )


def placeholder_value(
    value: Any,
) -> bool:
    text = (
        safe_text(
            value
        )
        .upper()
    )

    return (
        not text
        or text.startswith(
            "MANUAL_REQUIRED"
        )
        or text.startswith(
            "PLACEHOLDER"
        )
        or text
        in {
            "TBD",
            "TODO",
            "NONE",
            "NULL",
        }
    )


def canonical_utc_value(
    value: Any,
) -> bool:
    text = safe_text(
        value
    )

    return (
        bool(
            text
        )
        and is_canonical_utc_timestamp(
            text
        )
    )


def hex_fingerprint_valid(
    value: Any,
    *,
    minimum_length: int = 16,
    maximum_length: int = 128,
) -> bool:
    text = (
        safe_text(
            value
        )
        .lower()
        .replace(
            ":",
            "",
        )
    )

    return (
        minimum_length
        <= len(
            text
        )
        <= maximum_length
        and all(
            character
            in "0123456789abcdef"
            for character in text
        )
    )


def hash_without(
    payload: Mapping[
        str,
        Any,
    ],
    hash_field: str,
) -> str:
    body = dict(
        payload
    )

    body.pop(
        hash_field,
        None,
    )

    return sha256_json(
        body
    )


def verify_embedded_hash(
    payload: Mapping[
        str,
        Any,
    ],
    hash_field: str,
) -> bool:
    expected = payload.get(
        hash_field
    )

    return (
        isinstance(
            expected,
            str,
        )
        and bool(
            expected
        )
        and hash_without(
            payload,
            hash_field,
        )
        == expected
    )


def artifact_hash(
    payload: Mapping[
        str,
        Any,
    ] | None,
    *,
    preferred_fields: Sequence[
        str
    ] = (),
    dynamic_name: str | None = None,
) -> str | None:
    data = dict(
        payload
        or {}
    )

    if not data:
        return None

    candidates: list[str] = []

    if dynamic_name:
        candidates.append(
            f"{dynamic_name}_sha256"
        )

    candidates.extend(
        str(
            field
        )
        for field in preferred_fields
    )

    candidates.extend(
        DEFAULT_ARTIFACT_HASH_FIELDS
    )

    for field in dict.fromkeys(
        candidates
    ):
        value = data.get(
            field
        )

        if value:
            return str(
                value
            )

    return sha256_json(
        data
    )


def artifact_summary(
    name: str,
    payload: Mapping[
        str,
        Any,
    ] | None,
    *,
    preferred_hash_fields: Sequence[
        str
    ] = (),
    include_block_state: bool = True,
) -> dict[str, Any]:
    data = dict(
        payload
        or {}
    )

    summary: dict[
        str,
        Any,
    ] = {
        "artifact_name": (
            name
        ),
        "present": bool(
            data
        ),
        "status": (
            data.get(
                "status"
            )
            or data.get(
                "packet_type"
            )
            or data.get(
                "guard_type"
            )
        ),
        "sha256": (
            artifact_hash(
                data,
                preferred_fields=(
                    preferred_hash_fields
                ),
                dynamic_name=(
                    name
                ),
            )
        ),
    }

    if include_block_state:
        summary.update(
            {
                "blocked": (
                    data.get(
                        "blocked"
                    )
                ),
                "fail_closed": (
                    data.get(
                        "fail_closed"
                    )
                ),
            }
        )

    return summary


def required_field_blockers(
    payload: Mapping[
        str,
        Any,
    ],
    fields: Sequence[
        str
    ],
    *,
    prefix: str = (
        "REQUIRED_FIELD_MISSING"
    ),
) -> list[str]:
    return sorted(
        {
            f"{prefix}:{field}"
            for field in fields
            if not safe_text(
                payload.get(
                    field
                )
            )
        }
    )


def canonical_utc_blockers(
    payload: Mapping[
        str,
        Any,
    ],
    field: str,
    *,
    blocker: str,
) -> list[str]:
    value = payload.get(
        field
    )

    if not value:
        return []

    return (
        []
        if canonical_utc_value(
            value
        )
        else [
            blocker
        ]
    )


def unsafe_true_fields(
    payload: Mapping[
        str,
        Any,
    ],
    *,
    fields: Sequence[
        str
    ] = DEFAULT_UNSAFE_APPROVAL_FIELDS,
) -> list[str]:
    return sorted(
        field
        for field in fields
        if bool_value(
            payload.get(
                field
            )
        )
    )


def unsafe_flags_by_artifact(
    artifacts: Mapping[
        str,
        Mapping[
            str,
            Any,
        ],
    ],
    *,
    fields: Sequence[
        str
    ] = DEFAULT_UNSAFE_APPROVAL_FIELDS,
) -> dict[str, list[str]]:
    return {
        str(
            name
        ): flags
        for (
            name,
            payload,
        ) in artifacts.items()
        if (
            flags := unsafe_true_fields(
                payload,
                fields=(
                    fields
                ),
            )
        )
    }


def unsafe_field_blockers(
    payload: Mapping[
        str,
        Any,
    ],
    *,
    fields: Sequence[
        str
    ] = DEFAULT_UNSAFE_APPROVAL_FIELDS,
    prefix: str = (
        "UNSAFE_FIELD_TRUE"
    ),
) -> list[str]:
    return [
        f"{prefix}:{field}"
        for field in unsafe_true_fields(
            payload,
            fields=(
                fields
            ),
        )
    ]


def forbidden_secret_fields(
    payload: Mapping[
        str,
        Any,
    ],
    *,
    fragments: Sequence[
        str
    ] = (
        DEFAULT_FORBIDDEN_SECRET_FIELD_FRAGMENTS
    ),
    allowed_false_fields: Sequence[
        str
    ] = (
        DEFAULT_UNSAFE_APPROVAL_FIELDS
    ),
) -> list[str]:
    allowed = set(
        str(
            field
        )
        for field in allowed_false_fields
    )

    findings: list[str] = []

    for (
        key,
        value,
    ) in payload.items():
        key_text = str(
            key
        )

        if (
            key_text
            in allowed
        ):
            continue

        if value in (
            None,
            "",
            False,
        ):
            continue

        lowered = (
            key_text.lower()
        )

        if any(
            str(
                fragment
            ).lower()
            in lowered
            for fragment in fragments
        ):
            findings.append(
                key_text
            )

    return sorted(
        set(
            findings
        )
    )


def expected_value_blockers(
    payload: Mapping[
        str,
        Any,
    ],
    expected_values: Mapping[
        str,
        Any,
    ],
    *,
    prefix: str = (
        "VALUE_MISMATCH"
    ),
) -> list[str]:
    blockers: list[str] = []

    for (
        field,
        expected,
    ) in expected_values.items():
        if (
            safe_text(
                payload.get(
                    field
                )
            )
            != safe_text(
                expected
            )
        ):
            blockers.append(
                f"{prefix}:{field}"
            )

    return sorted(
        set(
            blockers
        )
    )


def review_only_permission_state(
) -> dict[str, bool]:
    """Return the canonical governance-domain no-permission state."""

    return {
        field: False
        for field in dict.fromkeys(
            (
                *DEFAULT_UNSAFE_APPROVAL_FIELDS,
                "phase8_execution_allowed",
                "phase8_write_path_allowed",
                "phase8_secret_value_handling_allowed",
                "phase8_executor_enablement_allowed",
                "phase8_order_submission_allowed",
            )
        )
    }


def persist_report(
    *,
    cfg: AppConfig,
    latest_name: str,
    storage_relative_dir: str | Path,
    storage_name: str,
    payload: Mapping[
        str,
        Any,
    ],
) -> dict[str, Any]:
    output = dict(
        payload
    )

    atomic_write_json(
        latest_dir(
            cfg
        )
        / latest_name,
        output,
    )

    atomic_write_json(
        storage_dir(
            cfg,
            storage_relative_dir,
        )
        / storage_name,
        output,
    )

    return output


__all__ = [
    "DEFAULT_UNSAFE_APPROVAL_FIELDS",
    "DEFAULT_ARTIFACT_HASH_FIELDS",
    "DEFAULT_FORBIDDEN_SECRET_FIELD_FRAGMENTS",
    "latest_dir",
    "storage_dir",
    "read_latest_json",
    "read_optional_json",
    "safe_text",
    "bool_value",
    "number_value",
    "positive_number_within",
    "positive_integer_within",
    "is_zero_number",
    "placeholder_value",
    "canonical_utc_value",
    "hex_fingerprint_valid",
    "hash_without",
    "verify_embedded_hash",
    "artifact_hash",
    "artifact_summary",
    "required_field_blockers",
    "canonical_utc_blockers",
    "unsafe_true_fields",
    "unsafe_flags_by_artifact",
    "unsafe_field_blockers",
    "forbidden_secret_fields",
    "expected_value_blockers",
    "review_only_permission_state",
    "persist_report",
]

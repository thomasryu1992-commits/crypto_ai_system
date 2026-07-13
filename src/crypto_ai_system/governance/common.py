from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig
from crypto_ai_system.utils.audit import (
    is_canonical_utc_timestamp,
    sha256_json,
)

DEFAULT_UNSAFE_APPROVAL_FIELDS: tuple[str, ...] = (
    "signed_testnet_unlock_allowed",
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
    "live_trading_allowed",
    "live_trading_allowed_by_this_module",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "approval_packet_created",
    "approval_intake_validated",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
    "auto_promotion_allowed",
)


def latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def storage_dir(cfg: AppConfig, relative_path: str | Path) -> Path:
    path = Path(relative_path)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def read_latest_json(
    cfg: AppConfig,
    name: str,
    *,
    default: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = read_json(
        latest_dir(cfg) / name,
        default=dict(default or {}),
    )
    return (
        dict(payload)
        if isinstance(payload, Mapping)
        else dict(default or {})
    )


def safe_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


def hash_without(
    payload: Mapping[str, Any],
    hash_field: str,
) -> str:
    body = dict(payload)
    body.pop(hash_field, None)
    return sha256_json(body)


def verify_embedded_hash(
    payload: Mapping[str, Any],
    hash_field: str,
) -> bool:
    expected = payload.get(hash_field)
    return (
        isinstance(expected, str)
        and bool(expected)
        and hash_without(payload, hash_field) == expected
    )


def required_field_blockers(
    payload: Mapping[str, Any],
    fields: Sequence[str],
    *,
    prefix: str = "REQUIRED_FIELD_MISSING",
) -> list[str]:
    return sorted(
        {
            f"{prefix}:{field}"
            for field in fields
            if not safe_text(payload.get(field))
        }
    )


def canonical_utc_blockers(
    payload: Mapping[str, Any],
    field: str,
    *,
    blocker: str,
) -> list[str]:
    value = payload.get(field)
    if not value:
        return []
    return (
        []
        if is_canonical_utc_timestamp(str(value))
        else [blocker]
    )


def unsafe_true_fields(
    payload: Mapping[str, Any],
    *,
    fields: Sequence[str] = DEFAULT_UNSAFE_APPROVAL_FIELDS,
) -> list[str]:
    return sorted(
        field
        for field in fields
        if bool_value(payload.get(field))
    )


def unsafe_field_blockers(
    payload: Mapping[str, Any],
    *,
    fields: Sequence[str] = DEFAULT_UNSAFE_APPROVAL_FIELDS,
    prefix: str = "UNSAFE_FIELD_TRUE",
) -> list[str]:
    return [
        f"{prefix}:{field}"
        for field in unsafe_true_fields(payload, fields=fields)
    ]


def expected_value_blockers(
    payload: Mapping[str, Any],
    expected_values: Mapping[str, Any],
    *,
    prefix: str = "VALUE_MISMATCH",
) -> list[str]:
    blockers: list[str] = []
    for field, expected in expected_values.items():
        if safe_text(payload.get(field)) != safe_text(expected):
            blockers.append(f"{prefix}:{field}")
    return sorted(set(blockers))


def review_only_permission_state() -> dict[str, bool]:
    """Return the canonical approval-domain no-permission state."""

    return {
        "runtime_permission_source": False,
        "approval_intake_validated": False,
        "approval_packet_created": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "auto_promotion_allowed": False,
        "signed_testnet_unlock_allowed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
    }


def persist_report(
    *,
    cfg: AppConfig,
    latest_name: str,
    storage_relative_dir: str | Path,
    storage_name: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    output = dict(payload)
    atomic_write_json(latest_dir(cfg) / latest_name, output)
    atomic_write_json(
        storage_dir(cfg, storage_relative_dir) / storage_name,
        output,
    )
    return output


__all__ = [
    "DEFAULT_UNSAFE_APPROVAL_FIELDS",
    "latest_dir",
    "storage_dir",
    "read_latest_json",
    "safe_text",
    "bool_value",
    "hash_without",
    "verify_embedded_hash",
    "required_field_blockers",
    "canonical_utc_blockers",
    "unsafe_true_fields",
    "unsafe_field_blockers",
    "expected_value_blockers",
    "review_only_permission_state",
    "persist_report",
]

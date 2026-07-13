from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig
from crypto_ai_system.utils.audit import sha256_json

READINESS_UNSAFE_FIELDS: tuple[str, ...] = (
    "runtime_permission_source",
    "signed_testnet_unlock_authority",
    "phase7_execution_authority",
    "phase7_order_submission_authority",
    "approval_intake_validated",
    "operator_unlock_request_validated",
    "signed_testnet_preparation_ready",
    "signed_testnet_readiness_passed",
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
    "live_trading_allowed",
    "live_trading_allowed_by_this_module",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "auto_promotion_allowed",
)

ARTIFACT_HASH_FIELDS: tuple[str, ...] = (
    "phase5_report_sha256",
    "phase5_1_report_sha256",
    "phase5_2_report_sha256",
    "phase6_report_sha256",
    "phase6_1_report_sha256",
    "phase6_2_report_sha256",
    "phase6_3_report_sha256",
    "phase6_4_review_packet_sha256",
    "phase6_4_report_sha256",
    "phase6_5_report_sha256",
    "phase6_6_report_sha256",
    "signed_testnet_pre_submit_validation_sha256",
    "signed_testnet_execution_enablement_packet_sha256",
    "signed_testnet_execution_record_sha256",
    "real_read_only_venue_probe_sha256",
    "testnet_secret_metadata_intake_sha256",
    "report_sha256",
)


def latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)

    if not path.is_absolute():
        path = cfg.root / path

    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def storage_dir(
    cfg: AppConfig,
    relative_path: str | Path,
) -> Path:
    path = Path(relative_path)

    if not path.is_absolute():
        path = cfg.root / path

    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def readiness_review_storage_dir(
    cfg: AppConfig,
) -> Path:
    return storage_dir(
        cfg,
        "storage/governance/readiness",
    )


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


def read_optional_json(
    path: Path,
    *,
    default: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = read_json(
        path,
        default=dict(default or {}),
    )

    return (
        dict(payload)
        if isinstance(payload, Mapping)
        else dict(default or {})
    )


def safe_text(
    value: Any,
    default: str = "",
) -> str:
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


def positive_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None

    return parsed if parsed > 0 else None


def positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None

    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None

    return parsed if parsed > 0 else None


def positive_number(value: Any) -> bool:
    return positive_float(value) is not None


def positive_integer(value: Any) -> bool:
    if isinstance(value, bool):
        return False

    try:
        parsed_float = float(value)
        parsed_int = int(value)
    except (TypeError, ValueError, OverflowError):
        return False

    return parsed_int > 0 and parsed_int == parsed_float


def manual_value_filled(
    value: Any,
    *,
    placeholder_prefix: str = "MANUAL_REQUIRED",
) -> bool:
    text = safe_text(value)

    return (
        bool(text)
        and not text.startswith(placeholder_prefix)
    )


def artifact_hash(
    payload: Mapping[str, Any],
    *,
    hash_fields: Sequence[str] = ARTIFACT_HASH_FIELDS,
) -> str | None:
    data = dict(payload or {})

    if not data:
        return None

    for field in hash_fields:
        value = data.get(field)

        if value:
            return str(value)

    return sha256_json(data)


def preparation_artifact_summary(
    name: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    data = dict(payload or {})

    dynamic_hash = data.get(f"{name}_sha256")

    return {
        "artifact_name": name,
        "present": bool(data),
        "status": data.get("status"),
        "sha256": (
            str(dynamic_hash)
            if dynamic_hash
            else artifact_hash(data)
        ),
    }


def source_summary(
    name: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    data = dict(payload or {})

    return {
        "artifact_name": name,
        "present": bool(data),
        "status": data.get("status"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": artifact_hash(data),
    }


def unsafe_fields(
    payload: Mapping[str, Any],
    *,
    fields: Sequence[str] = READINESS_UNSAFE_FIELDS,
) -> list[str]:
    data = dict(payload or {})

    return sorted(
        field
        for field in fields
        if bool_value(data.get(field))
    )


def unsafe_flags_by_artifact(
    artifacts: Mapping[str, Mapping[str, Any]],
    *,
    fields: Sequence[str] = READINESS_UNSAFE_FIELDS,
) -> dict[str, list[str]]:
    unsafe: dict[str, list[str]] = {}

    for name, payload in artifacts.items():
        flags = unsafe_fields(
            payload,
            fields=fields,
        )

        if flags:
            unsafe[name] = flags

    return unsafe


def manual_file_summary(
    path: Path,
    *,
    fields: Sequence[str] = READINESS_UNSAFE_FIELDS,
) -> dict[str, Any]:
    payload = (
        read_optional_json(path)
        if path.exists()
        else {}
    )

    return {
        "path": str(path),
        "present": path.exists(),
        "sha256": (
            sha256_json(payload)
            if payload
            else None
        ),
        "unsafe_truthy_fields": unsafe_fields(
            payload,
            fields=fields,
        ),
        "field_count": len(payload),
        "payload_inspected_review_only": bool(payload),
    }


def readiness_review_permission_state() -> dict[str, bool]:
    return {
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "approval_intake_validated": False,
        "operator_unlock_request_validated": False,
        "signed_testnet_preparation_ready": False,
        "signed_testnet_readiness_passed": False,
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
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "auto_promotion_allowed": False,
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

    atomic_write_json(
        latest_dir(cfg) / latest_name,
        output,
    )

    atomic_write_json(
        storage_dir(
            cfg,
            storage_relative_dir,
        ) / storage_name,
        output,
    )

    return output


__all__ = [
    "READINESS_UNSAFE_FIELDS",
    "ARTIFACT_HASH_FIELDS",
    "latest_dir",
    "storage_dir",
    "readiness_review_storage_dir",
    "read_latest_json",
    "read_optional_json",
    "safe_text",
    "bool_value",
    "positive_float",
    "positive_int",
    "positive_number",
    "positive_integer",
    "manual_value_filled",
    "artifact_hash",
    "preparation_artifact_summary",
    "source_summary",
    "unsafe_fields",
    "unsafe_flags_by_artifact",
    "manual_file_summary",
    "readiness_review_permission_state",
    "persist_report",
]

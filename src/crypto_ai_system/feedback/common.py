from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig
from crypto_ai_system.utils.audit import sha256_file, sha256_json


def latest_dir(cfg: AppConfig) -> Path:
    """Return the canonical latest-artifact directory."""

    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def storage_dir(cfg: AppConfig, relative_path: str | Path) -> Path:
    """Return a repository-relative storage directory and create it."""

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
    """Read a JSON object from the canonical latest-artifact directory."""

    payload = read_json(latest_dir(cfg) / name, default=dict(default or {}))
    return dict(payload) if isinstance(payload, Mapping) else dict(default or {})


def hash_latest(cfg: AppConfig, name: str) -> str | None:
    """Hash a latest artifact when it exists."""

    path = latest_dir(cfg) / name
    return sha256_file(path) if path.exists() else None


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def text_value(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return default
    return text


def float_value(value: Any, default: float = 0.0) -> float:
    try:
        if value in {None, ""}:
            return default
        output = float(value)
        if math.isnan(output) or math.isinf(output):
            return default
        return output
    except (TypeError, ValueError, OverflowError):
        return default


def json_safe(value: Any) -> Any:
    """Convert nested values into deterministic JSON-safe primitives."""

    if isinstance(value, Mapping):
        return {str(key): json_safe(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [json_safe(child) for child in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None

    # Avoid importing pandas into the shared utility. Handle common NaN-like
    # scalar values without making pandas a dependency of this module.
    try:
        if value != value:
            return None
    except Exception:
        pass
    return value


def unsafe_true_flags(
    payload: Mapping[str, Any],
    fields: Sequence[str],
) -> list[str]:
    return sorted(field for field in fields if bool_value(payload.get(field)))


def seal_payload(payload: Mapping[str, Any], hash_field: str) -> dict[str, Any]:
    """Return a copied payload with a deterministic SHA-256 seal."""

    output = dict(payload)
    output.pop(hash_field, None)
    output[hash_field] = sha256_json(output)
    return output


def persist_report(
    *,
    cfg: AppConfig,
    latest_name: str,
    storage_relative_dir: str | Path,
    storage_name: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist one report to the canonical latest and domain storage paths."""

    output = dict(payload)
    atomic_write_json(latest_dir(cfg) / latest_name, output)
    atomic_write_json(
        storage_dir(cfg, storage_relative_dir) / storage_name,
        output,
    )
    return output


__all__ = [
    "latest_dir",
    "storage_dir",
    "read_latest_json",
    "hash_latest",
    "bool_value",
    "text_value",
    "float_value",
    "json_safe",
    "unsafe_true_flags",
    "seal_payload",
    "persist_report",
]

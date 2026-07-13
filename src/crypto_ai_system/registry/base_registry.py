from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.config import AppConfig
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical

REGISTRY_SCHEMA_VERSION = "step283_canonical_registry_v1"


class RegistryIntegrityError(RuntimeError):
    """Raised when an append-only registry is damaged or semantically invalid."""


def registry_root(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.registry_dir", "storage/registries")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def registry_path(cfg: AppConfig, registry_name: str) -> Path:
    safe = registry_name.strip().replace("/", "_").replace("\\", "_")
    if not safe.endswith(".jsonl"):
        safe = f"{safe}.jsonl"
    return registry_root(cfg) / safe


def _read_existing_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise RegistryIntegrityError(f"Damaged registry JSON at {path}:{lineno}: {exc}") from exc
            if not isinstance(payload, dict):
                raise RegistryIntegrityError(f"Damaged registry row at {path}:{lineno}: expected object")
            created = payload.get("created_at_utc")
            if created is not None and not is_canonical_utc_timestamp(created):
                raise RegistryIntegrityError(f"Invalid created_at_utc at {path}:{lineno}: {created!r}")
            records.append(payload)
    return records


def load_registry_records(path: str | Path) -> list[dict[str, Any]]:
    return _read_existing_records(Path(path))


def _with_registry_metadata(
    record: Mapping[str, Any],
    *,
    registry_name: str,
    id_field: str | None = None,
    hash_field: str | None = None,
    id_prefix: str | None = None,
) -> dict[str, Any]:
    payload = dict(record)
    payload.setdefault("registry_name", registry_name)
    payload.setdefault("registry_schema_version", REGISTRY_SCHEMA_VERSION)
    payload.setdefault("created_at_utc", utc_now_canonical())
    if not is_canonical_utc_timestamp(payload["created_at_utc"]):
        raise RegistryIntegrityError(f"Registry record has non-canonical created_at_utc: {payload['created_at_utc']!r}")

    if id_field and not payload.get(id_field):
        payload[id_field] = stable_id(id_prefix or id_field.replace("_id", ""), payload, 24)

    if hash_field:
        without_hash = {k: v for k, v in payload.items() if k != hash_field}
        payload[hash_field] = sha256_json(without_hash)
    return payload


def append_registry_record(
    path: str | Path,
    record: Mapping[str, Any],
    *,
    registry_name: str,
    id_field: str | None = None,
    hash_field: str | None = None,
    id_prefix: str | None = None,
) -> dict[str, Any]:
    """Append a validated record to a canonical registry.

    Missing registry files may be created. Damaged existing registry files fail
    closed and are never silently regenerated.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _read_existing_records(target)
    payload = _with_registry_metadata(
        record,
        registry_name=registry_name,
        id_field=id_field,
        hash_field=hash_field,
        id_prefix=id_prefix,
    )
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    return payload


def append_registry_records(
    path: str | Path,
    records: list[Mapping[str, Any]],
    *,
    registry_name: str,
    id_field: str | None = None,
    hash_field: str | None = None,
    id_prefix: str | None = None,
) -> list[dict[str, Any]]:
    """Append multiple validated records after a single integrity scan.

    This preserves the append-only registry contract while avoiding repeated full-file
    scans during paper outcome batch accumulation. Damaged existing registries still
    fail closed before any new row is appended.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _read_existing_records(target)
    payloads = [
        _with_registry_metadata(
            record,
            registry_name=registry_name,
            id_field=id_field,
            hash_field=hash_field,
            id_prefix=id_prefix,
        )
        for record in records
    ]
    with target.open("a", encoding="utf-8") as handle:
        for payload in payloads:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    return payloads

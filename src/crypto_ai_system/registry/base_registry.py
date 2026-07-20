from __future__ import annotations

import json
import os
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


_TAIL_PROBE_BYTES = 65536  # registry rows are ~1-2KB; 64KB always covers the last line


def _validate_tail(path: Path) -> None:
    """O(1) integrity check at the append site.

    Appends can only tear the LAST line (a crash mid-write), so the append path
    checks exactly that — the trailing newline and the last line's JSON — and
    stays O(1) instead of re-parsing the whole file per append (the
    performance-report registry alone is tens of MB). Full-file validation
    still happens on every ``load_registry_records`` read. Same fail-closed
    contract: damage raises, nothing is silently regenerated.
    """
    if not path.exists():
        return
    size = path.stat().st_size
    if size == 0:
        return
    with path.open("rb") as handle:
        handle.seek(max(0, size - _TAIL_PROBE_BYTES))
        chunk = handle.read()
    if not chunk.endswith(b"\n"):
        raise RegistryIntegrityError(
            f"Torn tail in {path}: last append did not complete (no trailing newline)"
        )
    lines = [ln for ln in chunk.split(b"\n") if ln.strip()]
    if not lines:
        return
    try:
        payload = json.loads(lines[-1].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegistryIntegrityError(f"Damaged registry tail in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RegistryIntegrityError(f"Damaged registry tail in {path}: expected object")


def rotate_registry_if_large(path: str | Path, *, max_bytes: int) -> Path | None:
    """Archive an oversized registry so appends start a fresh file.

    ONLY for write-only audit registries whose consumers read the separately
    persisted latest record — NEVER for a registry whose full history is a
    runtime input (outcome_feedback_registry feeds the risk limits). The
    archive keeps the full history on disk under a timestamped sibling name.
    """
    target = Path(path)
    if not target.exists() or target.stat().st_size < max_bytes:
        return None
    stamp = utc_now_canonical().replace(":", "").replace("-", "")
    archive = target.with_name(f"{target.stem}.{stamp}.rotated.jsonl")
    target.rename(archive)
    return archive


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
    _validate_tail(target)
    payload = _with_registry_metadata(
        record,
        registry_name=registry_name,
        id_field=id_field,
        hash_field=hash_field,
        id_prefix=id_prefix,
    )
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str) + "\n"
    with target.open("a", encoding="utf-8") as handle:
        # One write call + fsync narrows the torn-line window to the OS level.
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
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
    _validate_tail(target)
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
        handle.flush()
        os.fsync(handle.fileno())
    return payloads

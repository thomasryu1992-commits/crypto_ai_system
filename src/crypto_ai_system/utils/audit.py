from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

_CANONICAL_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def utc_now_canonical() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_canonical_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not _CANONICAL_UTC_RE.match(value):
        return False
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ") == value


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_json(value: Any) -> str:
    return sha256_text(canonical_json(value))


def sha256_file(path: str | Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def stable_id(prefix: str, payload: Mapping[str, Any], length: int = 24) -> str:
    return f"{prefix}_{sha256_json(payload)[:length]}"


def file_metadata(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"path": str(p), "exists": False, "sha256": None, "bytes": None}
    data = p.read_bytes()
    return {"path": str(p), "exists": True, "sha256": sha256_bytes(data), "bytes": len(data)}

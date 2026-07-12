from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from core.json_io import atomic_write_json, read_json
except Exception:  # pragma: no cover - compatibility fallback
    import json
    import os
    import tempfile

    def read_json(path: str | Path, default: Any = None) -> Any:
        path = Path(path)
        if not path.exists():
            return default
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return default

    def atomic_write_json(path: str | Path, data: Any) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2, default=str)
                handle.write("\n")
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)


def write_latest(path: str | Path, payload: Any) -> Path:
    target = Path(path)
    atomic_write_json(target, payload)
    return target


def read_latest(path: str | Path, default: Any = None) -> Any:
    return read_json(path, default=default)


__all__ = ["write_latest", "read_latest"]

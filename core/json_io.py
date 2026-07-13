from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def read_json(path: str | Path, default: Any = None) -> Any:
    path = Path(path)
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return default


def atomic_write_json(path: str | Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False, default=str)
            file.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def append_jsonl(path: str | Path, row: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists() and path.is_dir():
        raise PermissionError(f"JSONL target is a directory, not a file: {path}")

    try:
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        return
    except PermissionError:
        # Windows ZIP extraction or editor locks can leave files read-only.
        # Try clearing the write bit once, then retry.
        try:
            import stat
            if path.exists():
                path.chmod(path.stat().st_mode | stat.S_IWRITE)
            with path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            return
        except Exception:
            raise


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


# Backward-compatible helpers for legacy Step1~150 modules.
def _storage_latest_dir() -> Path:
    try:
        from config.settings import LATEST_DIR
        return Path(LATEST_DIR)
    except Exception:
        return Path("storage") / "latest"


def read_storage_json(filename: str | Path, default: Any = None) -> Any:
    path = Path(filename)
    if not path.is_absolute():
        path = _storage_latest_dir() / path
    return read_json(path, default=default)


def write_storage_json(filename: str | Path, data: Any) -> None:
    path = Path(filename)
    if not path.is_absolute():
        path = _storage_latest_dir() / path
    atomic_write_json(path, data)

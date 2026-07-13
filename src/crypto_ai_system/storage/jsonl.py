from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from core.json_io import append_jsonl as _append_jsonl, read_jsonl as _read_jsonl
except Exception:  # pragma: no cover - compatibility fallback
    import json

    def _append_jsonl(path: str | Path, row: dict[str, Any]) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
        path = Path(path)
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows


def append_jsonl(path: str | Path, row: dict[str, Any]) -> None:
    """Append a JSONL row using the canonical core helper.

    Compatibility wrapper only; it does not add runtime authority.
    """
    _append_jsonl(path, row)


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return _read_jsonl(path)


__all__ = ["append_jsonl", "read_jsonl"]

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def ensure_parent(path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def write_json(path: str | Path, data: Dict[str, Any]) -> str:
    p = ensure_parent(path)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(p.resolve())


def read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))

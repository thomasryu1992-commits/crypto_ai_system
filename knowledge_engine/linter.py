from __future__ import annotations

from pathlib import Path


def lint_knowledge_base() -> dict:
    kb = Path("knowledge_base")
    return {"status": "OK" if kb.exists() else "MISSING", "path": str(kb)}

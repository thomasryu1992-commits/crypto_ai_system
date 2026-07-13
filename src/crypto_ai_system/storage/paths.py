from __future__ import annotations

from pathlib import Path
from typing import Any

from crypto_ai_system.config import AppConfig, load_config


def _root(cfg: AppConfig | None = None) -> Path:
    cfg = cfg or load_config()
    return Path(cfg.root).resolve()


def ensure_storage_dirs(cfg: AppConfig | None = None) -> dict[str, Path]:
    root = _root(cfg)
    storage_root = root / "storage"
    paths = {
        "storage": storage_root,
        "raw": storage_root / "raw",
        "features": storage_root / "features",
        "latest": storage_root / "latest",
        "logs": storage_root / "logs",
        "backup": storage_root / "backup",
        "signals": storage_root / "signals",
        "spreadsheet_backup": storage_root / "spreadsheet_backup",
        "registries": storage_root / "registries",
        "review_packets": storage_root / "review_packets",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


__all__ = ["ensure_storage_dirs"]

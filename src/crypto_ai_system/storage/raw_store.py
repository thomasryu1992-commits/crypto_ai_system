from __future__ import annotations

from pathlib import Path
from typing import Mapping

import pandas as pd

from crypto_ai_system.config import AppConfig
from crypto_ai_system.storage.paths import ensure_storage_dirs


def store_raw_bundle(cfg: AppConfig, frames: Mapping[str, pd.DataFrame]) -> dict[str, str]:
    """Persist raw frames under storage/raw and return logical source file paths.

    Compatibility wrapper only; it does not validate data as live eligible.
    """
    paths = ensure_storage_dirs(cfg)
    raw_dir: Path = paths["raw"]
    written: dict[str, str] = {}
    for name, frame in frames.items():
        safe_name = str(name).replace("/", "_").replace("\\", "_")
        target = raw_dir / f"{safe_name}.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(target, index=False)
        written[str(name)] = str(target)
    return written


__all__ = ["store_raw_bundle"]

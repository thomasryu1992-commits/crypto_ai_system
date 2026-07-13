from __future__ import annotations

from pathlib import Path
from typing import Mapping

import pandas as pd

from crypto_ai_system.config import AppConfig
from crypto_ai_system.storage.paths import ensure_storage_dirs


def store_normalized_frames(cfg: AppConfig, frames: Mapping[str, pd.DataFrame]) -> dict[str, str]:
    """Persist normalized/feature frames under storage/features.

    Compatibility wrapper only; it does not create execution permission.
    """
    paths = ensure_storage_dirs(cfg)
    features_dir: Path = paths["features"]
    written: dict[str, str] = {}
    for name, frame in frames.items():
        safe_name = str(name).replace("/", "_").replace("\\", "_")
        target = features_dir / f"{safe_name}.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(target, index=False)
        written[str(name)] = str(target)
    return written


__all__ = ["store_normalized_frames"]

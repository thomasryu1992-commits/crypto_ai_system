from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def append_df_csv(path: str | Path, frame: pd.DataFrame, *, dedup_subset: list[str] | tuple[str, ...] | None = None) -> Path:
    """Append a DataFrame to CSV, optionally de-duplicating by columns.

    Compatibility wrapper for legacy collectors. This only writes local artifact data
    and never grants runtime/execution permission.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if dedup_subset and target.exists() and target.stat().st_size > 0:
        existing = pd.read_csv(target)
        combined = pd.concat([existing, frame], ignore_index=True)
        valid_subset = [column for column in dedup_subset if column in combined.columns]
        if valid_subset:
            combined = combined.drop_duplicates(subset=valid_subset, keep="last")
        else:
            combined = combined.drop_duplicates(keep="last")
        combined.to_csv(target, index=False)
        return target

    write_header = not target.exists() or target.stat().st_size == 0
    frame.to_csv(target, mode="a", header=write_header, index=False)
    return target


def write_df_csv(path: str | Path, frame: pd.DataFrame) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False)
    return target


__all__ = ["append_df_csv", "write_df_csv"]

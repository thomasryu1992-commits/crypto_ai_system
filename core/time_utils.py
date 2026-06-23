from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

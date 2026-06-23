from __future__ import annotations

from typing import Any

from config.settings import EVENT_LOG_PATH
from core.json_io import append_jsonl
from core.time_utils import utc_now_iso


def log_event(event_type: str, payload: dict[str, Any] | None = None, severity: str = "INFO") -> dict[str, Any]:
    row = {
        "timestamp": utc_now_iso(),
        "event_type": event_type,
        "severity": severity,
        "payload": payload or {},
    }
    append_jsonl(EVENT_LOG_PATH, row)
    return row

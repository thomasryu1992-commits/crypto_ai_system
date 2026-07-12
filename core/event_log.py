from __future__ import annotations

from pathlib import Path
from typing import Any

from config.settings import EVENT_LOG_PATH
from core.json_io import append_jsonl
from core.time_utils import utc_now_iso


def _fallback_event_log_path() -> Path:
    path = Path(EVENT_LOG_PATH)
    return path.parent / "event_log_fallback.jsonl"


def log_event(event_type: str, payload: dict[str, Any] | None = None, severity: str = "INFO") -> dict[str, Any]:
    """Append an event-log row without breaking the trading/research pipeline.

    Event logging is operational telemetry. A Windows read-only attribute,
    locked file, or accidentally-created directory must not crash the main
    dry-run/research/trading cycle. When the primary event log cannot be
    written, this function attempts a fallback file and then returns the row.
    """
    row = {
        "timestamp": utc_now_iso(),
        "event_type": event_type,
        "severity": severity,
        "payload": payload or {},
    }
    try:
        append_jsonl(EVENT_LOG_PATH, row)
    except PermissionError:
        try:
            append_jsonl(_fallback_event_log_path(), {**row, "log_warning": "primary_event_log_permission_denied"})
        except Exception:
            pass
    except Exception:
        try:
            append_jsonl(_fallback_event_log_path(), {**row, "log_warning": "primary_event_log_write_failed"})
        except Exception:
            pass
    return row

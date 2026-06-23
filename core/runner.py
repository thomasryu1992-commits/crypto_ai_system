from __future__ import annotations

from typing import Any, Callable

from core.console import configure_utf8_console, safe_print
from core.time_utils import utc_now_iso


def run_step(name: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    configure_utf8_console()
    safe_print(f"\n=== {name} ===")
    started_at = utc_now_iso()
    result = fn(*args, **kwargs)
    safe_print(f"{name}: completed at {utc_now_iso()} / started at {started_at}")
    return result

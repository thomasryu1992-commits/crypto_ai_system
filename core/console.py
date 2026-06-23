from __future__ import annotations

import sys
from typing import Any


def configure_utf8_console() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def safe_print(*values: Any, sep: str = " ", end: str = "\n") -> None:
    text = sep.join(str(v) for v in values)
    try:
        print(text, end=end)
    except UnicodeEncodeError:
        print(text.encode("utf-8", errors="replace").decode("utf-8"), end=end)

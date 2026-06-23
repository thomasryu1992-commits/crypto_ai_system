import sys
from typing import Any


def configure_utf8_console() -> None:
    """
    Prevent Windows cp949 console crashes when printing emoji or non-ASCII text.
    Safe to call on non-Windows platforms as well.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def safe_print(value: Any = "") -> None:
    """
    Print text without allowing UnicodeEncodeError to terminate the program.
    """
    text = "" if value is None else str(value)

    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe_text = text.encode(encoding, errors="backslashreplace").decode(
            encoding,
            errors="replace",
        )
        print(safe_text)

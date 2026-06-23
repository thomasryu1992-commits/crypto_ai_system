from __future__ import annotations

from pathlib import Path

from config.settings import settings
from core.console import configure_utf8_console, safe_print


def main() -> None:
    configure_utf8_console()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    removed = 0
    for path in settings.storage_dir.glob("*.json"):
        path.unlink()
        removed += 1
    for path in settings.storage_dir.glob("*.csv"):
        path.unlink()
        removed += 1
    safe_print(f"Storage reset completed. Removed files: {removed}")


if __name__ == "__main__":
    main()

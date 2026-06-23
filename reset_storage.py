from __future__ import annotations

import shutil
from pathlib import Path
from config.settings import Settings, ensure_storage_dirs
from core.console import configure_utf8_console, safe_print

configure_utf8_console()


def main() -> None:
    storage = Path(Settings.STORAGE_DIR)
    if storage.exists():
        shutil.rmtree(storage)
    ensure_storage_dirs()
    safe_print(f"Storage reset completed: {storage.resolve()}")


if __name__ == "__main__":
    main()

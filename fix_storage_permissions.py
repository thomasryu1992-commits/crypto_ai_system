from __future__ import annotations

import os
import stat
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STORAGE = ROOT / "storage"
REQUIRED_DIRS = [
    STORAGE,
    STORAGE / "latest",
    STORAGE / "logs",
    STORAGE / "backup",
    STORAGE / "backup" / "spreadsheet",
    STORAGE / "queue",
    STORAGE / "dead_letter",
    STORAGE / "backtest",
    STORAGE / "reports",
]
REQUIRED_FILES = [
    STORAGE / "logs" / "event_log.jsonl",
    STORAGE / "logs" / "forward_test_log.jsonl",
]


def make_writeable(path: Path) -> None:
    try:
        if path.exists():
            path.chmod(path.stat().st_mode | stat.S_IWRITE)
    except Exception:
        pass


def ensure_dir(path: Path) -> None:
    if path.exists() and path.is_file():
        backup = path.with_name(path.name + f".file_backup_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")
        path.rename(backup)
        print(f"RENAMED_FILE_BLOCKING_DIR: {path} -> {backup}")
    path.mkdir(parents=True, exist_ok=True)
    make_writeable(path)


def ensure_file(path: Path) -> None:
    ensure_dir(path.parent)
    if path.exists() and path.is_dir():
        backup = path.with_name(path.name + f".dir_backup_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")
        path.rename(backup)
        print(f"RENAMED_DIR_BLOCKING_FILE: {path} -> {backup}")
    if not path.exists():
        path.write_text("", encoding="utf-8")
        print(f"CREATED_FILE: {path}")
    make_writeable(path)


def main() -> None:
    for directory in REQUIRED_DIRS:
        ensure_dir(directory)
    for file_path in REQUIRED_FILES:
        ensure_file(file_path)

    for path in STORAGE.rglob("*"):
        make_writeable(path)

    print("Storage permission check complete.")
    print(f"Event log: {STORAGE / 'logs' / 'event_log.jsonl'}")


if __name__ == "__main__":
    main()

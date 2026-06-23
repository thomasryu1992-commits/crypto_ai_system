from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from config.settings import SPREADSHEET_LOCAL_BACKUP_DIR
from integrations.spreadsheet_schema import get_schema


def append_local_csv(tab: str, row: dict[str, Any]) -> str:
    SPREADSHEET_LOCAL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = SPREADSHEET_LOCAL_BACKUP_DIR / f"{tab}.csv"
    columns = get_schema(tab)
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        if not exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in columns})
    return str(path)

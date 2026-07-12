from pathlib import Path

import pandas as pd

from crypto_ai_system.storage.csv_backup import append_df_csv
from crypto_ai_system.storage.jsonl import append_jsonl, read_jsonl
from crypto_ai_system.storage.latest import read_latest, write_latest


def test_storage_compat_wrappers_write_local_artifacts(tmp_path: Path):
    jsonl_path = tmp_path / "logs" / "events.jsonl"
    append_jsonl(jsonl_path, {"type": "smoke", "order_endpoint_called": False})
    assert read_jsonl(jsonl_path)[0]["type"] == "smoke"

    latest_path = tmp_path / "latest" / "payload.json"
    write_latest(latest_path, {"review_only": True, "execution_permission_granted": False})
    assert read_latest(latest_path)["review_only"] is True

    csv_path = tmp_path / "backup" / "rows.csv"
    append_df_csv(csv_path, pd.DataFrame([{"a": 1}]))
    append_df_csv(csv_path, pd.DataFrame([{"a": 2}]))
    assert csv_path.read_text(encoding="utf-8").strip().splitlines() == ["a", "1", "2"]

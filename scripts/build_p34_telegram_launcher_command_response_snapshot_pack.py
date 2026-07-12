from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.telegram_launcher_command_response_snapshot_pack import persist_telegram_launcher_command_response_snapshot_pack


def main() -> int:
    cfg = load_config(Path.cwd())
    report = persist_telegram_launcher_command_response_snapshot_pack(cfg)
    print(report["status"])
    print(report["p34_telegram_launcher_command_response_snapshot_pack_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.telegram_launcher_command_response_snapshot_pack import persist_telegram_launcher_command_response_snapshot_pack


def main() -> int:
    parser = argparse.ArgumentParser(description="Build P34 Telegram/Launcher command response snapshot pack artifacts.")
    parser.add_argument("--print-telegram", action="store_true")
    parser.add_argument("--print-launcher", action="store_true")
    parser.add_argument("--print-markdown", action="store_true")
    parser.add_argument("--print-text", action="store_true")
    parser.add_argument("--print-pack", action="store_true")
    args = parser.parse_args()
    cfg = load_config(Path.cwd())
    report = persist_telegram_launcher_command_response_snapshot_pack(cfg)
    latest = cfg.root / cfg.get("storage.latest_dir", "storage/latest")
    if args.print_telegram:
        print(json.dumps(read_json(latest / "p34_telegram_command_response_snapshots.json"), indent=2, sort_keys=True))
    elif args.print_launcher:
        print(json.dumps(read_json(latest / "p34_launcher_command_response_snapshots.json"), indent=2, sort_keys=True))
    elif args.print_markdown:
        print((latest / "p34_command_response_snapshot_pack.md").read_text(encoding="utf-8"))
    elif args.print_text:
        print((latest / "p34_command_response_snapshot_pack.txt").read_text(encoding="utf-8"))
    elif args.print_pack:
        print(json.dumps(read_json(latest / "p34_command_response_snapshot_pack.json"), indent=2, sort_keys=True))
    else:
        print(report["status"])
        print("telegram_snapshot_count=", report["telegram_snapshot_count"])
        print("launcher_snapshot_count=", report["launcher_snapshot_count"])
        print("live_scaled_execution_enabled=", report["live_scaled_execution_enabled"])
        print("runtime_scheduler_enabled=", report["runtime_scheduler_enabled"])
        print("live_order_submission_allowed=", report["live_order_submission_allowed"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.telegram_launcher_command_router_fixture_validator import persist_telegram_launcher_command_router_fixture_validator


def main() -> int:
    parser = argparse.ArgumentParser(description="Build P33 Telegram/Launcher command router fixture validator artifacts.")
    parser.add_argument("--print-contract", action="store_true")
    parser.add_argument("--print-telegram-router", action="store_true")
    parser.add_argument("--print-launcher-router", action="store_true")
    parser.add_argument("--print-validation", action="store_true")
    args = parser.parse_args()
    cfg = load_config(Path.cwd())
    report = persist_telegram_launcher_command_router_fixture_validator(cfg)
    latest = cfg.root / cfg.get("storage.latest_dir", "storage/latest")
    if args.print_contract:
        print(json.dumps(read_json(latest / "p33_telegram_launcher_command_router_contract.json"), indent=2, sort_keys=True))
    elif args.print_telegram_router:
        print(json.dumps(read_json(latest / "p33_telegram_command_router_fixture.json"), indent=2, sort_keys=True))
    elif args.print_launcher_router:
        print(json.dumps(read_json(latest / "p33_launcher_command_router_fixture.json"), indent=2, sort_keys=True))
    elif args.print_validation:
        print(json.dumps(read_json(latest / "p33_command_router_fixture_validation_results.json"), indent=2, sort_keys=True))
    else:
        print(report["status"])
        print("router_command_executes_runtime=false")
        print("router_command_allows_order_submission=false")
        print("runtime_scheduler_enabled=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

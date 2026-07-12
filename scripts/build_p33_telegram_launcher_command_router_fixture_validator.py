from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.telegram_launcher_command_router_fixture_validator import persist_telegram_launcher_command_router_fixture_validator


def main() -> int:
    report = persist_telegram_launcher_command_router_fixture_validator(load_config(Path.cwd()))
    print(report["status"])
    print(report["p33_telegram_launcher_command_router_fixture_validator_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

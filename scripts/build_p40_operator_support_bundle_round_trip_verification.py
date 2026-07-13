from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_support_bundle_round_trip_verification import persist_operator_support_bundle_round_trip_verification


if __name__ == "__main__":
    report = persist_operator_support_bundle_round_trip_verification(load_config(Path.cwd()))
    print(report["status"])

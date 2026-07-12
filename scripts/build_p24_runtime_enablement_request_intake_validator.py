from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.runtime_enablement_request_intake_validator import persist_runtime_enablement_request_intake_validator


def main() -> None:
    cfg = load_config(Path.cwd())
    report = persist_runtime_enablement_request_intake_validator(cfg)
    print(report["status"])
    print(report["p24_runtime_enablement_request_intake_validator_sha256"])


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.runtime_enablement_request_intake_validator import persist_runtime_enablement_request_intake_validator


def main() -> None:
    parser = argparse.ArgumentParser(description="Run P24 runtime enablement request intake validator.")
    parser.add_argument("--print-template", action="store_true", help="Print the generated P24 intake template path and contents.")
    args = parser.parse_args()
    cfg = load_config(Path.cwd())
    report = persist_runtime_enablement_request_intake_validator(cfg)
    print(report["status"])
    print(report["p24_runtime_enablement_request_intake_validator_sha256"])
    if args.print_template:
        latest = cfg.root / cfg.get("storage.latest_dir", "storage/latest")
        template_path = latest / "p24_runtime_enablement_request_intake_TEMPLATE.json"
        print(template_path)
        print(read_json(template_path, default={}))


if __name__ == "__main__":
    main()

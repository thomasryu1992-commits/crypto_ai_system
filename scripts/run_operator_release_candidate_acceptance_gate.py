from __future__ import annotations

import argparse
from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_release_candidate_acceptance_review import (
    build_operator_release_candidate_acceptance_intake_template,
    persist_operator_release_candidate_acceptance_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run P22 operator release candidate acceptance review gate.")
    parser.add_argument("--print-template", action="store_true", help="Print/write the P22 operator acceptance intake template only.")
    args = parser.parse_args()
    cfg = load_config(Path.cwd())
    latest = cfg.root / cfg.get("storage.latest_dir", "storage/latest")
    latest.mkdir(parents=True, exist_ok=True)
    if args.print_template:
        template = build_operator_release_candidate_acceptance_intake_template()
        atomic_write_json(latest / "p22_operator_release_candidate_acceptance_intake_TEMPLATE.json", template)
        print("storage/latest/p22_operator_release_candidate_acceptance_intake_TEMPLATE.json")
        return
    report = persist_operator_release_candidate_acceptance_review(cfg)
    print(report["status"])
    print(f"release_candidate_accepted_review_only={str(report['release_candidate_accepted_review_only']).lower()}")
    print(f"live_scaled_execution_enabled={str(report['live_scaled_execution_enabled']).lower()}")
    print(f"runtime_scheduler_enabled={str(report['runtime_scheduler_enabled']).lower()}")


if __name__ == "__main__":
    main()

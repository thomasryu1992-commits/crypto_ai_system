from __future__ import annotations

import argparse
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.docker_launcher_evidence_intake import (
    STATUS_BLOCKED_FAIL_CLOSED,
    build_docker_build_external_evidence_template,
    build_docker_run_external_evidence_template,
    build_launcher_import_external_evidence_template,
    persist_docker_launcher_evidence_intake,
)
from core.json_io import read_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate external Docker build/run and Launcher import evidence without enabling runtime execution.")
    parser.add_argument("--print-templates", action="store_true", help="Print example external evidence templates using the current P18 hash.")
    args = parser.parse_args()
    cfg = load_config(Path.cwd())
    if args.print_templates:
        latest = cfg.root / cfg.get("storage.latest_dir", "storage/latest")
        p18_summary = read_json(latest / "p18_full_regression_ci_release_gate_summary.json", default={})
        p18_hash = p18_summary.get("p18_full_regression_ci_release_gate_sha256", "0" * 64)
        print("docker_build_template", build_docker_build_external_evidence_template(p18_hash))
        print("docker_run_template", build_docker_run_external_evidence_template(p18_hash))
        print("launcher_import_template", build_launcher_import_external_evidence_template(p18_hash))
        return 0
    report = persist_docker_launcher_evidence_intake(cfg=cfg)
    print(report["status"])
    print(report["p19_docker_launcher_evidence_intake_sha256"])
    print("limited_live_scaled_auto_trading_allowed=false")
    print("live_scaled_execution_enabled=false")
    print("live_order_submission_allowed=false")
    print("runtime_scheduler_enabled=false")
    return 1 if report["status"] == STATUS_BLOCKED_FAIL_CLOSED else 0


if __name__ == "__main__":
    raise SystemExit(main())

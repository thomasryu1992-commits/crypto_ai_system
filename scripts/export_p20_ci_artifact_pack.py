from __future__ import annotations

import argparse
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.external_evidence_template_export_pack import persist_external_evidence_template_export_pack


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate P20 external evidence templates and CI artifact export pack without executing Docker, Launcher, or trading runtime.")
    parser.add_argument("--print-paths", action="store_true", help="Print generated template and export pack paths.")
    args = parser.parse_args()
    cfg = load_config(Path.cwd())
    report = persist_external_evidence_template_export_pack(cfg=cfg)
    print(report["status"])
    print(report["p20_external_evidence_template_export_pack_sha256"])
    print("limited_live_scaled_auto_trading_allowed=false")
    print("live_scaled_execution_enabled=false")
    print("runtime_scheduler_enabled=false")
    if args.print_paths:
        for filename in report["template_files"]:
            print(f"template: storage/latest/{filename}")
        print("manifest: storage/latest/p20_ci_artifact_export_manifest.json")
        print("zip: storage/latest/p20_ci_artifact_export_pack_review_only.zip")
    return 1 if report["blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

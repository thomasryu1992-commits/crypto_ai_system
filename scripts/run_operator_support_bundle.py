from __future__ import annotations

import argparse
from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.operator_support_bundle_troubleshooting_export_pack import persist_operator_support_bundle


def _latest_path(filename: str) -> Path:
    cfg = load_config(Path.cwd())
    latest = Path(cfg.get("storage.latest_dir", "storage/latest"))
    if not latest.is_absolute():
        latest = cfg.root / latest
    return latest / filename


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate P38 operator support bundle / troubleshooting export pack.")
    parser.add_argument("--print-markdown", action="store_true")
    parser.add_argument("--print-share-packet", action="store_true")
    parser.add_argument("--print-manifest", action="store_true")
    parser.add_argument("--print-paths", action="store_true")
    args = parser.parse_args()

    report = persist_operator_support_bundle(load_config(Path.cwd()))
    if args.print_markdown:
        print(_latest_path("p38_operator_support_bundle.md").read_text(encoding="utf-8"))
    elif args.print_share_packet:
        print(read_json(_latest_path("p38_operator_support_bundle_share_packet.json"), default={}))
    elif args.print_manifest:
        print(read_json(_latest_path("p38_operator_support_bundle_manifest.json"), default=[]))
    elif args.print_paths:
        print(_latest_path("p38_operator_support_bundle_paths.txt").read_text(encoding="utf-8"))
    else:
        print(report["status"])
        print(f"support_issue_count={report['support_issue_count']}")
        print(f"present_source_artifact_count={report['present_source_artifact_count']}")
        print(f"missing_source_artifact_count={report['missing_source_artifact_count']}")
        print("runtime_scheduler_enabled=false")
        print("live_order_submission_allowed=false")
        print("order_endpoint_called=false")
        print("secret_value_accessed=false")
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())

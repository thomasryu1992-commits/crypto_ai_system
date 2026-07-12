from __future__ import annotations

import argparse
from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.final_runtime_enablement_boundary_review_packet import persist_final_runtime_enablement_boundary_review_packet


def main() -> None:
    parser = argparse.ArgumentParser(description="Run P25 final runtime enablement boundary review packet gate.")
    parser.add_argument("--print-template", action="store_true", help="Print the generated P25 controls template path and contents.")
    args = parser.parse_args()
    cfg = load_config(Path.cwd())
    report = persist_final_runtime_enablement_boundary_review_packet(cfg)
    print(report["status"])
    print(report["p25_final_runtime_enablement_boundary_review_packet_report_sha256"])
    if args.print_template:
        latest = cfg.root / cfg.get("storage.latest_dir", "storage/latest")
        template_path = latest / "p25_final_runtime_enablement_boundary_review_controls_TEMPLATE.json"
        print(template_path)
        print(read_json(template_path, default={}))


if __name__ == "__main__":
    main()

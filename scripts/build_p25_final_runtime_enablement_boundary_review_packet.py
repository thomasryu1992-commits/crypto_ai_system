from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.final_runtime_enablement_boundary_review_packet import persist_final_runtime_enablement_boundary_review_packet


def main() -> None:
    cfg = load_config(Path.cwd())
    report = persist_final_runtime_enablement_boundary_review_packet(cfg)
    print(report["status"])
    print(report["p25_final_runtime_enablement_boundary_review_packet_report_sha256"])


if __name__ == "__main__":
    main()

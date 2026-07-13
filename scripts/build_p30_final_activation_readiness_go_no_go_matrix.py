from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.final_activation_readiness_go_no_go_matrix import persist_final_activation_readiness_go_no_go_matrix


def main() -> int:
    report = persist_final_activation_readiness_go_no_go_matrix(load_config(Path.cwd()))
    print(report["status"])
    print(report["p30_final_activation_readiness_go_no_go_matrix_sha256"])
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())

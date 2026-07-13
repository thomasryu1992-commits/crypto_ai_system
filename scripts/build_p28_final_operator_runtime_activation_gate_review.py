from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.final_operator_runtime_activation_gate_review import persist_final_operator_runtime_activation_gate_review


def main() -> int:
    cfg = load_config(Path.cwd())
    report = persist_final_operator_runtime_activation_gate_review(cfg)
    print(report["status"])
    print(report["p28_final_operator_runtime_activation_gate_review_sha256"])
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())

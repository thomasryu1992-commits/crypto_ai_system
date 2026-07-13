from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.final_runtime_activation_dry_run_evidence_bundle import persist_final_runtime_activation_dry_run_evidence_bundle


def main() -> int:
    report = persist_final_runtime_activation_dry_run_evidence_bundle(load_config(Path.cwd()))
    print(report["status"])
    print(report["p29_final_runtime_activation_dry_run_evidence_bundle_sha256"])
    return 0 if not report.get("blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.ci_filled_evidence_release_candidate_bundle import persist_ci_filled_evidence_release_candidate_bundle


def main() -> int:
    cfg = load_config(Path.cwd())
    report = persist_ci_filled_evidence_release_candidate_bundle(cfg=cfg)
    print(report["status"])
    print(report["p21_ci_filled_evidence_release_candidate_bundle_sha256"])
    print("limited_live_scaled_auto_trading_allowed=false")
    print("live_scaled_execution_enabled=false")
    print("runtime_scheduler_enabled=false")
    return 0 if not report["blocked"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

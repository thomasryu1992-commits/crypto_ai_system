from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.ci_filled_evidence_release_candidate_bundle import persist_ci_filled_evidence_release_candidate_bundle


def main() -> int:
    cfg = load_config(Path.cwd())
    report = persist_ci_filled_evidence_release_candidate_bundle(cfg=cfg)
    summary_path = cfg.root / "storage" / "latest" / "p21_ci_filled_evidence_release_candidate_bundle_summary.json"
    print(report["status"])
    print(f"summary_path={summary_path}")
    bundle_path = cfg.root / "storage" / "latest" / "p21_release_candidate_bundle_review_only.zip"
    if bundle_path.exists():
        print(f"bundle_path={bundle_path}")
    else:
        print("bundle_path=None")
    return 0 if not report["blocked"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

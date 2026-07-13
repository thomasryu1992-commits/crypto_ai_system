from __future__ import annotations

import json

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.live_canary_post_submit_evidence_review import persist_p11_live_canary_post_submit_evidence_review


def main() -> int:
    cfg = load_config()
    report = persist_p11_live_canary_post_submit_evidence_review(cfg=cfg)
    print(json.dumps({
        "status": report.get("status"),
        "blocked": report.get("blocked"),
        "p11_live_canary_post_submit_evidence_review_id": report.get("p11_live_canary_post_submit_evidence_review_id"),
        "external_live_canary_submit_evidence_present": report.get("external_live_canary_submit_evidence_present"),
        "live_canary_post_submit_chain_complete": report.get("live_canary_post_submit_chain_complete"),
        "live_canary_execution_enabled": report.get("live_canary_execution_enabled"),
        "live_scaled_execution_enabled": report.get("live_scaled_execution_enabled"),
        "secret_value_accessed": report.get("secret_value_accessed"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

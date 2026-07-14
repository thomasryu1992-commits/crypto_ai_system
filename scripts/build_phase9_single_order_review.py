from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from crypto_ai_system.governance.signed_testnet_execution_preparation import (
    run_signed_testnet_execution_preparation_chain,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the review-only Phase 9 single-order packet."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root containing config and storage directories.",
    )
    args = parser.parse_args(argv)

    result = run_signed_testnet_execution_preparation_chain(
        project_root=args.project_root.resolve()
    )
    phase8 = result["report"]
    phase9 = result["phase9_single_order_approval_review_packet"]

    summary = {
        "phase8_status": phase8.get("status"),
        "phase8_fresh_runtime_evidence_validated": phase8.get(
            "phase8_fresh_runtime_evidence_validated"
        ),
        "phase8_blockers": phase8.get("blockers") or [],
        "phase8_next_action": phase8.get("next_action"),
        "phase9_status": phase9.get("status"),
        "phase9_review_packet_ready": phase9.get(
            "phase9_single_order_approval_review_packet_ready"
        ),
        "blockers": phase9.get("blockers") or [],
        "next_action": phase9.get("next_action"),
        "actual_phase9_approval_created": phase9.get(
            "actual_phase9_approval_created"
        ),
        "phase9_order_submission_permission_granted": phase9.get(
            "phase9_order_submission_permission_granted"
        ),
        "testnet_order_submission_allowed": phase9.get(
            "testnet_order_submission_allowed"
        ),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

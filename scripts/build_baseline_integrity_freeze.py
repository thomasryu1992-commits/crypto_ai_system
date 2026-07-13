from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from crypto_ai_system.config import load_config  # noqa: E402
from crypto_ai_system.validation.baseline_integrity_freeze import persist_baseline_integrity_freeze_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    root = Path(argv[0]).resolve() if argv else Path.cwd().resolve()
    cfg = load_config(root)
    report = persist_baseline_integrity_freeze_report(cfg=cfg, project_root=root)
    print(json.dumps({
        "passed": report.get("passed"),
        "status": report.get("status"),
        "baseline_integrity_freeze_id": report.get("baseline_integrity_freeze_id"),
        "agent_count": (report.get("agent_library_summary") or {}).get("agent_count"),
        "review_packet_status": (report.get("review_packet_summary") or {}).get("agent_library_evidence_status"),
        "live_scaled_gate_decision": (report.get("live_scaled_readiness_summary") or {}).get("gate_decision"),
        "block_reasons": report.get("block_reasons", []),
    }, ensure_ascii=False, sort_keys=True))
    return 0 if report.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from crypto_ai_system.agents.agent_library_contract_review import run_agent_library_contract_review_latest  # noqa: E402
from crypto_ai_system.config import load_config  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    root = Path(argv[0]).resolve() if argv else Path.cwd().resolve()
    cfg = load_config(root)
    report = run_agent_library_contract_review_latest(cfg)
    print(json.dumps({
        "passed": report.get("passed"),
        "status": report.get("status"),
        "agent_count": report.get("agent_count"),
        "missing_evidence_files": report.get("missing_evidence_files"),
    }, ensure_ascii=False, sort_keys=True))
    return 0 if report.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())

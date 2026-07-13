from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _PROJECT_ROOT / "src"
for _path in (_PROJECT_ROOT, _SRC_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from crypto_ai_system.config import load_config  # noqa: E402
from crypto_ai_system.reports.review_only_export_packet import (  # noqa: E402
    run_review_only_export_packet_latest,
)


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    root = Path(argv[0]).resolve() if argv else Path.cwd().resolve()
    cfg = load_config(root)
    manifest = run_review_only_export_packet_latest(cfg)
    print(
        json.dumps(
            {
                "status": manifest.get("status"),
                "agent_library_evidence_status": manifest.get("agent_library_evidence_status"),
                "missing_agent_library_artifacts": manifest.get(
                    "missing_agent_library_artifacts", []
                ),
                "runtime_settings_mutated": manifest.get("runtime_settings_mutated"),
                "auto_promotion_allowed": manifest.get("auto_promotion_allowed"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if manifest.get("agent_library_evidence_status") == "AGENT_LIBRARY_EVIDENCE_INCLUDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

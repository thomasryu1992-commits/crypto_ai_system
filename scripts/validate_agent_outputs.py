from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from crypto_ai_system.agents.agent_output_validator import (  # noqa: E402
    build_agent_output_schema_validation_report,
    load_json_file,
    persist_agent_output_schema_validation_report,
)
from crypto_ai_system.config import load_config  # noqa: E402


def _default_sample_output(root: Path) -> dict:
    sample = root / "agent_contracts" / "eval_cases" / "approval" / "valid_approval_intake.json"
    if sample.exists():
        return load_json_file(sample)["agent_output"]
    return {}


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    root = Path(argv.pop(0)).resolve() if argv and Path(argv[0]).exists() and Path(argv[0]).is_dir() else Path.cwd().resolve()
    outputs = []
    if argv:
        outputs = [load_json_file(path) for path in argv]
    else:
        sample = _default_sample_output(root)
        if sample:
            outputs = [sample]
    cfg = load_config(root)
    report = build_agent_output_schema_validation_report(outputs)
    persist_agent_output_schema_validation_report(cfg, report)
    print(json.dumps({
        "passed": report["passed"],
        "status": report["status"],
        "output_count": report["output_count"],
        "blocked_count": report["blocked_count"],
    }, ensure_ascii=False, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

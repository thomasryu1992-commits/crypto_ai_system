from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from crypto_ai_system.config import load_config
from crypto_ai_system.registry.agent_contract_registry import generate_and_persist_agent_contract_registry


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    root = Path(argv[0]).resolve() if argv else Path.cwd().resolve()
    cfg = load_config(root)
    result = generate_and_persist_agent_contract_registry(cfg)
    index = result["index"]
    print(json.dumps({
        "status": index.get("status"),
        "agent_count": index.get("agent_count"),
        "index_id": index.get("agent_contract_index_id"),
        "registry_record_id": result["registry_record"].get("agent_contract_registry_record_id"),
        "passed": not bool(index.get("validation_errors")),
    }, ensure_ascii=False, sort_keys=True))
    return 0 if not index.get("validation_errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())

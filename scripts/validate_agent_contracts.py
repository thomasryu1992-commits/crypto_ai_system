from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from typing import Any

import os
import tempfile
from crypto_ai_system.agents.contract_loader import validate_agent_contracts, validate_permission_policies
from crypto_ai_system.config import load_config
from crypto_ai_system.registry.agent_contract_registry import build_agent_contract_index, build_agent_contract_registry_record, persist_agent_contract_index
from crypto_ai_system.utils.audit import sha256_json, utc_now_canonical


def _atomic_write_json(path: str | Path, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=True, default=str)
            handle.write("\n")
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def build_agent_contract_validation_report(root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root).resolve()
    contracts, contract_errors = validate_agent_contracts(root_path)
    permission_errors = validate_permission_policies(root_path)
    index = build_agent_contract_index(project_root=root_path)
    errors = contract_errors + permission_errors
    report = {
        "agent_contract_validation_report_version": "step322_agent_contract_validation_v1",
        "created_at_utc": utc_now_canonical(),
        "status": "AGENT_CONTRACT_VALIDATION_PASSED" if not errors else "AGENT_CONTRACT_VALIDATION_BLOCKED",
        "passed": not errors,
        "review_only": True,
        "runtime_permission_source": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "order_submission_performed": False,
        "auto_promotion_allowed": False,
        "agent_contract_index_id": index.get("agent_contract_index_id"),
        "agent_contract_index_sha256": index.get("agent_contract_index_sha256"),
        "agent_count": len(contracts),
        "errors": errors,
    }
    report["agent_contract_validation_report_sha256"] = sha256_json(report)
    return report


def persist_agent_contract_validation_report(report: dict[str, Any], root: str | Path = ".") -> Path:
    latest = Path(root).resolve() / "storage" / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    target = latest / "agent_contract_validation_report.json"
    _atomic_write_json(target, report)
    return target


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    root = Path(argv[0]).resolve() if argv else Path.cwd().resolve()
    cfg = load_config(root)
    index = build_agent_contract_index(project_root=root)
    registry_record = build_agent_contract_registry_record(index)
    persist_agent_contract_index(cfg, index, registry_record)
    report = build_agent_contract_validation_report(root)
    path = persist_agent_contract_validation_report(report, root)
    print(json.dumps({"passed": report["passed"], "status": report["status"], "report_path": str(path)}, ensure_ascii=False, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

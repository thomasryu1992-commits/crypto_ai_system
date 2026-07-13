from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from crypto_ai_system.agents.agent_output_validator import (  # noqa: E402
    validate_agent_output,
)
from crypto_ai_system.config import load_config  # noqa: E402
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path  # noqa: E402
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical  # noqa: E402

AGENT_EVAL_REGISTRY_NAME = "agent_eval_registry"
AGENT_EVAL_REPORT_VERSION = "step324_agent_eval_report_v1"


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


def discover_eval_cases(root: str | Path = ".") -> list[Path]:
    base = Path(root).resolve() / "agent_contracts" / "eval_cases"
    if not base.exists():
        return []
    return sorted(base.rglob("*.json"))


def load_eval_case(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Eval case must be a JSON object: {path}")
    return data


def evaluate_case(path: str | Path, *, root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root).resolve()
    case_path = Path(path).resolve()
    case = load_eval_case(case_path)
    output = case.get("agent_output")
    if not isinstance(output, dict):
        result = None
        actual_passed = False
        actual_blocked = True
        actual_fail_closed = True
        actual_block_reasons = ["missing_agent_output"]
    else:
        result = validate_agent_output(output)
        actual_passed = result.passed
        actual_blocked = result.blocked
        actual_fail_closed = result.fail_closed
        actual_block_reasons = result.block_reasons

    expected_contains = str(case.get("expected_block_reason_contains") or "")
    contains_ok = True
    if expected_contains:
        contains_ok = any(expected_contains in str(reason) for reason in actual_block_reasons)

    expectation_errors: list[str] = []
    if actual_passed is not bool(case.get("expected_passed")):
        expectation_errors.append(f"expected_passed:{case.get('expected_passed')}:actual:{actual_passed}")
    if actual_blocked is not bool(case.get("expected_blocked")):
        expectation_errors.append(f"expected_blocked:{case.get('expected_blocked')}:actual:{actual_blocked}")
    if actual_fail_closed is not bool(case.get("expected_fail_closed")):
        expectation_errors.append(f"expected_fail_closed:{case.get('expected_fail_closed')}:actual:{actual_fail_closed}")
    if not contains_ok:
        expectation_errors.append(f"missing_expected_block_reason_contains:{expected_contains}")

    try:
        relative_path = case_path.relative_to(root_path).as_posix()
    except ValueError:
        relative_path = case_path.name
    record = {
        "eval_case_id": case.get("eval_case_id", case_path.stem),
        "eval_case_path": relative_path,
        "agent_id": output.get("agent_id") if isinstance(output, dict) else None,
        "actual_passed": actual_passed,
        "actual_blocked": actual_blocked,
        "actual_fail_closed": actual_fail_closed,
        "actual_block_reasons": actual_block_reasons,
        "expected_passed": bool(case.get("expected_passed")),
        "expected_blocked": bool(case.get("expected_blocked")),
        "expected_fail_closed": bool(case.get("expected_fail_closed")),
        "expected_block_reason_contains": expected_contains,
        "expectation_errors": expectation_errors,
        "passed": not expectation_errors,
        "review_only": True,
        "runtime_permission_source": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "order_submission_performed": False,
        "auto_promotion_allowed": False,
    }
    record["eval_case_record_sha256"] = sha256_json(record)
    return record


def build_agent_eval_report(root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root).resolve()
    paths = discover_eval_cases(root_path)
    records = [evaluate_case(path, root=root_path) for path in paths]
    errors: list[str] = []
    if not records:
        errors.append("no_agent_eval_cases_found")
    for record in records:
        for error in record.get("expectation_errors", []):
            errors.append(f"{record['eval_case_id']}:{error}")
    report = {
        "agent_eval_report_version": AGENT_EVAL_REPORT_VERSION,
        "agent_eval_report_id": stable_id("agent_eval_report", {"records": records, "errors": errors}, 24),
        "created_at_utc": utc_now_canonical(),
        "status": "AGENT_EVALS_PASSED" if not errors else "AGENT_EVALS_BLOCKED",
        "passed": not errors,
        "review_only": True,
        "runtime_permission_source": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "runtime_mutation_performed": False,
        "order_submission_performed": False,
        "auto_promotion_allowed": False,
        "eval_case_count": len(records),
        "blocked_case_count": sum(1 for record in records if record.get("actual_blocked")),
        "fail_closed_case_count": sum(1 for record in records if record.get("actual_fail_closed")),
        "records": records,
        "errors": errors,
    }
    report["agent_eval_report_sha256"] = sha256_json(report)
    return report


def persist_agent_eval_report(root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root).resolve()
    cfg = load_config(root_path)
    report = build_agent_eval_report(root_path)
    latest_raw = cfg.get("storage.latest_dir", "storage/latest")
    latest = Path(latest_raw)
    if not latest.is_absolute():
        latest = cfg.root / latest
    latest.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(latest / "agent_eval_report.json", report)
    appended = append_registry_record(
        registry_path(cfg, AGENT_EVAL_REGISTRY_NAME),
        report,
        registry_name=AGENT_EVAL_REGISTRY_NAME,
        id_field="agent_eval_registry_append_id",
        hash_field="agent_eval_registry_append_sha256",
        id_prefix="agent_eval_registry_append",
    )
    _atomic_write_json(latest / "agent_eval_registry_record.json", appended)
    return {"report": report, "registry_record": appended}


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    root = Path(argv[0]).resolve() if argv else Path.cwd().resolve()
    result = persist_agent_eval_report(root)
    report = result["report"]
    print(json.dumps({
        "passed": report["passed"],
        "status": report["status"],
        "eval_case_count": report["eval_case_count"],
        "blocked_case_count": report["blocked_case_count"],
    }, ensure_ascii=False, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

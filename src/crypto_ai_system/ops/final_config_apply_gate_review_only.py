from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.ops.config_activation_apply_stub_review_only import execute_config_activation_apply_stub_review_only

STEP225_STATUS_OK = "STEP225_V5_FINAL_CONFIG_APPLY_GATE_REVIEW_ONLY_OK"
STEP225_VALIDATION_OK = "STEP225_V5_FINAL_CONFIG_APPLY_GATE_REVIEW_ONLY_VALIDATION_OK"
FINAL_GATE_MODE = "FINAL_CONFIG_APPLY_GATE_REVIEW_ONLY"


@dataclass
class Step225Result:
    status: str
    root: str
    source_step224_result_path: str
    final_gate_decisions_json_path: str
    final_gate_decisions_jsonl_path: str
    final_gate_decisions_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_apply_stub_count: int
    final_gate_decision_count: int
    final_gate_review_ready_count: int
    final_gate_blocked_count: int
    final_config_apply_gate_review_created: bool
    final_gate_mode: str
    final_gate_review_only: bool
    final_apply_gate_passed: bool
    config_apply_allowed: bool
    config_applied: bool
    config_activation_allowed: bool
    config_activated: bool
    paper_execution_enabled: bool
    paper_order_execution_enabled: bool
    adapter_routing_enabled: bool
    live_trading_allowed: bool
    strategy_registry_write_allowed: bool
    live_order_executed: bool
    telegram_real_send: bool
    decisions: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step225ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step224_present: bool
    final_gate_decisions_json_exists: bool
    final_gate_decisions_jsonl_exists: bool
    final_gate_decisions_csv_exists: bool
    markdown_report_exists: bool
    source_apply_stubs_present: bool
    final_gate_decisions_present: bool
    final_gate_review_created: bool
    final_gate_mode_review_only: bool
    no_final_apply_gate_passed: bool
    no_config_apply_allowed: bool
    no_config_applied: bool
    no_config_activation_allowed: bool
    no_config_activated: bool
    no_paper_execution_enabled: bool
    no_paper_order_execution: bool
    no_adapter_routing: bool
    no_live_trading: bool
    no_strategy_registry_write: bool
    no_live_side_effects: bool
    blocking_failure_count: int
    blocking_failures: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True, ensure_ascii=False) for row in rows) + ("\n" if rows else ""), encoding="utf-8")


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else ["final_gate_decision_id", "final_gate_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["final_gate_checklist"] = json.dumps(out.get("final_gate_checklist", {}), sort_keys=True)
            out["final_gate_blockers"] = "|".join(out.get("final_gate_blockers", []))
            out["final_gate_warnings"] = "|".join(out.get("final_gate_warnings", []))
            writer.writerow(out)


def _ensure_step224(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step224_config_activation_apply_stub_review_only_latest.json"
    if not path.exists():
        execute_config_activation_apply_stub_review_only(root, write_output=True)
    return _load_json(path)


def _load_stubs(step224: Dict[str, Any]) -> List[Dict[str, Any]]:
    path = Path(step224.get("apply_stubs_json_path", ""))
    if path.exists():
        return list(_load_json(path).get("stubs", []) or [])
    return list(step224.get("stubs", []) or [])


def _decision(stub: Dict[str, Any]) -> Dict[str, Any]:
    checklist = {
        "source_apply_stub_review_ready": stub.get("apply_stub_status") == "CONFIG_ACTIVATION_APPLY_STUB_REVIEW_READY",
        "source_apply_mode_stub_only": stub.get("apply_mode") == "CONFIG_ACTIVATION_APPLY_STUB_ONLY",
        "source_apply_request_created": stub.get("apply_request_created") is True,
        "source_apply_request_submitted_false": stub.get("apply_request_submitted") is False,
        "source_config_apply_allowed_false": stub.get("config_apply_allowed") is False,
        "source_config_applied_false": stub.get("config_applied") is False,
        "source_paper_execution_enabled_false": stub.get("paper_execution_enabled") is False,
        "source_adapter_routing_enabled_false": stub.get("adapter_routing_enabled") is False,
        "source_live_trading_allowed_false": stub.get("live_trading_allowed") is False,
    }
    blockers = list(stub.get("apply_blockers", []) or [])
    for key, ok in checklist.items():
        if not ok:
            blockers.append(key.upper() + "_FAILED")
    blockers.append("STEP225_REVIEW_ONLY_NO_FINAL_APPLY")
    blockers = sorted(set(blockers))
    hard = [b for b in blockers if b != "STEP225_REVIEW_ONLY_NO_FINAL_APPLY"]
    status = "FINAL_CONFIG_APPLY_GATE_REVIEW_READY" if not hard and all(checklist.values()) else "FINAL_CONFIG_APPLY_GATE_BLOCKED"
    decision_id = "fcag_" + hashlib.sha1("|".join([str(stub.get("activation_apply_stub_id", "")), str(stub.get("observation_id", ""))]).encode()).hexdigest()[:20]
    return {
        "final_gate_decision_id": decision_id,
        "activation_apply_stub_id": str(stub.get("activation_apply_stub_id", "")),
        "activation_candidate_id": str(stub.get("activation_candidate_id", "")),
        "config_draft_id": str(stub.get("config_draft_id", "")),
        "observation_id": str(stub.get("observation_id", "")),
        "registry_id": str(stub.get("registry_id", "")),
        "comparison_group": str(stub.get("comparison_group", "")),
        "side": str(stub.get("side", "")),
        "source_apply_stub_status": str(stub.get("apply_stub_status", "")),
        "final_gate_mode": FINAL_GATE_MODE,
        "final_gate_status": status,
        "final_gate_checklist": checklist,
        "final_gate_blockers": blockers,
        "final_gate_warnings": sorted(set(list(stub.get("apply_warnings", []) or []) + ["FINAL_GATE_REVIEW_ONLY_NO_CONFIG_APPLY", "STEP226_REQUIRED_FOR_PAPER_EXECUTION_MODE_SHADOW_READY_REVIEW"])),
        "next_required_step": "STEP226_PAPER_EXECUTION_MODE_SHADOW_READY_REVIEW_ONLY" if status.endswith("REVIEW_READY") else "DO_NOT_CREATE_PAPER_EXECUTION_MODE_REVIEW_UNTIL_BLOCKERS_RESOLVED",
        "final_gate_decision_created": True,
        "final_apply_gate_passed": False,
        "config_apply_allowed": False,
        "config_applied": False,
        "config_activation_allowed": False,
        "config_activated": False,
        "paper_execution_enabled": False,
        "paper_order_execution_enabled": False,
        "adapter_routing_enabled": False,
        "live_trading_allowed": False,
        "strategy_registry_write_allowed": False,
        "live_order_executed": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _summary(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in rows:
        for blocker in row.get("final_gate_blockers", []):
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _render_md(result: Step225Result) -> str:
    lines = ["# Step225 v5 Final Config Apply Gate Review-Only", "", "Step225 creates final config apply gate decisions from Step224 apply stubs.", "This is review-only and does not apply config or enable paper execution.", "", "## Summary", f"- status: `{result.status}`", f"- source_apply_stub_count: {result.source_apply_stub_count}", f"- final_gate_decision_count: {result.final_gate_decision_count}", f"- final_gate_review_ready_count: {result.final_gate_review_ready_count}", f"- final_gate_blocked_count: {result.final_gate_blocked_count}", f"- final_gate_mode: `{result.final_gate_mode}`", f"- final_apply_gate_passed: {result.final_apply_gate_passed}", f"- config_applied: {result.config_applied}", f"- paper_execution_enabled: {result.paper_execution_enabled}"]
    return "\n".join(lines) + "\n"


def execute_final_config_apply_gate_review_only(root: str | Path, *, write_output: bool = True) -> Step225Result:
    root_path = Path(root).resolve()
    step224_path = root_path / "storage/latest/step224_config_activation_apply_stub_review_only_latest.json"
    step224 = _ensure_step224(root_path)
    stubs = _load_stubs(step224)
    decisions = [_decision(s) for s in stubs]
    json_path = root_path / "data/reports/step225_final_config_apply_gate_decisions.json"
    jsonl_path = root_path / "data/stores/step225_final_config_apply_gate_decisions.jsonl"
    csv_path = root_path / "data/reports/step225_final_config_apply_gate_decisions.csv"
    md_path = root_path / "data/reports/step225_final_config_apply_gate_review_only_report.md"
    latest_path = root_path / "storage/latest/step225_final_config_apply_gate_review_only_latest.json"
    result = Step225Result(
        status=STEP225_STATUS_OK,
        root=str(root_path),
        source_step224_result_path=str(step224_path),
        final_gate_decisions_json_path=str(json_path),
        final_gate_decisions_jsonl_path=str(jsonl_path),
        final_gate_decisions_csv_path=str(csv_path),
        markdown_report_path=str(md_path),
        latest_result_path=str(latest_path),
        source_apply_stub_count=len(stubs),
        final_gate_decision_count=len(decisions),
        final_gate_review_ready_count=sum(1 for d in decisions if d["final_gate_status"] == "FINAL_CONFIG_APPLY_GATE_REVIEW_READY"),
        final_gate_blocked_count=sum(1 for d in decisions if d["final_gate_status"] == "FINAL_CONFIG_APPLY_GATE_BLOCKED"),
        final_config_apply_gate_review_created=True,
        final_gate_mode=FINAL_GATE_MODE,
        final_gate_review_only=True,
        final_apply_gate_passed=False,
        config_apply_allowed=False,
        config_applied=False,
        config_activation_allowed=False,
        config_activated=False,
        paper_execution_enabled=False,
        paper_order_execution_enabled=False,
        adapter_routing_enabled=False,
        live_trading_allowed=False,
        strategy_registry_write_allowed=False,
        live_order_executed=False,
        telegram_real_send=False,
        decisions=decisions,
        blocker_summary=_summary(decisions),
    )
    payload = result.to_dict()
    result.result_sha256 = _sha256(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    if write_output:
        _write_json(json_path, {"decisions": decisions}); _write_jsonl(jsonl_path, decisions); _write_csv(csv_path, decisions)
        md_path.parent.mkdir(parents=True, exist_ok=True); md_path.write_text(_render_md(result), encoding="utf-8")
        _write_json(latest_path, result.to_dict())
    return result


def validate_final_config_apply_gate_review_only(root: str | Path) -> Step225ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step225_final_config_apply_gate_review_only_latest.json"
    if not result_path.exists():
        execute_final_config_apply_gate_review_only(root_path, write_output=True)
    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    decisions = list(payload.get("decisions", []) or [])
    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step224_present": Path(payload.get("source_step224_result_path", "")).exists(),
        "final_gate_decisions_json_exists": Path(payload.get("final_gate_decisions_json_path", "")).exists(),
        "final_gate_decisions_jsonl_exists": Path(payload.get("final_gate_decisions_jsonl_path", "")).exists(),
        "final_gate_decisions_csv_exists": Path(payload.get("final_gate_decisions_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_apply_stubs_present": int(payload.get("source_apply_stub_count", 0)) > 0,
        "final_gate_decisions_present": int(payload.get("final_gate_decision_count", 0)) > 0 and bool(decisions),
        "final_gate_review_created": payload.get("final_config_apply_gate_review_created") is True and all(d.get("final_gate_decision_created") is True for d in decisions),
        "final_gate_mode_review_only": payload.get("final_gate_mode") == FINAL_GATE_MODE and all(d.get("final_gate_mode") == FINAL_GATE_MODE for d in decisions),
        "no_final_apply_gate_passed": payload.get("final_apply_gate_passed") is False and all(d.get("final_apply_gate_passed") is False for d in decisions),
        "no_config_apply_allowed": payload.get("config_apply_allowed") is False and all(d.get("config_apply_allowed") is False for d in decisions),
        "no_config_applied": payload.get("config_applied") is False and all(d.get("config_applied") is False for d in decisions),
        "no_config_activation_allowed": payload.get("config_activation_allowed") is False and all(d.get("config_activation_allowed") is False for d in decisions),
        "no_config_activated": payload.get("config_activated") is False and all(d.get("config_activated") is False for d in decisions),
        "no_paper_execution_enabled": payload.get("paper_execution_enabled") is False and all(d.get("paper_execution_enabled") is False for d in decisions),
        "no_paper_order_execution": payload.get("paper_order_execution_enabled") is False and all(d.get("paper_order_execution_enabled") is False for d in decisions),
        "no_adapter_routing": payload.get("adapter_routing_enabled") is False and all(d.get("adapter_routing_enabled") is False for d in decisions),
        "no_live_trading": payload.get("live_trading_allowed") is False and all(d.get("live_trading_allowed") is False for d in decisions),
        "no_strategy_registry_write": payload.get("strategy_registry_write_allowed") is False and all(d.get("strategy_registry_write_allowed") is False for d in decisions),
        "no_live_side_effects": payload.get("live_order_executed") is False and payload.get("telegram_real_send") is False and all(d.get("live_order_executed") is False for d in decisions),
    }
    failures = [name for name, ok in checks.items() if not ok]
    return Step225ValidationResult(STEP225_VALIDATION_OK if not failures else "STEP225_V5_FINAL_CONFIG_APPLY_GATE_REVIEW_ONLY_VALIDATION_FAILED", str(result_path), blocking_failure_count=len(failures), blocking_failures=failures, **checks)

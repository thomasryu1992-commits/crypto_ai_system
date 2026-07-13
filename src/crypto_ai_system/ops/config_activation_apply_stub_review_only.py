from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.ops.controlled_config_activation_review_only import (
    execute_controlled_config_activation_review_only,
)

STEP224_STATUS_OK = "STEP224_V5_CONFIG_ACTIVATION_APPLY_STUB_REVIEW_ONLY_OK"
STEP224_VALIDATION_OK = "STEP224_V5_CONFIG_ACTIVATION_APPLY_STUB_REVIEW_ONLY_VALIDATION_OK"
APPLY_MODE_STUB_ONLY = "CONFIG_ACTIVATION_APPLY_STUB_ONLY"


@dataclass
class Step224Result:
    status: str
    root: str
    source_step223_result_path: str
    apply_stubs_json_path: str
    apply_stubs_jsonl_path: str
    apply_stubs_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_activation_candidate_count: int
    source_activation_review_ready_count: int
    apply_stub_count: int
    apply_stub_review_ready_count: int
    apply_stub_blocked_count: int
    apply_stub_watchlist_count: int
    config_activation_apply_stub_review_created: bool
    apply_mode: str
    apply_stub_only: bool
    apply_request_submitted: bool
    config_activation_allowed: bool
    config_activated: bool
    config_apply_allowed: bool
    config_applied: bool
    paper_execution_enabled: bool
    paper_execution_enablement_allowed: bool
    paper_execution_upgrade_allowed: bool
    paper_order_execution_enabled: bool
    paper_trade_execution_enabled: bool
    adapter_routing_enabled: bool
    shadow_execution_enabled: bool
    limited_live_review_allowed: bool
    live_trading_allowed: bool
    strategy_registry_write_allowed: bool
    promotion_allowed: bool
    auto_strategy_promotion: bool
    external_api_call_performed: bool
    live_order_executed: bool
    real_adapter_call_performed: bool
    telegram_real_send: bool
    production_cutover_executable: bool
    live_mode_enable_allowed: bool
    stubs: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step224ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step223_present: bool
    apply_stubs_json_exists: bool
    apply_stubs_jsonl_exists: bool
    apply_stubs_csv_exists: bool
    markdown_report_exists: bool
    source_activation_candidates_present: bool
    apply_stubs_present: bool
    apply_stub_review_created: bool
    apply_mode_stub_only: bool
    no_apply_request_submitted: bool
    no_config_activation_allowed: bool
    no_config_activated: bool
    no_config_apply_allowed: bool
    no_config_applied: bool
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
    fields = list(rows[0].keys()) if rows else ["activation_apply_stub_id", "apply_stub_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ("apply_request_template", "apply_preconditions"):
                out[key] = json.dumps(out.get(key, {}), sort_keys=True)
            for key in ("apply_blockers", "apply_warnings"):
                out[key] = "|".join(out.get(key, []))
            writer.writerow(out)


def _ensure_step223(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step223_controlled_config_activation_review_only_latest.json"
    if not path.exists():
        execute_controlled_config_activation_review_only(root, write_output=True)
    return _load_json(path)


def _load_candidates(step223: Dict[str, Any]) -> List[Dict[str, Any]]:
    path = Path(step223.get("activation_candidates_json_path", ""))
    if path.exists():
        return list(_load_json(path).get("candidates", []) or [])
    return list(step223.get("candidates", []) or [])


def _stub(candidate: Dict[str, Any]) -> Dict[str, Any]:
    preconditions = {
        "source_activation_review_ready": candidate.get("activation_status") == "CONTROLLED_CONFIG_ACTIVATION_REVIEW_READY",
        "source_activation_mode_review_only": candidate.get("activation_mode") == "CONTROLLED_ACTIVATION_REVIEW_ONLY",
        "source_config_activation_allowed_false": candidate.get("config_activation_allowed") is False,
        "source_config_activated_false": candidate.get("config_activated") is False,
        "source_config_apply_allowed_false": candidate.get("config_apply_allowed") is False,
        "source_config_applied_false": candidate.get("config_applied") is False,
        "source_paper_execution_enabled_false": candidate.get("paper_execution_enabled") is False,
        "paper_only_scope": bool((candidate.get("staged_activation_scope", {}) or {}).get("paper_only", False)),
    }
    blockers = list(candidate.get("activation_blockers", []) or [])
    for key, ok in preconditions.items():
        if not ok:
            blockers.append(key.upper() + "_FAILED")
    blockers.append("STEP224_REVIEW_ONLY_NO_APPLY_REQUEST_SUBMIT")
    blockers = sorted(set(blockers))
    hard = [b for b in blockers if b != "STEP224_REVIEW_ONLY_NO_APPLY_REQUEST_SUBMIT"]
    status = "CONFIG_ACTIVATION_APPLY_STUB_REVIEW_READY" if not hard and all(preconditions.values()) else "CONFIG_ACTIVATION_APPLY_STUB_BLOCKED"
    sid = "actapply_" + hashlib.sha1(
        ("|".join([
            str(candidate.get("activation_candidate_id", "")),
            str(candidate.get("config_draft_id", "")),
            str(candidate.get("observation_id", "")),
        ])).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "activation_apply_stub_id": sid,
        "activation_candidate_id": str(candidate.get("activation_candidate_id", "")),
        "apply_validation_id": str(candidate.get("apply_validation_id", "")),
        "config_draft_id": str(candidate.get("config_draft_id", "")),
        "enablement_plan_id": str(candidate.get("enablement_plan_id", "")),
        "approval_validation_id": str(candidate.get("approval_validation_id", "")),
        "observation_id": str(candidate.get("observation_id", "")),
        "registry_id": str(candidate.get("registry_id", "")),
        "comparison_group": str(candidate.get("comparison_group", "")),
        "side": str(candidate.get("side", "")),
        "source_activation_status": str(candidate.get("activation_status", "")),
        "source_activation_mode": str(candidate.get("activation_mode", "")),
        "apply_mode": APPLY_MODE_STUB_ONLY,
        "apply_stub_status": status,
        "apply_request_template": {
            "request_type": "CONFIG_ACTIVATION_APPLY_REQUEST_TEMPLATE",
            "request_mode": APPLY_MODE_STUB_ONLY,
            "activation_candidate_id": str(candidate.get("activation_candidate_id", "")),
            "config_draft_id": str(candidate.get("config_draft_id", "")),
            "observation_id": str(candidate.get("observation_id", "")),
            "scope": candidate.get("staged_activation_scope", {}),
            "runtime_guards": candidate.get("staged_runtime_guards", {}),
            "disable_flags": candidate.get("staged_disable_flags", {}),
            "submit_to_runtime": False,
            "paper_only": True,
            "live_trading_allowed": False,
        },
        "apply_preconditions": preconditions,
        "apply_blockers": blockers,
        "apply_warnings": sorted(set(list(candidate.get("activation_warnings", []) or []) + [
            "APPLY_STUB_ONLY_NO_CONFIG_APPLY",
            "STEP225_REQUIRED_FOR_FINAL_APPLY_GATE_REVIEW",
        ])),
        "next_required_step": "STEP225_FINAL_CONFIG_APPLY_GATE_REVIEW_ONLY" if status.endswith("REVIEW_READY") else "DO_NOT_CREATE_FINAL_APPLY_GATE_UNTIL_BLOCKERS_RESOLVED",
        "config_activation_apply_stub_created": True,
        "apply_request_created": True,
        "apply_request_submitted": False,
        "config_activation_allowed": False,
        "config_activated": False,
        "config_apply_allowed": False,
        "config_applied": False,
        "paper_execution_enabled": False,
        "paper_execution_enablement_allowed": False,
        "paper_execution_upgrade_allowed": False,
        "paper_order_execution_enabled": False,
        "paper_trade_execution_enabled": False,
        "adapter_routing_enabled": False,
        "shadow_execution_enabled": False,
        "limited_live_review_allowed": False,
        "live_trading_allowed": False,
        "strategy_registry_write_allowed": False,
        "promotion_allowed": False,
        "live_order_executed": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _summary(stubs: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for stub in stubs:
        for blocker in stub.get("apply_blockers", []):
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _render_md(result: Step224Result) -> str:
    lines = [
        "# Step224 v5 Config Activation Apply Stub Review-Only",
        "",
        "Step224 creates config activation apply request stubs from Step223 controlled activation candidates.",
        "This is apply-stub-only and does not submit requests, apply config, or enable paper execution.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- source_activation_candidate_count: {result.source_activation_candidate_count}",
        f"- apply_stub_count: {result.apply_stub_count}",
        f"- apply_stub_review_ready_count: {result.apply_stub_review_ready_count}",
        f"- apply_stub_blocked_count: {result.apply_stub_blocked_count}",
        f"- apply_mode: `{result.apply_mode}`",
        f"- apply_request_submitted: {result.apply_request_submitted}",
        f"- config_activation_allowed: {result.config_activation_allowed}",
        f"- config_activated: {result.config_activated}",
        f"- paper_execution_enabled: {result.paper_execution_enabled}",
        "",
        "## Apply stubs",
    ]
    for stub in result.stubs:
        blockers = ", ".join(stub.get("apply_blockers", [])) if stub.get("apply_blockers") else "NO_BLOCKER"
        lines.append(f"- `{stub.get('comparison_group','')}` {stub.get('side','')}: status={stub.get('apply_stub_status')}, submitted={stub.get('apply_request_submitted')}, blockers={blockers}")
    return "\n".join(lines) + "\n"


def execute_config_activation_apply_stub_review_only(root: str | Path, *, write_output: bool = True) -> Step224Result:
    root_path = Path(root).resolve()
    step223_path = root_path / "storage/latest/step223_controlled_config_activation_review_only_latest.json"
    step223 = _ensure_step223(root_path)
    candidates = _load_candidates(step223)
    stubs = [_stub(c) for c in candidates]

    json_path = root_path / "data/reports/step224_config_activation_apply_stubs.json"
    jsonl_path = root_path / "data/stores/step224_config_activation_apply_stubs.jsonl"
    csv_path = root_path / "data/reports/step224_config_activation_apply_stubs.csv"
    md_path = root_path / "data/reports/step224_config_activation_apply_stub_review_only_report.md"
    latest_path = root_path / "storage/latest/step224_config_activation_apply_stub_review_only_latest.json"

    result = Step224Result(
        status=STEP224_STATUS_OK,
        root=str(root_path),
        source_step223_result_path=str(step223_path),
        apply_stubs_json_path=str(json_path),
        apply_stubs_jsonl_path=str(jsonl_path),
        apply_stubs_csv_path=str(csv_path),
        markdown_report_path=str(md_path),
        latest_result_path=str(latest_path),
        source_activation_candidate_count=len(candidates),
        source_activation_review_ready_count=sum(1 for c in candidates if c.get("activation_status") == "CONTROLLED_CONFIG_ACTIVATION_REVIEW_READY"),
        apply_stub_count=len(stubs),
        apply_stub_review_ready_count=sum(1 for s in stubs if s.get("apply_stub_status") == "CONFIG_ACTIVATION_APPLY_STUB_REVIEW_READY"),
        apply_stub_blocked_count=sum(1 for s in stubs if s.get("apply_stub_status") == "CONFIG_ACTIVATION_APPLY_STUB_BLOCKED"),
        apply_stub_watchlist_count=sum(1 for s in stubs if s.get("apply_stub_status") == "CONFIG_ACTIVATION_APPLY_STUB_WATCHLIST"),
        config_activation_apply_stub_review_created=True,
        apply_mode=APPLY_MODE_STUB_ONLY,
        apply_stub_only=True,
        apply_request_submitted=False,
        config_activation_allowed=False,
        config_activated=False,
        config_apply_allowed=False,
        config_applied=False,
        paper_execution_enabled=False,
        paper_execution_enablement_allowed=False,
        paper_execution_upgrade_allowed=False,
        paper_order_execution_enabled=False,
        paper_trade_execution_enabled=False,
        adapter_routing_enabled=False,
        shadow_execution_enabled=False,
        limited_live_review_allowed=False,
        live_trading_allowed=False,
        strategy_registry_write_allowed=False,
        promotion_allowed=False,
        auto_strategy_promotion=False,
        external_api_call_performed=False,
        live_order_executed=False,
        real_adapter_call_performed=False,
        telegram_real_send=False,
        production_cutover_executable=False,
        live_mode_enable_allowed=False,
        stubs=stubs,
        blocker_summary=_summary(stubs),
    )
    payload = result.to_dict()
    result.result_sha256 = _sha256(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    if write_output:
        _write_json(json_path, {"stubs": stubs})
        _write_jsonl(jsonl_path, stubs)
        _write_csv(csv_path, stubs)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_render_md(result), encoding="utf-8")
        _write_json(latest_path, result.to_dict())
    return result


def validate_config_activation_apply_stub_review_only(root: str | Path) -> Step224ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step224_config_activation_apply_stub_review_only_latest.json"
    if not result_path.exists():
        execute_config_activation_apply_stub_review_only(root_path, write_output=True)
    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    stubs = list(payload.get("stubs", []) or [])
    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step223_present": Path(payload.get("source_step223_result_path", "")).exists(),
        "apply_stubs_json_exists": Path(payload.get("apply_stubs_json_path", "")).exists(),
        "apply_stubs_jsonl_exists": Path(payload.get("apply_stubs_jsonl_path", "")).exists(),
        "apply_stubs_csv_exists": Path(payload.get("apply_stubs_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_activation_candidates_present": int(payload.get("source_activation_candidate_count", 0)) > 0,
        "apply_stubs_present": int(payload.get("apply_stub_count", 0)) > 0 and bool(stubs),
        "apply_stub_review_created": payload.get("config_activation_apply_stub_review_created") is True and all(s.get("config_activation_apply_stub_created") is True for s in stubs),
        "apply_mode_stub_only": payload.get("apply_mode") == APPLY_MODE_STUB_ONLY and all(s.get("apply_mode") == APPLY_MODE_STUB_ONLY for s in stubs),
        "no_apply_request_submitted": payload.get("apply_request_submitted") is False and all(s.get("apply_request_submitted") is False for s in stubs),
        "no_config_activation_allowed": payload.get("config_activation_allowed") is False and all(s.get("config_activation_allowed") is False for s in stubs),
        "no_config_activated": payload.get("config_activated") is False and all(s.get("config_activated") is False for s in stubs),
        "no_config_apply_allowed": payload.get("config_apply_allowed") is False and all(s.get("config_apply_allowed") is False for s in stubs),
        "no_config_applied": payload.get("config_applied") is False and all(s.get("config_applied") is False for s in stubs),
        "no_paper_execution_enabled": payload.get("paper_execution_enabled") is False and all(s.get("paper_execution_enabled") is False for s in stubs),
        "no_paper_order_execution": payload.get("paper_order_execution_enabled") is False and all(s.get("paper_order_execution_enabled") is False for s in stubs),
        "no_adapter_routing": payload.get("adapter_routing_enabled") is False and all(s.get("adapter_routing_enabled") is False for s in stubs),
        "no_live_trading": payload.get("live_trading_allowed") is False and all(s.get("live_trading_allowed") is False for s in stubs),
        "no_strategy_registry_write": payload.get("strategy_registry_write_allowed") is False and all(s.get("strategy_registry_write_allowed") is False for s in stubs),
        "no_live_side_effects": payload.get("live_order_executed") is False and payload.get("real_adapter_call_performed") is False and payload.get("telegram_real_send") is False and all(s.get("live_order_executed") is False for s in stubs),
    }
    failures = [name for name, ok in checks.items() if not ok]
    return Step224ValidationResult(
        status=STEP224_VALIDATION_OK if not failures else "STEP224_V5_CONFIG_ACTIVATION_APPLY_STUB_REVIEW_ONLY_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )

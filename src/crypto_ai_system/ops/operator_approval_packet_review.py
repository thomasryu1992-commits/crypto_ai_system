from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.feedback.paper_execution_upgrade_readiness_review import (
    execute_paper_execution_upgrade_readiness_review,
)

STEP217_STATUS_OK = "STEP217_V5_OPERATOR_APPROVAL_PACKET_REVIEW_ONLY_OK"
STEP217_VALIDATION_OK = "STEP217_V5_OPERATOR_APPROVAL_PACKET_REVIEW_ONLY_VALIDATION_OK"

APPROVAL_PACKET_VERSION = "step217_v5_operator_approval_packet_review_only"


@dataclass
class OperatorApprovalPacket:
    approval_packet_id: str
    upgrade_review_id: str
    promotion_decision_id: str
    feedback_review_id: str
    observation_id: str
    registry_id: str
    comparison_group: str
    side: str
    source_upgrade_readiness_status: str
    upgrade_readiness_score: float
    promotion_readiness_score: float
    evidence_completeness_score: float
    packet_status: str
    packet_summary: str
    approval_checklist: Dict[str, bool]
    approval_blockers: List[str]
    approval_warnings: List[str]
    required_operator_actions: List[str]
    safety_attestations: Dict[str, bool]
    packet_version: str
    created_at_utc: str
    manual_approval_required: bool
    operator_review_required: bool
    operator_approved: bool
    approval_recorded: bool
    paper_execution_upgrade_allowed: bool
    paper_order_execution_enabled: bool
    paper_trade_execution_enabled: bool
    adapter_routing_enabled: bool
    shadow_execution_enabled: bool
    limited_live_review_allowed: bool
    live_trading_allowed: bool
    strategy_registry_write_allowed: bool
    promotion_allowed: bool
    live_order_executed: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step217OperatorApprovalPacketResult:
    status: str
    root: str
    source_step216_result_path: str
    approval_packets_json_path: str
    approval_packets_jsonl_path: str
    approval_packets_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_upgrade_review_count: int
    approval_packet_count: int
    review_ready_packet_count: int
    watchlist_packet_count: int
    blocked_packet_count: int
    operator_approval_packet_created: bool
    operator_packet_review_only: bool
    manual_approval_required: bool
    operator_review_required: bool
    operator_approved: bool
    approval_recorded: bool
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
    packets: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step217ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step216_present: bool
    approval_packets_json_exists: bool
    approval_packets_jsonl_exists: bool
    approval_packets_csv_exists: bool
    markdown_report_exists: bool
    source_upgrade_reviews_present: bool
    approval_packets_present: bool
    operator_approval_packet_created: bool
    review_only_mode: bool
    manual_approval_required: bool
    operator_review_required: bool
    no_operator_approval_recorded: bool
    no_paper_execution_upgrade: bool
    no_paper_order_execution: bool
    no_adapter_routing: bool
    no_shadow_execution: bool
    no_limited_live_review: bool
    no_live_trading: bool
    no_strategy_registry_write: bool
    no_promotion_allowed: bool
    no_auto_strategy_promotion: bool
    no_external_api_calls: bool
    no_live_side_effects: bool
    no_production_cutover: bool
    blocking_failure_count: int
    blocking_failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["approval_packet_id", "packet_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["approval_checklist"] = json.dumps(out.get("approval_checklist", {}), sort_keys=True)
            out["safety_attestations"] = json.dumps(out.get("safety_attestations", {}), sort_keys=True)
            out["approval_blockers"] = "|".join(out.get("approval_blockers", []))
            out["approval_warnings"] = "|".join(out.get("approval_warnings", []))
            out["required_operator_actions"] = "|".join(out.get("required_operator_actions", []))
            writer.writerow(out)


def _ensure_step216(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step216_paper_execution_upgrade_readiness_review_latest.json"
    if not path.exists():
        execute_paper_execution_upgrade_readiness_review(root, write_output=True, allow_source_regeneration=True)
    return _load_json(path)


def _load_step216_reviews(step216: Dict[str, Any]) -> List[Dict[str, Any]]:
    reviews_path = Path(step216.get("upgrade_reviews_json_path", ""))
    if reviews_path.exists():
        return list(_load_json(reviews_path).get("reviews", []) or [])
    return list(step216.get("reviews", []) or [])


def _packet_id(review: Dict[str, Any]) -> str:
    raw = "|".join(
        [
            "step217_operator_approval_packet",
            str(review.get("upgrade_review_id", "")),
            str(review.get("promotion_decision_id", "")),
            str(review.get("observation_id", "")),
        ]
    )
    return "opap_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _checklist(review: Dict[str, Any]) -> Dict[str, bool]:
    return {
        "upgrade_review_ready": str(review.get("upgrade_readiness_status", "")) == "PAPER_EXECUTION_UPGRADE_REVIEW_READY",
        "operator_review_required": bool(review.get("operator_review_required", False)),
        "manual_approval_required": bool(review.get("manual_approval_required", False)),
        "promotion_review_ready": bool(review.get("has_promotion_review_ready", False)),
        "no_promotion_blockers": bool(review.get("has_no_promotion_blockers", False)),
        "replay_evidence_present": bool(review.get("has_replay_evidence", False)),
        "dry_run_intent_evidence_present": bool(review.get("has_dry_run_intent_evidence", False)),
        "lifecycle_evidence_present": bool(review.get("has_lifecycle_evidence", False)),
        "outcome_evidence_present": bool(review.get("has_outcome_evidence", False)),
        "feedback_evidence_present": bool(review.get("has_feedback_evidence", False)),
        "promotion_decision_evidence_present": bool(review.get("has_promotion_decision_evidence", False)),
        "paper_execution_upgrade_disabled": review.get("paper_execution_upgrade_allowed") is False,
        "paper_order_execution_disabled": review.get("paper_order_execution_enabled") is False,
        "adapter_routing_disabled": review.get("adapter_routing_enabled") is False,
        "limited_live_review_disabled": review.get("limited_live_review_allowed") is False,
        "live_trading_disabled": review.get("live_trading_allowed") is False,
        "strategy_registry_write_disabled": review.get("strategy_registry_write_allowed") is False,
        "promotion_disabled": review.get("promotion_allowed") is False,
    }


def _safety_attestations(review: Dict[str, Any]) -> Dict[str, bool]:
    return {
        "operator_approved_false": True,
        "approval_recorded_false": True,
        "paper_execution_upgrade_allowed_false": review.get("paper_execution_upgrade_allowed") is False,
        "paper_order_execution_enabled_false": review.get("paper_order_execution_enabled") is False,
        "paper_trade_execution_enabled_false": review.get("paper_trade_execution_enabled") is False,
        "adapter_routing_enabled_false": review.get("adapter_routing_enabled") is False,
        "shadow_execution_enabled_false": review.get("shadow_execution_enabled") is False,
        "limited_live_review_allowed_false": review.get("limited_live_review_allowed") is False,
        "live_trading_allowed_false": review.get("live_trading_allowed") is False,
        "strategy_registry_write_allowed_false": review.get("strategy_registry_write_allowed") is False,
        "promotion_allowed_false": review.get("promotion_allowed") is False,
    }


def _packet_blockers(review: Dict[str, Any], checklist: Dict[str, bool]) -> List[str]:
    blockers = list(review.get("readiness_blockers", []) or [])
    if not checklist.get("operator_review_required", False):
        blockers.append("OPERATOR_REVIEW_NOT_REQUIRED")
    if not checklist.get("manual_approval_required", False):
        blockers.append("MANUAL_APPROVAL_NOT_REQUIRED")
    for name, passed in checklist.items():
        if not passed and name.endswith("_present"):
            blockers.append(f"{name.upper()}_MISSING")
    if not checklist.get("paper_execution_upgrade_disabled", False):
        blockers.append("PAPER_EXECUTION_UPGRADE_NOT_DISABLED")
    if not checklist.get("paper_order_execution_disabled", False):
        blockers.append("PAPER_ORDER_EXECUTION_NOT_DISABLED")
    if not checklist.get("adapter_routing_disabled", False):
        blockers.append("ADAPTER_ROUTING_NOT_DISABLED")
    if not checklist.get("live_trading_disabled", False):
        blockers.append("LIVE_TRADING_NOT_DISABLED")
    return sorted(set(str(b) for b in blockers if str(b)))


def _packet_warnings(review: Dict[str, Any], checklist: Dict[str, bool]) -> List[str]:
    warnings = list(review.get("readiness_warnings", []) or [])
    if str(review.get("upgrade_readiness_status", "")) != "PAPER_EXECUTION_UPGRADE_REVIEW_READY":
        warnings.append("PACKET_CREATED_FOR_NON_READY_CANDIDATE_REVIEW_CONTEXT")
    if not checklist.get("upgrade_review_ready", False):
        warnings.append("UPGRADE_REVIEW_NOT_READY")
    warnings.append("REVIEW_ONLY_OPERATOR_APPROVAL_NOT_RECORDED")
    warnings.append("NO_EXECUTION_PERMISSION_GRANTED_BY_PACKET")
    return sorted(set(str(w) for w in warnings if str(w)))


def _packet_status(review: Dict[str, Any], blockers: List[str]) -> str:
    source_status = str(review.get("upgrade_readiness_status", ""))
    hard = {
        "PAPER_EXECUTION_UPGRADE_NOT_DISABLED",
        "PAPER_ORDER_EXECUTION_NOT_DISABLED",
        "ADAPTER_ROUTING_NOT_DISABLED",
        "LIVE_TRADING_NOT_DISABLED",
    }
    if any(blocker in hard for blocker in blockers):
        return "OPERATOR_PACKET_INVALID_SAFETY_BLOCK"
    if source_status == "PAPER_EXECUTION_UPGRADE_REVIEW_READY" and not blockers:
        return "OPERATOR_PACKET_REVIEW_READY"
    if source_status == "PAPER_EXECUTION_UPGRADE_BLOCKED":
        return "OPERATOR_PACKET_BLOCKED"
    return "OPERATOR_PACKET_WATCHLIST"


def _required_actions(status: str, blockers: List[str], warnings: List[str]) -> List[str]:
    actions = [
        "Review all evidence artifacts from Step210 through Step216.",
        "Confirm no paper execution or live trading permission is granted by this packet.",
    ]
    if status == "OPERATOR_PACKET_REVIEW_READY":
        actions.append("Manually approve or reject future Step218 paper execution enablement in a separate explicit step.")
    elif status == "OPERATOR_PACKET_WATCHLIST":
        actions.append("Collect more paper evidence or resolve watchlist warnings before future approval.")
    else:
        actions.append("Do not approve future paper execution enablement until blockers are resolved.")
    if blockers:
        actions.append("Resolve approval blockers before any future upgrade step.")
    if warnings:
        actions.append("Review warnings and document operator decision rationale.")
    return actions


def _packet_summary(review: Dict[str, Any], status: str) -> str:
    group = str(review.get("comparison_group", "UNKNOWN"))
    side = str(review.get("side", "UNKNOWN"))
    score = float(review.get("upgrade_readiness_score", 0.0))
    source = str(review.get("upgrade_readiness_status", "UNKNOWN"))
    return f"{group} {side} has source readiness {source} with upgrade score {score:.2f}; packet status is {status}. This packet is review-only and records no approval."


def _build_packet(review: Dict[str, Any]) -> OperatorApprovalPacket:
    checklist = _checklist(review)
    blockers = _packet_blockers(review, checklist)
    warnings = _packet_warnings(review, checklist)
    status = _packet_status(review, blockers)
    return OperatorApprovalPacket(
        approval_packet_id=_packet_id(review),
        upgrade_review_id=str(review.get("upgrade_review_id", "")),
        promotion_decision_id=str(review.get("promotion_decision_id", "")),
        feedback_review_id=str(review.get("feedback_review_id", "")),
        observation_id=str(review.get("observation_id", "")),
        registry_id=str(review.get("registry_id", "")),
        comparison_group=str(review.get("comparison_group", "")),
        side=str(review.get("side", "")),
        source_upgrade_readiness_status=str(review.get("upgrade_readiness_status", "")),
        upgrade_readiness_score=float(review.get("upgrade_readiness_score", 0.0)),
        promotion_readiness_score=float(review.get("promotion_readiness_score", 0.0)),
        evidence_completeness_score=float(review.get("evidence_completeness_score", 0.0)),
        packet_status=status,
        packet_summary=_packet_summary(review, status),
        approval_checklist=checklist,
        approval_blockers=blockers,
        approval_warnings=warnings,
        required_operator_actions=_required_actions(status, blockers, warnings),
        safety_attestations=_safety_attestations(review),
        packet_version=APPROVAL_PACKET_VERSION,
        created_at_utc=_utc_now(),
        manual_approval_required=True,
        operator_review_required=True,
        operator_approved=False,
        approval_recorded=False,
        paper_execution_upgrade_allowed=False,
        paper_order_execution_enabled=False,
        paper_trade_execution_enabled=False,
        adapter_routing_enabled=False,
        shadow_execution_enabled=False,
        limited_live_review_allowed=False,
        live_trading_allowed=False,
        strategy_registry_write_allowed=False,
        promotion_allowed=False,
        live_order_executed=False,
    )


def _blocker_summary(packets: List[OperatorApprovalPacket]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for packet in packets:
        if not packet.approval_blockers:
            out["NO_BLOCKER"] = out.get("NO_BLOCKER", 0) + 1
        for blocker in packet.approval_blockers:
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _result_hash_payload(result: Step217OperatorApprovalPacketResult) -> Dict[str, Any]:
    payload = result.to_dict()
    payload.pop("result_sha256", None)
    return payload


def _render_markdown(result: Step217OperatorApprovalPacketResult) -> str:
    lines = [
        "# Step217 v5 Operator Approval Packet Review-Only",
        "",
        "Step217 creates operator approval packets from Step216 paper execution upgrade readiness reviews.",
        "This step is review-only. It does not record approval, enable paper execution, route adapters, submit orders, allow limited-live review, write strategy registry state, send Telegram messages, or enable live trading.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- source_upgrade_review_count: {result.source_upgrade_review_count}",
        f"- approval_packet_count: {result.approval_packet_count}",
        f"- review_ready_packet_count: {result.review_ready_packet_count}",
        f"- watchlist_packet_count: {result.watchlist_packet_count}",
        f"- blocked_packet_count: {result.blocked_packet_count}",
        f"- operator_approved: {result.operator_approved}",
        f"- approval_recorded: {result.approval_recorded}",
        f"- paper_execution_upgrade_allowed: {result.paper_execution_upgrade_allowed}",
        f"- paper_order_execution_enabled: {result.paper_order_execution_enabled}",
        f"- adapter_routing_enabled: {result.adapter_routing_enabled}",
        f"- limited_live_review_allowed: {result.limited_live_review_allowed}",
        f"- live_trading_allowed: {result.live_trading_allowed}",
        "",
        "## Approval packets",
    ]
    for packet in result.packets:
        blockers = ", ".join(packet.get("approval_blockers", [])) if packet.get("approval_blockers") else "NO_BLOCKER"
        warnings = ", ".join(packet.get("approval_warnings", [])) if packet.get("approval_warnings") else "NO_WARNING"
        lines.append(
            "- `{group}` {side}: status={status}, upgrade_score={score:.2f}, evidence={evidence:.2f}, "
            "operator_approved={approved}, blockers={blockers}, warnings={warnings}".format(
                group=packet.get("comparison_group", ""),
                side=packet.get("side", ""),
                status=packet.get("packet_status", ""),
                score=float(packet.get("upgrade_readiness_score", 0.0)),
                evidence=float(packet.get("evidence_completeness_score", 0.0)),
                approved=packet.get("operator_approved", False),
                blockers=blockers,
                warnings=warnings,
            )
        )
    lines.extend(
        [
            "",
            "## Policy",
            "- Step217 creates operator packets only.",
            "- `operator_approved` remains false.",
            "- `approval_recorded` remains false.",
            "- Paper execution upgrade remains disabled.",
            "- Paper order execution, adapter routing, limited-live review, and live trading remain disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def execute_operator_approval_packet_review(root: str | Path, *, write_output: bool = True) -> Step217OperatorApprovalPacketResult:
    root_path = Path(root).resolve()
    step216_path = root_path / "storage/latest/step216_paper_execution_upgrade_readiness_review_latest.json"
    step216 = _ensure_step216(root_path)
    reviews = _load_step216_reviews(step216)
    packets = [_build_packet(review) for review in reviews]
    packet_dicts = [packet.to_dict() for packet in packets]

    approval_packets_json_path = root_path / "data/reports/step217_operator_approval_packets.json"
    approval_packets_jsonl_path = root_path / "data/stores/step217_operator_approval_packets.jsonl"
    approval_packets_csv_path = root_path / "data/reports/step217_operator_approval_packets.csv"
    markdown_report_path = root_path / "data/reports/step217_operator_approval_packet_review_report.md"
    latest_result_path = root_path / "storage/latest/step217_operator_approval_packet_review_latest.json"

    result = Step217OperatorApprovalPacketResult(
        status=STEP217_STATUS_OK,
        root=str(root_path),
        source_step216_result_path=str(step216_path),
        approval_packets_json_path=str(approval_packets_json_path),
        approval_packets_jsonl_path=str(approval_packets_jsonl_path),
        approval_packets_csv_path=str(approval_packets_csv_path),
        markdown_report_path=str(markdown_report_path),
        latest_result_path=str(latest_result_path),
        source_upgrade_review_count=len(reviews),
        approval_packet_count=len(packets),
        review_ready_packet_count=sum(1 for packet in packets if packet.packet_status == "OPERATOR_PACKET_REVIEW_READY"),
        watchlist_packet_count=sum(1 for packet in packets if packet.packet_status == "OPERATOR_PACKET_WATCHLIST"),
        blocked_packet_count=sum(1 for packet in packets if packet.packet_status in {"OPERATOR_PACKET_BLOCKED", "OPERATOR_PACKET_INVALID_SAFETY_BLOCK"}),
        operator_approval_packet_created=True,
        operator_packet_review_only=True,
        manual_approval_required=True,
        operator_review_required=True,
        operator_approved=False,
        approval_recorded=False,
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
        packets=packet_dicts,
        blocker_summary=_blocker_summary(packets),
    )
    result.result_sha256 = _sha256_text(_canonical_json(_result_hash_payload(result)))

    if write_output:
        _write_json(approval_packets_json_path, {"packets": packet_dicts})
        _write_jsonl(approval_packets_jsonl_path, packet_dicts)
        _write_csv(approval_packets_csv_path, packet_dicts)
        markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_report_path.write_text(_render_markdown(result), encoding="utf-8")
        _write_json(latest_result_path, result.to_dict())
    return result


def validate_operator_approval_packet_review(root: str | Path) -> Step217ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step217_operator_approval_packet_review_latest.json"
    if not result_path.exists():
        execute_operator_approval_packet_review(root_path, write_output=True)

    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256_text(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    packets = list(payload.get("packets", []) or [])

    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step216_present": Path(payload.get("source_step216_result_path", "")).exists(),
        "approval_packets_json_exists": Path(payload.get("approval_packets_json_path", "")).exists(),
        "approval_packets_jsonl_exists": Path(payload.get("approval_packets_jsonl_path", "")).exists(),
        "approval_packets_csv_exists": Path(payload.get("approval_packets_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_upgrade_reviews_present": int(payload.get("source_upgrade_review_count", 0)) > 0,
        "approval_packets_present": int(payload.get("approval_packet_count", 0)) > 0 and bool(packets),
        "operator_approval_packet_created": payload.get("operator_approval_packet_created") is True,
        "review_only_mode": payload.get("operator_packet_review_only") is True,
        "manual_approval_required": payload.get("manual_approval_required") is True and all(packet.get("manual_approval_required") is True for packet in packets),
        "operator_review_required": payload.get("operator_review_required") is True and all(packet.get("operator_review_required") is True for packet in packets),
        "no_operator_approval_recorded": payload.get("operator_approved") is False
        and payload.get("approval_recorded") is False
        and all(packet.get("operator_approved") is False for packet in packets)
        and all(packet.get("approval_recorded") is False for packet in packets),
        "no_paper_execution_upgrade": payload.get("paper_execution_upgrade_allowed") is False and all(packet.get("paper_execution_upgrade_allowed") is False for packet in packets),
        "no_paper_order_execution": payload.get("paper_order_execution_enabled") is False and all(packet.get("paper_order_execution_enabled") is False for packet in packets),
        "no_adapter_routing": payload.get("adapter_routing_enabled") is False and all(packet.get("adapter_routing_enabled") is False for packet in packets),
        "no_shadow_execution": payload.get("shadow_execution_enabled") is False and all(packet.get("shadow_execution_enabled") is False for packet in packets),
        "no_limited_live_review": payload.get("limited_live_review_allowed") is False and all(packet.get("limited_live_review_allowed") is False for packet in packets),
        "no_live_trading": payload.get("live_trading_allowed") is False and all(packet.get("live_trading_allowed") is False for packet in packets),
        "no_strategy_registry_write": payload.get("strategy_registry_write_allowed") is False and all(packet.get("strategy_registry_write_allowed") is False for packet in packets),
        "no_promotion_allowed": payload.get("promotion_allowed") is False and all(packet.get("promotion_allowed") is False for packet in packets),
        "no_auto_strategy_promotion": payload.get("auto_strategy_promotion") is False,
        "no_external_api_calls": payload.get("external_api_call_performed") is False,
        "no_live_side_effects": payload.get("live_order_executed") is False
        and payload.get("real_adapter_call_performed") is False
        and payload.get("telegram_real_send") is False
        and all(packet.get("live_order_executed") is False for packet in packets),
        "no_production_cutover": payload.get("production_cutover_executable") is False
        and payload.get("live_mode_enable_allowed") is False,
    }
    failures = [name for name, ok in checks.items() if not ok]
    return Step217ValidationResult(
        status=STEP217_VALIDATION_OK if not failures else "STEP217_V5_OPERATOR_APPROVAL_PACKET_REVIEW_ONLY_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )

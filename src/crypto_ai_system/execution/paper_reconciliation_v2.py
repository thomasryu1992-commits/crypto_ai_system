from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.trading.order_id_chain import (
    ORDER_ID_CHAIN_VERSION,
    chain_complete,
    missing_chain_fields,
)
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

PAPER_RECONCILIATION_VERSION = "step295_paper_reconciliation_v2"
PAPER_RECONCILIATION_REGISTRY_NAME = "paper_reconciliation_registry"

STATUS_RECONCILED = "RECONCILED"
STATUS_RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"
STATUS_RECONCILIATION_BLOCKED_NO_EXECUTION = "RECONCILIATION_BLOCKED_NO_EXECUTION"
STATUS_RECONCILIATION_NOT_REQUIRED = "RECONCILIATION_NOT_REQUIRED"
STATUS_UNSAFE_LIVE_SIDE_EFFECT = "UNSAFE_LIVE_SIDE_EFFECT"

PROMOTION_BLOCKER_NONE = "NO_PROMOTION_BLOCKER"
PROMOTION_BLOCKER_MISMATCH = "BLOCK_PROMOTION_RECONCILIATION_MISMATCH"
PROMOTION_BLOCKER_NO_EVIDENCE = "BLOCK_PROMOTION_RECONCILIATION_EVIDENCE_MISSING"
PROMOTION_BLOCKER_UNSAFE_SIDE_EFFECT = "BLOCK_PROMOTION_UNSAFE_LIVE_SIDE_EFFECT"

LIVE_POSITION_SYNC_ENABLED_BY_THIS_MODULE = False
EXTERNAL_EXECUTION_SYNC_PERFORMED = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED = False
LIVE_ORDER_EXECUTED = False


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in {None, ""}:
            return default
        return float(value)
    except Exception:
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _latest_path(cfg: AppConfig, name: str) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    base = Path(raw)
    if not base.is_absolute():
        base = cfg.root / base
    base.mkdir(parents=True, exist_ok=True)
    return base / name


def _check(name: str, passed: bool, ok: str, bad: str, *, severity: str = "mismatch") -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "severity": severity,
        "message": ok if passed else bad,
    }


def _expected_side(intent: Mapping[str, Any]) -> str:
    explicit = _text(intent.get("side")).upper()
    if explicit:
        return explicit
    direction = _text(intent.get("direction")).upper()
    if direction in {"LONG", "BUY"}:
        return "BUY"
    if direction in {"SHORT", "SELL"}:
        return "SELL"
    return ""


def _position_side(position_delta: Mapping[str, Any]) -> str:
    return _text(position_delta.get("side")).upper()


def _quantity_delta_abs(position_delta: Mapping[str, Any]) -> float:
    return abs(_float(position_delta.get("quantity_delta"), 0.0))


def _live_side_effect_detected(record: Mapping[str, Any]) -> bool:
    objects = [record, record.get("expected_order_intent") or {}, record.get("simulated_execution") or {}]
    for obj in objects:
        if isinstance(obj, Mapping):
            if obj.get("external_order_submission_performed") is True:
                return True
            if obj.get("live_order_executed") is True:
                return True
            if obj.get("adapter_called") is True:
                return True
            if obj.get("real_exchange_order_id") not in {None, ""}:
                return True
    return False


def build_reconciliation_checks(paper_execution_record: Mapping[str, Any]) -> list[dict[str, Any]]:
    record = dict(paper_execution_record or {})
    intent = dict(record.get("expected_order_intent") or {})
    execution = dict(record.get("simulated_execution") or {})
    fill = dict(record.get("simulated_fill") or {})
    position_delta = dict(record.get("position_delta") or {})
    fee_model = dict(record.get("fee_model") or {})
    slippage_model = dict(record.get("slippage_model") or {})

    requested_quantity = _float(intent.get("quantity"), 0.0)
    filled_quantity = _float(fill.get("filled_quantity"), 0.0)
    fill_ratio = _float(fill.get("fill_ratio"), 0.0)
    expected_fill_ratio = filled_quantity / requested_quantity if requested_quantity > 0 else 0.0
    fill_status = _text(fill.get("fill_status")).upper()
    terminal_state = _text(record.get("state")).upper()

    checks = [
        _check(
            "PAPER_EXECUTION_RECORD_EXISTS",
            bool(record),
            "Paper execution record exists.",
            "Paper execution record is missing.",
            severity="fatal",
        ),
        _check(
            "EXPECTED_ORDER_INTENT_EXISTS",
            bool(intent),
            "Expected order intent exists.",
            "Expected order intent is missing.",
            severity="fatal",
        ),
        _check(
            "SIMULATED_EXECUTION_EXISTS",
            bool(execution),
            "Simulated execution exists.",
            "Simulated execution is missing.",
            severity="fatal",
        ),
        _check(
            "SIMULATED_FILL_EXISTS",
            bool(fill),
            "Simulated fill exists.",
            "Simulated fill is missing.",
            severity="fatal",
        ),
        _check(
            "ORDER_INTENT_ID_MATCH",
            bool(_text(record.get("order_intent_id"))) and _text(record.get("order_intent_id")) == _text(intent.get("order_intent_id")) == _text(execution.get("order_intent_id")) == _text(fill.get("order_intent_id")),
            "Order intent ID matches across intent, execution, and fill.",
            "Order intent ID mismatch across paper execution evidence.",
        ),
        _check(
            "EXECUTION_ID_MATCH",
            bool(_text(record.get("execution_id"))) and _text(record.get("execution_id")) == _text(execution.get("execution_id")) == _text(fill.get("execution_id")),
            "Execution ID matches across record, execution, and fill.",
            "Execution ID mismatch across paper execution evidence.",
        ),
        _check(
            "DECISION_ID_PRESENT",
            bool(_text(record.get("decision_id"))),
            "Decision ID is present.",
            "Decision ID is missing.",
        ),
        _check(
            "RISK_GATE_ID_PRESENT",
            bool(_text(record.get("risk_gate_id"))),
            "Risk gate ID is present.",
            "Risk gate ID is missing.",
        ),
        _check(
            "FILL_STATUS_VALID",
            fill_status in {"FILLED", "PARTIALLY_FILLED", "NO_FILL"},
            "Fill status is valid.",
            "Fill status is invalid.",
        ),
        _check(
            "FILLED_QUANTITY_WITHIN_REQUESTED",
            filled_quantity <= requested_quantity + 1e-12,
            "Filled quantity does not exceed requested quantity.",
            "Filled quantity exceeds requested quantity.",
        ),
        _check(
            "FILL_RATIO_CONSISTENT",
            abs(fill_ratio - expected_fill_ratio) <= 1e-9 or fill_status == "NO_FILL",
            "Fill ratio is consistent with requested and filled quantity.",
            "Fill ratio does not match requested and filled quantity.",
        ),
        _check(
            "POSITION_DELTA_MATCHES_FILL",
            abs(_quantity_delta_abs(position_delta) - filled_quantity) <= 1e-12,
            "Position delta quantity matches filled quantity.",
            "Position delta quantity does not match filled quantity.",
        ),
        _check(
            "POSITION_SIDE_MATCHES_INTENT",
            fill_status == "NO_FILL" or _position_side(position_delta) == _expected_side(intent),
            "Position delta side matches expected order side.",
            "Position delta side does not match expected order side.",
        ),
        _check(
            "FEE_MODEL_PRESENT",
            bool(fee_model.get("fee_model_used") is True and fee_model.get("fee_model_version")),
            "Fee model evidence is present.",
            "Fee model evidence is missing.",
        ),
        _check(
            "SLIPPAGE_MODEL_PRESENT",
            bool(slippage_model.get("slippage_model_used") is True and slippage_model.get("slippage_model_version")),
            "Slippage model evidence is present.",
            "Slippage model evidence is missing.",
        ),
        _check(
            "LIFECYCLE_REACHED_RECONCILIATION",
            terminal_state == "PENDING_RECONCILIATION" or _text(record.get("status")) in {"PAPER_CANCELLED", "PAPER_REJECTED"},
            "Paper lifecycle reached a reconciliation boundary.",
            "Paper lifecycle has not reached a reconciliation boundary.",
        ),
        _check(
            "PAPER_EXECUTION_HASH_PRESENT",
            bool(_text(record.get("paper_execution_record_sha256"))),
            "Paper execution record hash is present.",
            "Paper execution record hash is missing.",
        ),
        _check(
            "NO_LIVE_SIDE_EFFECTS",
            not _live_side_effect_detected(record),
            "No live/external side-effect flags detected.",
            "Unsafe live/external side-effect flag detected.",
            severity="fatal",
        ),
    ]
    return checks


def _status_from_checks(record: Mapping[str, Any], checks: list[dict[str, Any]]) -> str:
    if not record:
        return STATUS_RECONCILIATION_BLOCKED_NO_EXECUTION
    if any(c["name"] == "NO_LIVE_SIDE_EFFECTS" and not c["passed"] for c in checks):
        return STATUS_UNSAFE_LIVE_SIDE_EFFECT
    if _text(record.get("status")) in {"PAPER_REJECTED", "PAPER_CANCELLED"} and not record.get("reconciliation_required"):
        return STATUS_RECONCILIATION_NOT_REQUIRED
    if all(c.get("passed") for c in checks):
        return STATUS_RECONCILED
    return STATUS_RECONCILIATION_MISMATCH


def _promotion_blocker(status: str) -> str:
    if status == STATUS_RECONCILED:
        return PROMOTION_BLOCKER_NONE
    if status == STATUS_RECONCILIATION_BLOCKED_NO_EXECUTION:
        return PROMOTION_BLOCKER_NO_EVIDENCE
    if status == STATUS_UNSAFE_LIVE_SIDE_EFFECT:
        return PROMOTION_BLOCKER_UNSAFE_SIDE_EFFECT
    return PROMOTION_BLOCKER_MISMATCH


@dataclass
class PaperReconciliationRecord:
    paper_reconciliation_id: str
    reconciliation_id: str
    paper_execution_id: str
    execution_id: str
    order_intent_id: str
    decision_id: str
    risk_gate_id: str
    research_signal_id: str
    profile_id: str
    status: str
    reconciliation_status: str
    reconciled: bool
    reconciliation_mismatch: bool
    mismatch_reasons: list[str]
    checks: list[dict[str, Any]]
    expected_order_intent: dict[str, Any]
    simulated_execution: dict[str, Any]
    simulated_fill: dict[str, Any]
    position_delta: dict[str, Any]
    fee_model: dict[str, Any]
    slippage_model: dict[str, Any]
    paper_execution_record_sha256: str | None
    reconciliation_evidence_hash: str
    promotion_blocked: bool
    promotion_blocker: str
    order_id_chain_version: str = ORDER_ID_CHAIN_VERSION
    paper_reconciliation_version: str = PAPER_RECONCILIATION_VERSION
    live_position_sync_enabled_by_this_module: bool = LIVE_POSITION_SYNC_ENABLED_BY_THIS_MODULE
    external_execution_sync_performed: bool = EXTERNAL_EXECUTION_SYNC_PERFORMED
    external_order_submission_performed: bool = EXTERNAL_ORDER_SUBMISSION_PERFORMED
    live_order_executed: bool = LIVE_ORDER_EXECUTED
    runtime_settings_mutated: bool = False
    score_weights_mutated: bool = False
    created_at_utc: str = field(default_factory=utc_now_canonical)
    paper_reconciliation_record_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if not payload.get("paper_reconciliation_record_sha256"):
            payload["paper_reconciliation_record_sha256"] = sha256_json({k: v for k, v in payload.items() if k != "paper_reconciliation_record_sha256"})
        return payload


def reconcile_paper_execution_record(paper_execution_record: Mapping[str, Any]) -> dict[str, Any]:
    record = dict(paper_execution_record or {})
    checks = build_reconciliation_checks(record)
    status = _status_from_checks(record, checks)
    mismatch_reasons = [c["name"] for c in checks if not c.get("passed")]
    reconciled = status == STATUS_RECONCILED
    blocker = _promotion_blocker(status)
    evidence_payload = {
        "paper_execution_id": record.get("paper_execution_id"),
        "execution_id": record.get("execution_id"),
        "order_intent_id": record.get("order_intent_id"),
        "paper_execution_record_sha256": record.get("paper_execution_record_sha256"),
        "expected_order_intent": record.get("expected_order_intent") or {},
        "simulated_execution": record.get("simulated_execution") or {},
        "simulated_fill": record.get("simulated_fill") or {},
        "position_delta": record.get("position_delta") or {},
        "fee_model": record.get("fee_model") or {},
        "slippage_model": record.get("slippage_model") or {},
        "checks": checks,
        "status": status,
    }
    evidence_hash = sha256_json(evidence_payload)
    reconciliation_id = stable_id(
        "reconciliation",
        {
            "paper_execution_id": record.get("paper_execution_id"),
            "execution_id": record.get("execution_id"),
            "order_intent_id": record.get("order_intent_id"),
            "evidence_hash": evidence_hash,
        },
        24,
    )
    paper_reconciliation_id = stable_id(
        "paper_reconciliation",
        {"reconciliation_id": reconciliation_id, "status": status, "mismatch_reasons": mismatch_reasons},
        24,
    )
    output = PaperReconciliationRecord(
        paper_reconciliation_id=paper_reconciliation_id,
        reconciliation_id=reconciliation_id,
        paper_execution_id=_text(record.get("paper_execution_id")),
        execution_id=_text(record.get("execution_id")),
        order_intent_id=_text(record.get("order_intent_id")),
        decision_id=_text(record.get("decision_id")),
        risk_gate_id=_text(record.get("risk_gate_id")),
        research_signal_id=_text(record.get("research_signal_id")),
        profile_id=_text(record.get("profile_id")),
        status=status,
        reconciliation_status=status,
        reconciled=reconciled,
        reconciliation_mismatch=not reconciled,
        mismatch_reasons=mismatch_reasons,
        checks=checks,
        expected_order_intent=dict(record.get("expected_order_intent") or {}),
        simulated_execution=dict(record.get("simulated_execution") or {}),
        simulated_fill=dict(record.get("simulated_fill") or {}),
        position_delta=dict(record.get("position_delta") or {}),
        fee_model=dict(record.get("fee_model") or {}),
        slippage_model=dict(record.get("slippage_model") or {}),
        paper_execution_record_sha256=record.get("paper_execution_record_sha256"),
        reconciliation_evidence_hash=evidence_hash,
        promotion_blocked=blocker != PROMOTION_BLOCKER_NONE,
        promotion_blocker=blocker,
        external_order_submission_performed=_live_side_effect_detected(record),
        live_order_executed=bool(record.get("live_order_executed") is True),
    ).to_dict()
    return output


def build_paper_reconciliation_registry_record(reconciliation: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(reconciliation or {})
    chain_payload = {
        "research_signal_id": payload.get("research_signal_id"),
        "decision_id": payload.get("decision_id"),
        "risk_gate_id": payload.get("risk_gate_id"),
        "order_intent_id": payload.get("order_intent_id"),
        "execution_id": payload.get("execution_id"),
        "reconciliation_id": payload.get("reconciliation_id"),
    }
    registry_record = {
        "paper_reconciliation_registry_version": PAPER_RECONCILIATION_VERSION,
        "order_id_chain_version": ORDER_ID_CHAIN_VERSION,
        "paper_reconciliation_id": payload.get("paper_reconciliation_id"),
        "reconciliation_id": payload.get("reconciliation_id"),
        "paper_execution_id": payload.get("paper_execution_id"),
        "execution_id": payload.get("execution_id"),
        "order_intent_id": payload.get("order_intent_id"),
        "decision_id": payload.get("decision_id"),
        "risk_gate_id": payload.get("risk_gate_id"),
        "research_signal_id": payload.get("research_signal_id"),
        "profile_id": payload.get("profile_id"),
        "status": payload.get("status"),
        "reconciliation_status": payload.get("reconciliation_status"),
        "reconciled": payload.get("reconciled"),
        "reconciliation_mismatch": payload.get("reconciliation_mismatch"),
        "mismatch_reasons": payload.get("mismatch_reasons", []),
        "mismatch_count": len(payload.get("mismatch_reasons", []) or []),
        "promotion_blocked": payload.get("promotion_blocked"),
        "promotion_blocker": payload.get("promotion_blocker"),
        "reconciliation_evidence_hash": payload.get("reconciliation_evidence_hash"),
        "paper_execution_record_sha256": payload.get("paper_execution_record_sha256"),
        "reconciliation_chain_complete": chain_complete(chain_payload, through="reconciliation"),
        "missing_reconciliation_chain_fields": missing_chain_fields(chain_payload, through="reconciliation"),
        "live_position_sync_enabled_by_this_module": payload.get("live_position_sync_enabled_by_this_module"),
        "external_execution_sync_performed": payload.get("external_execution_sync_performed"),
        "external_order_submission_performed": payload.get("external_order_submission_performed"),
        "live_order_executed": payload.get("live_order_executed"),
        "runtime_settings_mutated": payload.get("runtime_settings_mutated"),
        "score_weights_mutated": payload.get("score_weights_mutated"),
        "created_at_utc": payload.get("created_at_utc") or utc_now_canonical(),
    }
    registry_record["paper_reconciliation_registry_record_id"] = stable_id("paper_reconciliation_registry", registry_record, 24)
    registry_record["paper_reconciliation_registry_record_sha256"] = sha256_json(registry_record)
    return registry_record


def persist_paper_reconciliation_record(cfg: AppConfig, reconciliation: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(reconciliation)
    atomic_write_json(_latest_path(cfg, "paper_reconciliation_record.json"), payload)
    registry_record = build_paper_reconciliation_registry_record(payload)
    persisted = append_registry_record(
        registry_path(cfg, PAPER_RECONCILIATION_REGISTRY_NAME),
        registry_record,
        registry_name=PAPER_RECONCILIATION_REGISTRY_NAME,
        id_field="paper_reconciliation_registry_record_id",
        hash_field="paper_reconciliation_registry_record_sha256",
        id_prefix="paper_reconciliation_registry",
    )
    atomic_write_json(_latest_path(cfg, "paper_reconciliation_registry_record.json"), persisted)
    payload["paper_reconciliation_registry_record_id"] = persisted.get("paper_reconciliation_registry_record_id")
    payload["paper_reconciliation_registry_record_sha256"] = persisted.get("paper_reconciliation_registry_record_sha256")
    atomic_write_json(_latest_path(cfg, "paper_reconciliation_record.json"), payload)
    return persisted


def reconcile_and_persist_paper_execution(
    paper_execution_record: Mapping[str, Any],
    *,
    cfg: AppConfig | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(".")
    reconciliation = reconcile_paper_execution_record(paper_execution_record)
    registry_record = persist_paper_reconciliation_record(cfg, reconciliation)
    reconciliation["paper_reconciliation_registry_record_id"] = registry_record.get("paper_reconciliation_registry_record_id")
    reconciliation["paper_reconciliation_registry_record_sha256"] = registry_record.get("paper_reconciliation_registry_record_sha256")
    atomic_write_json(_latest_path(cfg, "paper_reconciliation_record.json"), reconciliation)
    return reconciliation


def reconcile_latest_paper_execution(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(".")
    paper_execution_record = read_json(_latest_path(cfg, "paper_execution_record.json"), default={})
    if not isinstance(paper_execution_record, dict) or not paper_execution_record:
        result = reconcile_paper_execution_record({})
        persist_paper_reconciliation_record(cfg, result)
        return result
    return reconcile_and_persist_paper_execution(paper_execution_record, cfg=cfg)

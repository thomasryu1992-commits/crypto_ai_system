from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import (
    append_registry_record,
    load_registry_records,
    registry_path,
)
from crypto_ai_system.trading.order_id_chain import (
    ORDER_ID_CHAIN_VERSION,
    chain_complete,
    feedback_cycle_id_from_outcome,
    missing_chain_fields,
    outcome_id_from_reconciliation,
)
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

OUTCOME_ANALYTICS_VERSION = "step296_outcome_analytics_v2"
OUTCOME_FEEDBACK_REGISTRY_NAME = "outcome_feedback_registry"

STATUS_OUTCOME_RECORDED = "OUTCOME_RECORDED"
STATUS_OUTCOME_REVIEW_ONLY_OPEN_POSITION = "OUTCOME_REVIEW_ONLY_OPEN_POSITION"
STATUS_OUTCOME_BLOCKED_RECONCILIATION_MISMATCH = "OUTCOME_BLOCKED_RECONCILIATION_MISMATCH"
STATUS_OUTCOME_BLOCKED_RECONCILIATION_EVIDENCE_MISSING = "OUTCOME_BLOCKED_RECONCILIATION_EVIDENCE_MISSING"
STATUS_OUTCOME_BLOCKED_UNSAFE_LIVE_SIDE_EFFECT = "OUTCOME_BLOCKED_UNSAFE_LIVE_SIDE_EFFECT"

NEXT_REPEAT_IN_PAPER = "repeat_in_paper"
NEXT_EXPAND_TEST_COVERAGE = "expand_test_coverage"
NEXT_IMPROVE_CANDIDATE_PROFILE = "improve_candidate_profile"
NEXT_DROP_CANDIDATE_PROFILE = "drop_candidate_profile"
NEXT_CREATE_PERFORMANCE_REPORT = "create_performance_report"
NEXT_ARCHIVE = "archive"

LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE = False
SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE = False
AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE = False


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


def _side(reconciliation: Mapping[str, Any]) -> str:
    intent = reconciliation.get("expected_order_intent") or {}
    side = _text(intent.get("side")).upper()
    if side:
        return side
    direction = _text(intent.get("direction")).upper()
    if direction in {"LONG", "BUY"}:
        return "BUY"
    if direction in {"SHORT", "SELL"}:
        return "SELL"
    return "UNKNOWN"


def _entry_price(reconciliation: Mapping[str, Any]) -> float:
    intent = reconciliation.get("expected_order_intent") or {}
    fill = reconciliation.get("simulated_fill") or {}
    return _float(intent.get("entry_price") or intent.get("price") or fill.get("avg_fill_price"), 0.0)


def _quantity(reconciliation: Mapping[str, Any]) -> float:
    intent = reconciliation.get("expected_order_intent") or {}
    fill = reconciliation.get("simulated_fill") or {}
    return _float(fill.get("filled_quantity") or intent.get("quantity"), 0.0)


def _risk_per_unit(reconciliation: Mapping[str, Any]) -> float:
    intent = reconciliation.get("expected_order_intent") or {}
    entry = _entry_price(reconciliation)
    stop = _float(intent.get("stop_loss"), 0.0)
    if entry > 0 and stop > 0:
        return abs(entry - stop)
    explicit = _float(intent.get("risk_per_unit"), 0.0)
    return max(0.0, explicit)


def _derive_result_r(reconciliation: Mapping[str, Any], context: Mapping[str, Any]) -> tuple[float, bool, str]:
    explicit = context.get("result_R", context.get("result_r", context.get("simulated_close_r", context.get("close_r"))))
    if explicit not in {None, ""}:
        return round(_float(explicit), 8), True, _text(context.get("close_reason") or "explicit_result_R")

    exit_price = context.get("exit_price", context.get("close_price"))
    if exit_price in {None, ""}:
        return 0.0, False, "open_or_unclosed_position"

    entry = _entry_price(reconciliation)
    risk = _risk_per_unit(reconciliation)
    if entry <= 0 or risk <= 0:
        return 0.0, False, "missing_entry_or_stop_for_R_multiple"

    exit_f = _float(exit_price)
    if _side(reconciliation) in {"SELL", "SHORT"}:
        result_r = (entry - exit_f) / risk
    else:
        result_r = (exit_f - entry) / risk
    return round(result_r, 8), True, _text(context.get("close_reason") or "derived_from_exit_price")


def _derive_pnl(reconciliation: Mapping[str, Any], context: Mapping[str, Any], result_r: float) -> float:
    explicit = context.get("pnl", context.get("pnl_usdt"))
    if explicit not in {None, ""}:
        return round(_float(explicit), 8)
    qty = _quantity(reconciliation)
    risk = _risk_per_unit(reconciliation)
    if qty > 0 and risk > 0:
        return round(result_r * qty * risk, 8)
    return 0.0


def _max_drawdown_from_single(result_r: float) -> float:
    return round(abs(min(0.0, result_r)), 8)


def _signal_drift(reconciliation: Mapping[str, Any], context: Mapping[str, Any], result_r: float, outcome_closed: bool) -> float:
    explicit = context.get("signal_to_outcome_drift")
    if explicit not in {None, ""}:
        return round(_float(explicit), 8)
    if not outcome_closed:
        return 0.0
    permission = _text(context.get("permission_result") or context.get("research_permission") or "").lower()
    if not permission:
        intent = reconciliation.get("expected_order_intent") or {}
        permission = _text(intent.get("permission_result") or intent.get("risk_level") or "").lower()
    if "block" in permission and result_r > 0:
        return 1.0
    if "allow" in permission and result_r < 0:
        return abs(result_r)
    return 0.0


def _paper_live_gap(context: Mapping[str, Any]) -> str | float:
    explicit = context.get("paper_live_gap")
    if explicit not in {None, ""}:
        return explicit
    paper = context.get("paper_fill_price")
    live = context.get("live_fill_price")
    if paper in {None, ""} or live in {None, ""}:
        return "not_applicable"
    paper_f = _float(paper)
    live_f = _float(live)
    if paper_f <= 0:
        return "not_applicable"
    return round(((live_f - paper_f) / paper_f) * 10_000.0, 8)


def _status(reconciliation: Mapping[str, Any], outcome_closed: bool) -> str:
    if not reconciliation:
        return STATUS_OUTCOME_BLOCKED_RECONCILIATION_EVIDENCE_MISSING
    if reconciliation.get("external_order_submission_performed") is True or reconciliation.get("live_order_executed") is True:
        return STATUS_OUTCOME_BLOCKED_UNSAFE_LIVE_SIDE_EFFECT
    if reconciliation.get("reconciled") is not True or reconciliation.get("reconciliation_mismatch") is True:
        return STATUS_OUTCOME_BLOCKED_RECONCILIATION_MISMATCH
    if not outcome_closed:
        return STATUS_OUTCOME_REVIEW_ONLY_OPEN_POSITION
    return STATUS_OUTCOME_RECORDED


def _next_action(status: str, result_r: float, outcome_closed: bool, sample_size: int = 1) -> str:
    if status in {STATUS_OUTCOME_BLOCKED_RECONCILIATION_EVIDENCE_MISSING, STATUS_OUTCOME_BLOCKED_UNSAFE_LIVE_SIDE_EFFECT}:
        return NEXT_EXPAND_TEST_COVERAGE
    if status == STATUS_OUTCOME_BLOCKED_RECONCILIATION_MISMATCH:
        return NEXT_EXPAND_TEST_COVERAGE
    if not outcome_closed:
        return NEXT_REPEAT_IN_PAPER
    if sample_size < 3:
        return NEXT_REPEAT_IN_PAPER
    if result_r < -1.0:
        return NEXT_DROP_CANDIDATE_PROFILE
    if result_r < 0:
        return NEXT_IMPROVE_CANDIDATE_PROFILE
    return NEXT_CREATE_PERFORMANCE_REPORT


@dataclass
class OutcomeAnalyticsRecord:
    outcome_id: str
    feedback_cycle_id: str
    profile_id: str
    research_signal_id: str
    decision_id: str
    risk_gate_id: str
    order_intent_id: str
    execution_id: str
    reconciliation_id: str
    status: str
    outcome_closed: bool
    close_reason: str
    regime: str
    direction: str
    strategy_id: str
    book_id: str
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: float | None
    result_R: float
    pnl: float
    expectancy: float
    win_loss: str
    win_loss_ratio: float
    average_R: float
    max_drawdown: float
    slippage: float
    latency_ms: float
    rejection_rate: float
    stale_data_rate: float
    signal_to_outcome_drift: float
    paper_live_gap: str | float
    api_error_rate: float
    manual_override_count: int
    next_action: str
    reconciliation_status: str
    reconciliation_mismatch: bool
    reconciliation_evidence_hash: str
    paper_reconciliation_record_sha256: str | None
    outcome_quality_warnings: list[str]
    order_id_chain_version: str = ORDER_ID_CHAIN_VERSION
    outcome_analytics_version: str = OUTCOME_ANALYTICS_VERSION
    live_trading_allowed_by_this_module: bool = LIVE_TRADING_ALLOWED_BY_THIS_MODULE
    runtime_settings_mutated: bool = RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE
    score_weights_mutated: bool = SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE
    auto_promotion_allowed: bool = AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE
    created_at_utc: str = field(default_factory=utc_now_canonical)
    outcome_record_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if not payload.get("outcome_record_sha256"):
            payload["outcome_record_sha256"] = sha256_json({k: v for k, v in payload.items() if k != "outcome_record_sha256"})
        return payload


def analyze_paper_reconciliation_outcome(
    reconciliation: Mapping[str, Any],
    *,
    outcome_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rec = dict(reconciliation or {})
    ctx = dict(outcome_context or {})
    result_r, closed, close_reason = _derive_result_r(rec, ctx)
    status = _status(rec, closed)
    if status != STATUS_OUTCOME_RECORDED and status != STATUS_OUTCOME_REVIEW_ONLY_OPEN_POSITION:
        closed = False
    pnl = _derive_pnl(rec, ctx, result_r if closed else 0.0)

    intent = dict(rec.get("expected_order_intent") or {})
    fill = dict(rec.get("simulated_fill") or {})
    slippage_model = dict(rec.get("slippage_model") or {})
    direction = _text(intent.get("direction") or _side(rec))
    profile_id = _text(rec.get("profile_id"))
    research_signal_id = _text(rec.get("research_signal_id"))
    reconciliation_id = _text(rec.get("reconciliation_id"))
    outcome_id = outcome_id_from_reconciliation(reconciliation_id, result_r if closed else 0.0, close_reason)
    feedback_cycle_id = feedback_cycle_id_from_outcome(outcome_id, profile_id=profile_id, research_signal_id=research_signal_id)

    if status.startswith("OUTCOME_BLOCKED"):
        result_r = 0.0
        pnl = 0.0

    win_loss = "open"
    if closed:
        if result_r > 0:
            win_loss = "win"
        elif result_r < 0:
            win_loss = "loss"
        else:
            win_loss = "breakeven"
    win_loss_ratio = 1.0 if win_loss == "win" else 0.0
    if win_loss == "breakeven":
        win_loss_ratio = 0.5

    warnings: list[str] = []
    if not rec:
        warnings.append("RECONCILIATION_EVIDENCE_MISSING")
    if rec and rec.get("reconciled") is not True:
        warnings.append("RECONCILIATION_NOT_RECONCILED")
    if rec and rec.get("reconciliation_mismatch") is True:
        warnings.append("RECONCILIATION_MISMATCH")
    if not closed and status == STATUS_OUTCOME_REVIEW_ONLY_OPEN_POSITION:
        warnings.append("OUTCOME_NOT_CLOSED")
    if not _text(rec.get("reconciliation_evidence_hash")):
        warnings.append("RECONCILIATION_EVIDENCE_HASH_MISSING")

    record = OutcomeAnalyticsRecord(
        outcome_id=outcome_id,
        feedback_cycle_id=feedback_cycle_id,
        profile_id=profile_id,
        research_signal_id=research_signal_id,
        decision_id=_text(rec.get("decision_id")),
        risk_gate_id=_text(rec.get("risk_gate_id")),
        order_intent_id=_text(rec.get("order_intent_id")),
        execution_id=_text(rec.get("execution_id")),
        reconciliation_id=reconciliation_id,
        status=status,
        outcome_closed=closed,
        close_reason=close_reason,
        regime=_text(ctx.get("regime") or ctx.get("market_regime") or "unknown"),
        direction=direction,
        strategy_id=_text(intent.get("strategy_id")),
        book_id=_text(ctx.get("book_id")),
        entry_price=_entry_price(rec),
        stop_loss=_float(intent.get("stop_loss"), 0.0),
        take_profit=_float(intent.get("take_profit"), 0.0),
        exit_price=None if ctx.get("exit_price", ctx.get("close_price")) in {None, ""} else _float(ctx.get("exit_price", ctx.get("close_price"))),
        result_R=round(result_r, 8),
        pnl=round(pnl, 8),
        expectancy=round(result_r if closed else 0.0, 8),
        win_loss=win_loss,
        win_loss_ratio=win_loss_ratio,
        average_R=round(result_r if closed else 0.0, 8),
        max_drawdown=_max_drawdown_from_single(result_r if closed else 0.0),
        slippage=_float(fill.get("slippage_bps") or slippage_model.get("slippage_bps"), 0.0),
        latency_ms=_float(fill.get("latency_ms") or ctx.get("latency_ms"), 0.0),
        rejection_rate=1.0 if _text(rec.get("status")) in {"RECONCILIATION_NOT_REQUIRED"} or _text(fill.get("fill_status")).upper() == "NO_FILL" else 0.0,
        stale_data_rate=_float(ctx.get("stale_data_rate"), 0.0),
        signal_to_outcome_drift=_signal_drift(rec, ctx, result_r if closed else 0.0, closed),
        paper_live_gap=_paper_live_gap(ctx),
        api_error_rate=_float(ctx.get("api_error_rate"), 0.0),
        manual_override_count=int(_float(ctx.get("manual_override_count"), 0.0)),
        next_action=_next_action(status, result_r if closed else 0.0, closed, sample_size=int(_float(ctx.get("sample_size"), 1.0))),
        reconciliation_status=_text(rec.get("reconciliation_status") or rec.get("status")),
        reconciliation_mismatch=_bool(rec.get("reconciliation_mismatch")),
        reconciliation_evidence_hash=_text(rec.get("reconciliation_evidence_hash")),
        paper_reconciliation_record_sha256=rec.get("paper_reconciliation_record_sha256"),
        outcome_quality_warnings=warnings,
    ).to_dict()
    return record


def summarize_outcomes(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(r) for r in records if isinstance(r, Mapping)]
    closed = [r for r in rows if r.get("outcome_closed") is True]
    result_rs = [_float(r.get("result_R"), 0.0) for r in closed]
    win_count = sum(1 for value in result_rs if value > 0)
    loss_count = sum(1 for value in result_rs if value < 0)
    breakeven_count = sum(1 for value in result_rs if value == 0)
    expectancy = sum(result_rs) / len(result_rs) if result_rs else 0.0
    avg_r = expectancy
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in result_rs:
        cumulative += value
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)
    return {
        "outcome_count": len(rows),
        "closed_count": len(closed),
        "win_count": win_count,
        "loss_count": loss_count,
        "breakeven_count": breakeven_count,
        "expectancy": round(expectancy, 8),
        "win_loss_ratio": round(win_count / loss_count, 8) if loss_count else float(win_count),
        "average_R": round(avg_r, 8),
        "max_drawdown": round(max_dd, 8),
        "average_slippage": round(sum(_float(r.get("slippage"), 0.0) for r in rows) / len(rows), 8) if rows else 0.0,
        "average_latency_ms": round(sum(_float(r.get("latency_ms"), 0.0) for r in rows) / len(rows), 8) if rows else 0.0,
        "rejection_rate": round(sum(_float(r.get("rejection_rate"), 0.0) for r in rows) / len(rows), 8) if rows else 0.0,
        "stale_data_rate": round(sum(_float(r.get("stale_data_rate"), 0.0) for r in rows) / len(rows), 8) if rows else 0.0,
        "signal_to_outcome_drift": round(sum(_float(r.get("signal_to_outcome_drift"), 0.0) for r in rows) / len(rows), 8) if rows else 0.0,
        "api_error_rate": round(sum(_float(r.get("api_error_rate"), 0.0) for r in rows) / len(rows), 8) if rows else 0.0,
        "manual_override_count": int(sum(_float(r.get("manual_override_count"), 0.0) for r in rows)),
        "reconciliation_mismatch_count": sum(1 for r in rows if r.get("reconciliation_mismatch") is True),
    }


#: Re-entries of the same setup in consecutive scheduler cycles land minutes
#: apart; genuinely new setups at the same R multiple arrive hours later. Two
#: hours cleanly separates the two on the 15-minute cadence.
TRADE_EVENT_MERGE_GAP_MINUTES = 120


def _parse_created_at(value: Any):
    from datetime import datetime, timezone

    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def independent_trade_events(
    records: Iterable[Mapping[str, Any]],
    *,
    merge_gap_minutes: float = TRADE_EVENT_MERGE_GAP_MINUTES,
) -> list[dict[str, Any]]:
    """Cluster closed outcomes into independent trade events.

    The scheduler re-enters the same strategy setup every cycle, so raw
    closed-outcome counts overstate the independent sample. Rows with the same
    ``result_R`` (a strategy's R multiple is its rule's fingerprint) and a
    compatible direction within ``merge_gap_minutes`` of the cluster's last
    member are ONE event. A missing direction (legacy rows) is a wildcard and
    an unparseable timestamp merges rather than splits — every ambiguity
    resolves toward FEWER events, the stricter direction for sample gates.
    Entry price is deliberately NOT in the signature: re-entries land at
    slightly different prices each cycle, and splitting on price would count
    one repeated setup many times.
    """
    closed = [dict(r) for r in records if isinstance(r, Mapping) and r.get("outcome_closed") is True]
    closed.sort(key=lambda r: _text(r.get("created_at_utc")))
    events: list[dict[str, Any]] = []
    by_result: dict[float, list[int]] = {}
    for row in closed:
        r_key = round(_float(row.get("result_R"), 0.0), 6)
        direction = _text(row.get("direction")).upper()
        created = _parse_created_at(row.get("created_at_utc"))
        merged = False
        for event_index in reversed(by_result.get(r_key, [])):
            event = events[event_index]
            direction_compatible = (
                not direction or not event["direction"] or event["direction"] == direction
            )
            if not direction_compatible:
                continue
            previous = event.get("_last_dt")
            within_gap = (
                created is None
                or previous is None
                or (created - previous).total_seconds() <= merge_gap_minutes * 60.0
            )
            if not within_gap:
                continue
            event["outcome_ids"].append(_text(row.get("outcome_id")))
            event["count"] += 1
            event["last_created_at_utc"] = _text(row.get("created_at_utc"))
            if created is not None:
                event["_last_dt"] = created
            if direction and not event["direction"]:
                event["direction"] = direction
            merged = True
            break
        if merged:
            continue
        events.append({
            "direction": direction,
            "result_R": r_key,
            "outcome_ids": [_text(row.get("outcome_id"))],
            "count": 1,
            "first_created_at_utc": _text(row.get("created_at_utc")),
            "last_created_at_utc": _text(row.get("created_at_utc")),
            "_last_dt": created,
        })
        by_result.setdefault(r_key, []).append(len(events) - 1)
    for event in events:
        event.pop("_last_dt", None)
    return events


def count_independent_trade_events(
    records: Iterable[Mapping[str, Any]],
    *,
    merge_gap_minutes: float = TRADE_EVENT_MERGE_GAP_MINUTES,
) -> int:
    return len(independent_trade_events(records, merge_gap_minutes=merge_gap_minutes))


def build_outcome_feedback_registry_record(outcome: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(outcome or {})
    chain_payload = {
        "research_signal_id": payload.get("research_signal_id"),
        "decision_id": payload.get("decision_id"),
        "risk_gate_id": payload.get("risk_gate_id"),
        "order_intent_id": payload.get("order_intent_id"),
        "execution_id": payload.get("execution_id"),
        "reconciliation_id": payload.get("reconciliation_id"),
        "outcome_id": payload.get("outcome_id"),
        "feedback_cycle_id": payload.get("feedback_cycle_id"),
    }
    record = {
        "outcome_feedback_registry_version": OUTCOME_ANALYTICS_VERSION,
        "order_id_chain_version": ORDER_ID_CHAIN_VERSION,
        "outcome_id": payload.get("outcome_id"),
        "feedback_cycle_id": payload.get("feedback_cycle_id"),
        "profile_id": payload.get("profile_id"),
        "research_signal_id": payload.get("research_signal_id"),
        "decision_id": payload.get("decision_id"),
        "risk_gate_id": payload.get("risk_gate_id"),
        "order_intent_id": payload.get("order_intent_id"),
        "execution_id": payload.get("execution_id"),
        "reconciliation_id": payload.get("reconciliation_id"),
        "status": payload.get("status"),
        "outcome_closed": payload.get("outcome_closed"),
        # Grouping/dedupe keys: the performance report groups registry rows by
        # regime/direction and clusters re-entries into independent trade
        # events — without these here every group is "unknown" and every row
        # counts as its own sample.
        "regime": payload.get("regime"),
        "direction": payload.get("direction"),
        "strategy_id": payload.get("strategy_id"),
        "book_id": payload.get("book_id"),
        "entry_price": payload.get("entry_price"),
        "close_reason": payload.get("close_reason"),
        "result_R": payload.get("result_R"),
        "pnl": payload.get("pnl"),
        "expectancy": payload.get("expectancy"),
        "win_loss": payload.get("win_loss"),
        "average_R": payload.get("average_R"),
        "max_drawdown": payload.get("max_drawdown"),
        "slippage": payload.get("slippage"),
        "latency_ms": payload.get("latency_ms"),
        "rejection_rate": payload.get("rejection_rate"),
        "stale_data_rate": payload.get("stale_data_rate"),
        "signal_to_outcome_drift": payload.get("signal_to_outcome_drift"),
        "paper_live_gap": payload.get("paper_live_gap"),
        "api_error_rate": payload.get("api_error_rate"),
        "manual_override_count": payload.get("manual_override_count"),
        "next_action": payload.get("next_action"),
        "reconciliation_status": payload.get("reconciliation_status"),
        "reconciliation_mismatch": payload.get("reconciliation_mismatch"),
        "reconciliation_evidence_hash": payload.get("reconciliation_evidence_hash"),
        "outcome_record_sha256": payload.get("outcome_record_sha256"),
        "outcome_chain_complete": chain_complete(chain_payload, through="outcome"),
        "missing_outcome_chain_fields": missing_chain_fields(chain_payload, through="outcome"),
        "live_trading_allowed_by_this_module": payload.get("live_trading_allowed_by_this_module"),
        "runtime_settings_mutated": payload.get("runtime_settings_mutated"),
        "score_weights_mutated": payload.get("score_weights_mutated"),
        "auto_promotion_allowed": payload.get("auto_promotion_allowed"),
        "created_at_utc": payload.get("created_at_utc") or utc_now_canonical(),
    }
    record["outcome_feedback_registry_record_id"] = stable_id("outcome_feedback_registry", record, 24)
    record["outcome_feedback_registry_record_sha256"] = sha256_json(record)
    return record


def outcome_skip_reason(payload: Mapping[str, Any], existing_records: list[Mapping[str, Any]]) -> str | None:
    """Decide whether an outcome must NOT be appended (P0-3).

    Returns a skip reason (``"not_closed"`` / ``"no_execution"`` /
    ``"duplicate"``) or ``None`` to append. Pure — no IO.
    """
    if not bool(payload.get("outcome_closed")):
        return "not_closed"
    execution_id = payload.get("execution_id")
    reconciliation_id = payload.get("reconciliation_id")
    if not execution_id and not reconciliation_id:
        return "no_execution"
    outcome_id = payload.get("outcome_id")
    seen_outcomes = {r.get("outcome_id") for r in existing_records}
    seen_execs = {r.get("execution_id") for r in existing_records if r.get("execution_id")}
    seen_recons = {r.get("reconciliation_id") for r in existing_records if r.get("reconciliation_id")}
    if (
        (outcome_id and outcome_id in seen_outcomes)
        or (execution_id and execution_id in seen_execs)
        or (reconciliation_id and reconciliation_id in seen_recons)
    ):
        return "duplicate"
    return None


def persist_outcome_analytics_record(cfg: AppConfig, outcome: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(outcome)
    atomic_write_json(_latest_path(cfg, "outcome_analytics_record.json"), payload)

    # P0-3: only a fresh, CLOSED trade produces an outcome, and each
    # execution/reconciliation is recorded exactly once. No-trade / open /
    # already-seen cycles must not append (this is what inflated the metrics).
    reg_path = registry_path(cfg, OUTCOME_FEEDBACK_REGISTRY_NAME)
    skip_reason = outcome_skip_reason(payload, load_registry_records(reg_path))
    if skip_reason:
        marker = {
            "status": "OUTCOME_DUPLICATE_SKIPPED" if skip_reason == "duplicate" else "NO_TRADE_OBSERVATION",
            "skip_reason": skip_reason,
            "outcome_id": payload.get("outcome_id"),
            "execution_id": payload.get("execution_id"),
            "reconciliation_id": payload.get("reconciliation_id"),
            "appended": False,
        }
        atomic_write_json(_latest_path(cfg, "outcome_feedback_registry_record.json"), marker)
        return marker

    registry_record = build_outcome_feedback_registry_record(payload)
    persisted = append_registry_record(
        registry_path(cfg, OUTCOME_FEEDBACK_REGISTRY_NAME),
        registry_record,
        registry_name=OUTCOME_FEEDBACK_REGISTRY_NAME,
        id_field="outcome_feedback_registry_record_id",
        hash_field="outcome_feedback_registry_record_sha256",
        id_prefix="outcome_feedback_registry",
    )
    atomic_write_json(_latest_path(cfg, "outcome_feedback_registry_record.json"), persisted)
    payload["outcome_feedback_registry_record_id"] = persisted.get("outcome_feedback_registry_record_id")
    payload["outcome_feedback_registry_record_sha256"] = persisted.get("outcome_feedback_registry_record_sha256")
    atomic_write_json(_latest_path(cfg, "outcome_analytics_record.json"), payload)
    return persisted


def analyze_and_persist_paper_outcome(
    reconciliation: Mapping[str, Any],
    *,
    outcome_context: Mapping[str, Any] | None = None,
    cfg: AppConfig | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(".")
    outcome = analyze_paper_reconciliation_outcome(reconciliation, outcome_context=outcome_context)
    registry_record = persist_outcome_analytics_record(cfg, outcome)
    outcome["outcome_feedback_registry_record_id"] = registry_record.get("outcome_feedback_registry_record_id")
    outcome["outcome_feedback_registry_record_sha256"] = registry_record.get("outcome_feedback_registry_record_sha256")
    atomic_write_json(_latest_path(cfg, "outcome_analytics_record.json"), outcome)
    return outcome


def run_outcome_analytics_latest(
    *,
    cfg: AppConfig | None = None,
    outcome_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(".")
    reconciliation = read_json(_latest_path(cfg, "paper_reconciliation_record.json"), default={})
    if not isinstance(reconciliation, dict):
        reconciliation = {}
    return analyze_and_persist_paper_outcome(reconciliation, outcome_context=outcome_context, cfg=cfg)

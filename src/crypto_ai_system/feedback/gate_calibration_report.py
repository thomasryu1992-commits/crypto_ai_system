"""Gate calibration: which blocks cost money and which ones saved it.

Aggregates settled counterfactuals by block reason. A reason whose blocked trades
would have averaged a positive R is a gate charging the system for safety it may
not need; a reason averaging negative R is a gate paying for itself. Sample size
decides whether either claim is worth acting on.

Review-only, like every feedback module: it produces a verdict a human reads, and
never retunes a gate. Loosening a gate remains a deliberate, manual change —
this report only tells the operator where to look.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from core.json_io import atomic_write_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.feedback.counterfactual_tracker import (
    AVOIDED_LOSS,
    COUNTERFACTUAL_OUTCOME_REGISTRY_NAME,
    MISSED_OPPORTUNITY,
    NEUTRAL_BLOCK,
)
from crypto_ai_system.registry.base_registry import load_registry_records, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

GATE_CALIBRATION_REPORT_VERSION = "gate_calibration_report.v1"

# This module reports; it never retunes.
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE = False
GATE_THRESHOLDS_MUTATED_BY_THIS_MODULE = False

DEFAULT_MIN_SAMPLE_SIZE = 5
# Below this |expectancy| the evidence is noise, not a verdict.
EXPECTANCY_VERDICT_THRESHOLD_R = 0.1

COSTLY_GATE = "COSTLY_GATE"
PROTECTIVE_GATE = "PROTECTIVE_GATE"
NEUTRAL_GATE = "NEUTRAL_GATE"
INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


def _latest_path(cfg: AppConfig, name: str) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    base = Path(raw)
    if not base.is_absolute():
        base = cfg.root / base
    base.mkdir(parents=True, exist_ok=True)
    return base / name


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value not in {None, ""} else default
    except (TypeError, ValueError):
        return default


def _verdict(count: int, expectancy: float, min_sample_size: int) -> str:
    if count < min_sample_size:
        return INSUFFICIENT_SAMPLE
    if expectancy > EXPECTANCY_VERDICT_THRESHOLD_R:
        return COSTLY_GATE
    if expectancy < -EXPECTANCY_VERDICT_THRESHOLD_R:
        return PROTECTIVE_GATE
    return NEUTRAL_GATE


def summarize_counterfactuals(
    rows: Iterable[Mapping[str, Any]], *, min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE
) -> dict[str, Any]:
    """Expectancy and verdict over one group of settled counterfactuals."""
    records = [row for row in rows if row.get("outcome_closed") is True]
    count = len(records)
    if count == 0:
        return {
            "count": 0,
            "missed_opportunity_count": 0,
            "avoided_loss_count": 0,
            "neutral_count": 0,
            "expectancy_R": 0.0,
            "total_R": 0.0,
            "missed_rate": 0.0,
            "best_R": 0.0,
            "worst_R": 0.0,
            "verdict": INSUFFICIENT_SAMPLE,
        }

    results = [_f(row.get("result_R")) for row in records]
    missed = sum(1 for row in records if row.get("classification") == MISSED_OPPORTUNITY)
    avoided = sum(1 for row in records if row.get("classification") == AVOIDED_LOSS)
    neutral = sum(1 for row in records if row.get("classification") == NEUTRAL_BLOCK)
    total_r = sum(results)
    expectancy = total_r / count
    return {
        "count": count,
        "missed_opportunity_count": missed,
        "avoided_loss_count": avoided,
        "neutral_count": neutral,
        "expectancy_R": round(expectancy, 8),
        "total_R": round(total_r, 8),
        "missed_rate": round(missed / count, 8),
        "best_R": round(max(results), 8),
        "worst_R": round(min(results), 8),
        "verdict": _verdict(count, expectancy, min_sample_size),
    }


def _group_by(
    rows: list[Mapping[str, Any]], key: str, *, min_sample_size: int
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        name = str(row.get(key) or "unknown")
        groups.setdefault(name, []).append(row)
    return {
        name: summarize_counterfactuals(values, min_sample_size=min_sample_size)
        for name, values in sorted(groups.items())
    }


def build_gate_calibration_report(
    outcomes: Iterable[Mapping[str, Any]],
    *,
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
) -> dict[str, Any]:
    rows = [dict(row) for row in outcomes if dict(row).get("outcome_closed") is True]
    by_reason = _group_by(rows, "block_reason", min_sample_size=min_sample_size)

    # The operator's actual question: which gate should I look at first? Rank the
    # costly ones by the R they turned away.
    costly = sorted(
        (
            {"block_reason": reason, **summary}
            for reason, summary in by_reason.items()
            if summary["verdict"] == COSTLY_GATE
        ),
        key=lambda item: item["total_R"],
        reverse=True,
    )

    report = {
        "gate_calibration_report_version": GATE_CALIBRATION_REPORT_VERSION,
        "created_at_utc": utc_now_canonical(),
        "min_sample_size": int(min_sample_size),
        "expectancy_verdict_threshold_R": EXPECTANCY_VERDICT_THRESHOLD_R,
        "overall": summarize_counterfactuals(rows, min_sample_size=min_sample_size),
        "summary_by_block_reason": by_reason,
        "summary_by_block_stage": _group_by(rows, "block_stage", min_sample_size=min_sample_size),
        "summary_by_regime": _group_by(rows, "regime", min_sample_size=min_sample_size),
        "summary_by_direction": _group_by(rows, "direction", min_sample_size=min_sample_size),
        "costly_gates_ranked": costly,
        "review_only": True,
        "live_trading_allowed_by_this_module": LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        "runtime_settings_mutated": RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE,
        "gate_thresholds_mutated": GATE_THRESHOLDS_MUTATED_BY_THIS_MODULE,
    }
    report["gate_calibration_report_id"] = stable_id("gate_calibration_report", report, 24)
    report["gate_calibration_report_sha256"] = sha256_json(report)
    return report


def run_gate_calibration_report_latest(
    *,
    cfg: AppConfig | None = None,
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
) -> dict[str, Any]:
    """Rebuild the report from the full counterfactual registry and snapshot it."""
    cfg = cfg or load_config(".")
    rows = load_registry_records(registry_path(cfg, COUNTERFACTUAL_OUTCOME_REGISTRY_NAME))
    report = build_gate_calibration_report(rows, min_sample_size=min_sample_size)
    atomic_write_json(_latest_path(cfg, "gate_calibration_report.json"), report)
    return report

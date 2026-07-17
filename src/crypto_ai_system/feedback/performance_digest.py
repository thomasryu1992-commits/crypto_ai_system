"""Weekly and monthly performance digests: is the edge decaying?

The performance report groups outcomes by profile, signal, regime and direction —
every axis except time. So a system whose edge died a month ago looks identical
to one that never had an edge: both report the same blended average over all
history, and the blend is exactly what hides the decay. The longer the registry
grows, the better it hides it, because each new week is a smaller share of the
mean.

This buckets closed outcomes into ISO weeks and calendar months and compares the
most recent *complete* period against the one before it. Completeness is the
point: judging a half-finished week against a full one manufactures a decline out
of the missing days.

Review-only, like every feedback module. It reports a trend; acting on one stays
a human decision.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.json_io import atomic_write_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.feedback.outcome_analytics_v2 import (
    OUTCOME_FEEDBACK_REGISTRY_NAME,
    summarize_outcomes,
)
from crypto_ai_system.registry.base_registry import load_registry_records, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

PERFORMANCE_DIGEST_VERSION = "performance_digest.v1"

# This module reports; it never acts.
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE = False
SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE = False

WEEKLY = "weekly"
MONTHLY = "monthly"

DEFAULT_MIN_BUCKET_SAMPLE = 5
# The same noise floor the gate-calibration report uses: an expectancy move
# smaller than this is not a trend, it is a handful of trades.
TREND_THRESHOLD_R = 0.1

IMPROVING = "IMPROVING"
DEGRADING = "DEGRADING"
STABLE = "STABLE"
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


def _parse(value: Any) -> datetime | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _week_key(moment: datetime) -> str:
    iso = moment.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _month_key(moment: datetime) -> str:
    return f"{moment.year:04d}-{moment.month:02d}"


def _week_end(key: str) -> datetime:
    """First instant after the ISO week — the key always came from isocalendar(),
    so it names a week that exists."""
    year, week = int(key[:4]), int(key[6:])
    monday = date.fromisocalendar(year, week, 1)
    return datetime(monday.year, monday.month, monday.day, tzinfo=timezone.utc) + timedelta(days=7)


def _month_end(key: str) -> datetime:
    year, month = int(key[:4]), int(key[5:])
    return datetime(year + (month // 12), (month % 12) + 1, 1, tzinfo=timezone.utc)


def _bucket_summary(rows: list[Mapping[str, Any]], *, period: str, period_end: datetime, now: datetime) -> dict[str, Any]:
    summary = summarize_outcomes(rows)
    closed = [r for r in rows if r.get("outcome_closed") is True]
    closed_count = int(summary["closed_count"])
    return {
        "period": period,
        # An open period is still accumulating; comparing it to a closed one
        # measures the calendar, not the strategy.
        "complete": period_end <= now,
        "closed_count": closed_count,
        "win_count": summary["win_count"],
        "loss_count": summary["loss_count"],
        "breakeven_count": summary["breakeven_count"],
        "win_rate": round(summary["win_count"] / closed_count, 6) if closed_count else 0.0,
        "expectancy_R": summary["expectancy"],
        "total_R": round(sum(_f(r.get("result_R")) for r in closed), 6),
        "max_drawdown_R": summary["max_drawdown"],
    }


def _buckets(rows: list[Mapping[str, Any]], *, period: str, now: datetime) -> list[dict[str, Any]]:
    key_of = _week_key if period == WEEKLY else _month_key
    end_of = _week_end if period == WEEKLY else _month_end
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        moment = _parse(row.get("created_at_utc"))
        if moment is None:
            continue
        groups.setdefault(key_of(moment), []).append(row)
    return [
        _bucket_summary(values, period=key, period_end=end_of(key), now=now)
        for key, values in sorted(groups.items())
    ]


def _trend(buckets: list[dict[str, Any]], *, min_bucket_sample: int) -> dict[str, Any]:
    """Compare the last two complete periods, or say why we cannot."""
    complete = [b for b in buckets if b["complete"]]
    base = {
        "verdict": INSUFFICIENT_SAMPLE,
        "latest_period": None,
        "previous_period": None,
        "expectancy_delta_R": None,
        "reason": None,
    }
    if len(complete) < 2:
        return {**base, "reason": "fewer_than_two_complete_periods"}

    latest, previous = complete[-1], complete[-2]
    thin = [
        b["period"] for b in (latest, previous) if b["closed_count"] < min_bucket_sample
    ]
    if thin:
        return {
            **base,
            "latest_period": latest["period"],
            "previous_period": previous["period"],
            "reason": f"below_min_sample: {', '.join(thin)}",
        }

    delta = latest["expectancy_R"] - previous["expectancy_R"]
    if delta > TREND_THRESHOLD_R:
        verdict = IMPROVING
    elif delta < -TREND_THRESHOLD_R:
        verdict = DEGRADING
    else:
        verdict = STABLE
    return {
        "verdict": verdict,
        "latest_period": latest["period"],
        "previous_period": previous["period"],
        "latest_expectancy_R": latest["expectancy_R"],
        "previous_expectancy_R": previous["expectancy_R"],
        "expectancy_delta_R": round(delta, 6),
        "reason": None,
    }


def build_performance_digest(
    outcomes: Iterable[Mapping[str, Any]],
    *,
    now: str | None = None,
    min_bucket_sample: int = DEFAULT_MIN_BUCKET_SAMPLE,
) -> dict[str, Any]:
    """Bucket closed outcomes by week and month, and read the recent trend."""
    created_at = now or utc_now_canonical()
    now_dt = _parse(created_at) or datetime.now(timezone.utc).replace(microsecond=0)
    rows = [dict(r) for r in outcomes if isinstance(r, Mapping)]

    weekly = _buckets(rows, period=WEEKLY, now=now_dt)
    monthly = _buckets(rows, period=MONTHLY, now=now_dt)
    overall = summarize_outcomes(rows)

    digest = {
        "performance_digest_version": PERFORMANCE_DIGEST_VERSION,
        "created_at_utc": created_at,
        "source_registry_name": OUTCOME_FEEDBACK_REGISTRY_NAME,
        "min_bucket_sample": int(min_bucket_sample),
        "trend_threshold_R": TREND_THRESHOLD_R,
        "outcome_count": overall["outcome_count"],
        "closed_count": overall["closed_count"],
        # Rows whose created_at_utc could not be read land in no period; say so
        # rather than letting them silently vanish from every bucket.
        "unbucketed_count": sum(1 for r in rows if _parse(r.get("created_at_utc")) is None),
        "overall_expectancy_R": overall["expectancy"],
        "weekly": weekly,
        "monthly": monthly,
        "weekly_trend": _trend(weekly, min_bucket_sample=min_bucket_sample),
        "monthly_trend": _trend(monthly, min_bucket_sample=min_bucket_sample),
        "review_only": True,
        "live_trading_allowed_by_this_module": LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        "runtime_settings_mutated": RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE,
        "score_weights_mutated": SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE,
    }
    digest["performance_digest_id"] = stable_id("performance_digest", digest, 24)
    digest["performance_digest_sha256"] = sha256_json(digest)
    return digest


def run_performance_digest_latest(
    *,
    cfg: AppConfig | None = None,
    now: str | None = None,
    min_bucket_sample: int = DEFAULT_MIN_BUCKET_SAMPLE,
) -> dict[str, Any]:
    """Rebuild the digest from the full outcome registry and snapshot it."""
    cfg = cfg or load_config(".")
    rows = load_registry_records(registry_path(cfg, OUTCOME_FEEDBACK_REGISTRY_NAME))
    digest = build_performance_digest(rows, now=now, min_bucket_sample=min_bucket_sample)
    atomic_write_json(_latest_path(cfg, "performance_digest.json"), digest)
    return digest

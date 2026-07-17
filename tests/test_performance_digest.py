"""Weekly/monthly digests: a decaying edge must show as a trend rather than
being averaged into the all-history mean that hides it."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.feedback import performance_digest as pd_mod
from crypto_ai_system.feedback.performance_digest import build_performance_digest

# 2026-06-01 is a Monday (ISO 2026-W23); 2026-06-08 starts 2026-W24.
WEEK_A = "2026-06-01"
WEEK_B = "2026-06-08"
# Far enough ahead that both June weeks and June itself are complete.
NOW = "2026-07-15T00:00:00Z"


def _outcome(day: str, result_r: float, hour: int = 12):
    return {
        "outcome_closed": True,
        "result_R": result_r,
        "created_at_utc": f"{day}T{hour:02d}:00:00Z",
    }


def _week(day: str, results: list[float]):
    return [_outcome(day, r, hour=h) for h, r in enumerate(results)]


def _digest(rows, now=NOW, min_bucket_sample=5):
    return build_performance_digest(rows, now=now, min_bucket_sample=min_bucket_sample)


def _bucket(digest, period, key):
    return next(b for b in digest[period] if b["period"] == key)


# -- bucketing ----------------------------------------------------------------

def test_outcomes_land_in_their_iso_week():
    digest = _digest(_week(WEEK_A, [1.0, -1.0]) + _week(WEEK_B, [2.0]))
    assert [b["period"] for b in digest["weekly"]] == ["2026-W23", "2026-W24"]
    assert _bucket(digest, "weekly", "2026-W23")["closed_count"] == 2
    assert _bucket(digest, "weekly", "2026-W24")["closed_count"] == 1


def test_outcomes_land_in_their_calendar_month():
    digest = _digest(_week(WEEK_A, [1.0]) + [_outcome("2026-07-02", 1.0)])
    assert [b["period"] for b in digest["monthly"]] == ["2026-06", "2026-07"]


def test_bucket_reports_the_metrics_an_operator_reads():
    bucket = _bucket(_digest(_week(WEEK_A, [2.0, 2.0, -1.0, -1.0])), "weekly", "2026-W23")
    assert bucket["closed_count"] == 4
    assert bucket["win_count"] == 2
    assert bucket["loss_count"] == 2
    assert bucket["win_rate"] == 0.5
    assert bucket["expectancy_R"] == 0.5
    assert bucket["total_R"] == 2.0


def test_open_outcomes_are_not_counted_as_closed():
    rows = _week(WEEK_A, [1.0]) + [{"outcome_closed": False, "result_R": 99.0,
                                    "created_at_utc": f"{WEEK_A}T12:00:00Z"}]
    bucket = _bucket(_digest(rows), "weekly", "2026-W23")
    assert bucket["closed_count"] == 1
    assert bucket["total_R"] == 1.0


def test_unreadable_timestamps_are_counted_not_silently_dropped():
    rows = _week(WEEK_A, [1.0]) + [{"outcome_closed": True, "result_R": 1.0, "created_at_utc": "garbage"}]
    digest = _digest(rows)
    assert digest["unbucketed_count"] == 1
    assert sum(b["closed_count"] for b in digest["weekly"]) == 1


# -- completeness -------------------------------------------------------------

def test_the_period_in_progress_is_marked_incomplete():
    """Mid-week, this week is still accumulating."""
    digest = _digest(_week(WEEK_A, [1.0]), now="2026-06-03T00:00:00Z")
    assert _bucket(digest, "weekly", "2026-W23")["complete"] is False
    assert _bucket(digest, "monthly", "2026-06")["complete"] is False


def test_a_finished_period_is_complete():
    digest = _digest(_week(WEEK_A, [1.0]), now="2026-06-08T00:00:00Z")
    assert _bucket(digest, "weekly", "2026-W23")["complete"] is True
    # June is not over on the 8th.
    assert _bucket(digest, "monthly", "2026-06")["complete"] is False


def test_partial_period_never_drives_the_trend():
    """The in-progress week looks catastrophic only because it is two days old.
    Comparing it to a full week would report a decline that is missing days."""
    rows = _week(WEEK_A, [2.0] * 6) + _week(WEEK_B, [-1.0] * 6)
    mid_week_b = "2026-06-09T00:00:00Z"
    trend = _digest(rows, now=mid_week_b)["weekly_trend"]
    assert trend["verdict"] == pd_mod.INSUFFICIENT_SAMPLE
    assert trend["reason"] == "fewer_than_two_complete_periods"


# -- trend --------------------------------------------------------------------

def test_edge_decay_is_reported_as_degrading():
    rows = _week(WEEK_A, [2.0] * 6) + _week(WEEK_B, [-1.0] * 6)
    trend = _digest(rows)["weekly_trend"]
    assert trend["verdict"] == pd_mod.DEGRADING
    assert trend["latest_period"] == "2026-W24"
    assert trend["previous_period"] == "2026-W23"
    assert trend["expectancy_delta_R"] == -3.0


def test_improving_edge_is_reported():
    rows = _week(WEEK_A, [-1.0] * 6) + _week(WEEK_B, [2.0] * 6)
    assert _digest(rows)["weekly_trend"]["verdict"] == pd_mod.IMPROVING


def test_small_move_is_not_a_trend():
    rows = _week(WEEK_A, [1.0] * 6) + _week(WEEK_B, [1.05] * 6)
    assert _digest(rows)["weekly_trend"]["verdict"] == pd_mod.STABLE


def test_thin_period_yields_no_verdict():
    rows = _week(WEEK_A, [2.0] * 6) + _week(WEEK_B, [-1.0] * 2)
    trend = _digest(rows)["weekly_trend"]
    assert trend["verdict"] == pd_mod.INSUFFICIENT_SAMPLE
    assert "2026-W24" in trend["reason"]


def test_trend_compares_only_the_two_most_recent_complete_periods():
    rows = (
        _week("2026-05-25", [-5.0] * 6)  # W22, ancient history
        + _week(WEEK_A, [1.0] * 6)       # W23
        + _week(WEEK_B, [1.0] * 6)       # W24
    )
    trend = _digest(rows)["weekly_trend"]
    assert (trend["latest_period"], trend["previous_period"]) == ("2026-W24", "2026-W23")
    assert trend["verdict"] == pd_mod.STABLE


def test_blended_average_hides_what_the_digest_surfaces():
    """The whole point: all-history expectancy stays positive while the most
    recent week is losing money."""
    rows = _week(WEEK_A, [2.0] * 6) + _week(WEEK_B, [-1.0] * 6)
    digest = _digest(rows)
    assert digest["overall_expectancy_R"] == 0.5
    assert digest["weekly_trend"]["verdict"] == pd_mod.DEGRADING
    assert _bucket(digest, "weekly", "2026-W24")["expectancy_R"] == -1.0


# -- shape --------------------------------------------------------------------

def test_empty_registry_reports_nothing_rather_than_failing():
    digest = _digest([])
    assert digest["weekly"] == []
    assert digest["monthly"] == []
    assert digest["weekly_trend"]["verdict"] == pd_mod.INSUFFICIENT_SAMPLE
    assert digest["closed_count"] == 0


def test_digest_is_deterministic_and_identified():
    rows = _week(WEEK_A, [1.0])
    assert _digest(rows)["performance_digest_id"] == _digest(rows)["performance_digest_id"]


def test_digest_is_review_only():
    digest = _digest(_week(WEEK_A, [1.0]))
    assert digest["review_only"] is True
    assert digest["live_trading_allowed_by_this_module"] is False
    assert digest["runtime_settings_mutated"] is False

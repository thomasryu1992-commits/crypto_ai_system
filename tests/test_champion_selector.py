"""Phase S5: batch champion selection tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.backtesting.champion_selector_agent import (
    ChampionScoreWeights,
    select_batch_champion,
)


def _record(strategy_id, *, qualified=True, expectancy=0.5, profit_factor=1.5,
            drawdown=3.0, trades=120, regime_consistency=1.0, stability=0.8,
            win_rate=0.5, generation_id="GEN-001"):
    return {
        "strategy_id": strategy_id,
        "strategy_rule_hash": f"hash_{strategy_id}",
        "generation_id": generation_id,
        "qualified": qualified,
        "metrics": {
            "expectancy_r": expectancy,
            "profit_factor": profit_factor,
            "max_drawdown_r": drawdown,
            "trade_count": trades,
            "regime_consistency": regime_consistency,
            "win_rate": win_rate,
        },
        "walk_forward": {"temporal_stability": stability, "walk_forward_pass_rate": 0.9},
    }


NOW = "2026-07-16T00:00:00Z"


def test_no_qualified_yields_no_champion():
    records = [_record("S001", qualified=False), _record("S002", qualified=False)]
    result = select_batch_champion(records, now=NOW)
    assert result["selection_status"] == "NO_CHAMPION"
    assert result["selected_strategy_id"] is None
    assert result["activation_permission"] is None
    assert result["qualified_count"] == 0


def test_empty_batch_no_champion():
    result = select_batch_champion([], generation_id="GEN-009", now=NOW)
    assert result["selection_status"] == "NO_CHAMPION"
    assert result["generation_id"] == "GEN-009"


def test_single_qualified_is_champion():
    records = [_record("S001"), _record("S002", qualified=False)]
    result = select_batch_champion(records, now=NOW)
    assert result["selection_status"] == "BATCH_CHAMPION"
    assert result["selected_strategy_id"] == "S001"
    assert result["activation_permission"] == "PAPER_ONLY"


def test_best_composite_wins():
    records = [
        _record("S001", expectancy=0.2, profit_factor=1.2, drawdown=5.0, stability=0.5),
        _record("S002", expectancy=0.9, profit_factor=2.5, drawdown=2.0, stability=0.9),  # best all round
        _record("S003", expectancy=0.4, profit_factor=1.4, drawdown=4.0, stability=0.6),
    ]
    result = select_batch_champion(records, now=NOW)
    assert result["selected_strategy_id"] == "S002"
    assert result["ranked"][0]["strategy_id"] == "S002"
    assert len(result["ranked"]) == 3


def test_unqualified_excluded_even_if_metrics_high():
    records = [
        _record("S001", expectancy=5.0, profit_factor=9.0, drawdown=0.5, qualified=False),  # unqualified
        _record("S002", expectancy=0.3, profit_factor=1.3),
    ]
    result = select_batch_champion(records, now=NOW)
    assert result["selected_strategy_id"] == "S002"
    assert result["qualified_count"] == 1


def test_permissions_are_paper_only():
    result = select_batch_champion([_record("S001")], now=NOW)
    assert result["can_add_to_paper_pool"] is True
    assert result["can_add_to_testnet_pool"] is False
    assert result["can_add_to_live_pool"] is False


def test_drawdown_penalty_breaks_a_tie():
    # Identical except drawdown; the lower-drawdown strategy must win.
    records = [
        _record("S001", drawdown=8.0),
        _record("S002", drawdown=1.0),
    ]
    result = select_batch_champion(records, now=NOW)
    assert result["selected_strategy_id"] == "S002"


def test_win_rate_not_in_score():
    # A high win rate must not override a weaker expectancy/PF profile.
    records = [
        _record("S001", expectancy=0.2, profit_factor=1.2, win_rate=0.9),
        _record("S002", expectancy=0.9, profit_factor=2.5, win_rate=0.4),
    ]
    result = select_batch_champion(records, now=NOW)
    assert result["selected_strategy_id"] == "S002"


def test_deterministic_selection_id():
    records = [_record("S001"), _record("S002", expectancy=0.9, profit_factor=2.5)]
    a = select_batch_champion(records, now=NOW)
    b = select_batch_champion(records, now=NOW)
    assert a["champion_selection_id"] == b["champion_selection_id"]


def test_custom_weights_change_outcome():
    # S001 has better drawdown; S002 better expectancy. Heavy drawdown weight favours S001.
    records = [
        _record("S001", expectancy=0.4, profit_factor=1.4, drawdown=1.0),
        _record("S002", expectancy=0.6, profit_factor=1.6, drawdown=9.0),
    ]
    default = select_batch_champion(records, now=NOW)
    assert default["selected_strategy_id"] == "S002"

    drawdown_averse = ChampionScoreWeights(
        expectancy=0.1, profit_factor=0.1, walk_forward_stability=0.1,
        regime_consistency=0.1, sample_quality=0.1, drawdown_penalty=0.9,
    )
    averse = select_batch_champion(records, weights=drawdown_averse, now=NOW)
    assert averse["selected_strategy_id"] == "S001"

"""Pre-deployment overfitting scoring: a backtest that looks good is only
evidence if enough observations back each number that was fitted."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.backtesting import robustness_scorer as rs
from crypto_ai_system.backtesting.robustness_scorer import (
    count_free_parameters,
    score_robustness,
)
from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec


def _spec(conditions=None):
    return StrategySpec.from_dict({
        "schema_version": "strategy_spec.v1",
        "strategy_id": "S001", "strategy_version": "1.0", "generation_id": "GEN-001",
        "strategy_family": "trend_pullback", "status": "GENERATED",
        "symbol_scope": ["BTCUSDT"], "timeframe": "1h", "direction": "long",
        "entry_rules": {
            "operator": "AND",
            "conditions": conditions or [{"feature": "rsi", "comparison": "<=", "value": 50}],
        },
        "exit_rules": {"stop_model": "atr", "stop_atr": 1.0, "target_atr": 2.0, "max_holding_bars": 5},
        "risk_constraints": {"max_risk_per_trade_R": 1.0},
    })


def _metrics(trade_count, *, net=10.0, fee=0.5, slip=0.5):
    return {
        "trade_count": trade_count,
        "total_net_r": net,
        "fee_cost_r": fee,
        "slippage_cost_r": slip,
        "expectancy_r": (net / trade_count) if trade_count else None,
    }


def _walk_forward(pass_rate=1.0, stability=0.8):
    return {"walk_forward_pass_rate": pass_rate, "temporal_stability": stability}


def _regimes(traded=("TREND_UP", "RANGE"), profitable=2):
    return {"regimes_traded": list(traded), "profitable_regime_count": profitable}


def _score(spec=None, metrics=None, walk_forward=None, regimes=None):
    return score_robustness(
        spec or _spec(),
        metrics or _metrics(200),
        walk_forward or _walk_forward(),
        regimes or _regimes(),
    )


# -- degrees of freedom -------------------------------------------------------

def test_only_literals_count_as_fitted():
    """close > ma20 states a relationship and tunes nothing; adx >= 22.66 is a
    number someone chose."""
    spec = _spec([
        {"feature": "close", "comparison": ">", "value_from": "ma20"},
        {"feature": "ma20", "comparison": ">", "value_from": "ma50"},
        {"feature": "adx", "comparison": ">=", "value": 22.6602},
    ])
    # 1 literal + stop_atr/target_atr/max_holding_bars — the real pool's shape.
    assert count_free_parameters(spec) == 4


def test_exits_always_cost_three_parameters():
    spec = _spec([{"feature": "close", "comparison": ">", "value_from": "ma20"}])
    assert count_free_parameters(spec) == rs.EXIT_FREE_PARAMETERS


def test_categorical_label_is_a_fitted_choice():
    spec = _spec([{"feature": "market_regime", "comparison": "==", "value": "TREND_UP"}])
    assert count_free_parameters(spec) == rs.EXIT_FREE_PARAMETERS + 1


# -- the veto -----------------------------------------------------------------

def test_thin_sample_is_fragile_however_good_it_looks():
    """The pool's live shape: 8 trades over 4 fitted parameters. Perfect
    walk-forward and perfect regime breadth must not rescue it — they are
    measured on the same eight trades."""
    result = _score(metrics=_metrics(8), walk_forward=_walk_forward(1.0, 1.0), regimes=_regimes())
    assert result["free_parameters"] == 4
    assert result["trades_per_parameter"] == 2.0
    assert result["verdict"] == rs.FRAGILE
    assert "trades_per_parameter_below_critical" in result["warnings"]


def test_veto_applies_at_the_boundary():
    # 4 params x 5 trades = exactly the critical ratio, so the veto releases.
    assert _score(metrics=_metrics(20, net=20.0))["trades_per_parameter"] == 5.0
    assert _score(metrics=_metrics(20, net=20.0))["verdict"] != rs.FRAGILE
    assert _score(metrics=_metrics(19, net=19.0))["verdict"] == rs.FRAGILE


# -- verdicts -----------------------------------------------------------------

def test_deep_sample_with_consistent_edge_is_robust():
    result = _score(metrics=_metrics(400, net=80.0, fee=1.0, slip=1.0))
    assert result["trades_per_parameter"] == 100.0
    assert result["verdict"] == rs.ROBUST
    assert result["robustness_score"] >= rs.ROBUST_SCORE_THRESHOLD
    assert result["warnings"] == []


def test_adequate_sample_but_shaky_evidence_is_provisional():
    result = _score(
        metrics=_metrics(40),
        walk_forward=_walk_forward(0.5, 0.3),
        regimes=_regimes(("TREND_UP", "RANGE", "HIGH_VOL"), profitable=1),
    )
    assert result["verdict"] == rs.PROVISIONAL


def test_edge_in_one_regime_of_many_scores_down():
    broad = _score(regimes=_regimes(("TREND_UP", "RANGE", "HIGH_VOL", "TREND_DOWN"), profitable=4))
    narrow = _score(regimes=_regimes(("TREND_UP", "RANGE", "HIGH_VOL", "TREND_DOWN"), profitable=1))
    assert narrow["components"]["regime_breadth"] < broad["components"]["regime_breadth"]
    assert "edge_concentrated_in_minority_of_regimes" in narrow["warnings"]


# -- components ---------------------------------------------------------------

def test_absent_walk_forward_evidence_earns_no_credit():
    """Too few windows traded to compare is an absence of evidence, not proof of
    stability."""
    result = _score(walk_forward={"walk_forward_pass_rate": None, "temporal_stability": None})
    assert result["components"]["temporal_consistency"] == 0.0
    assert "insufficient_walk_forward_evidence" in result["warnings"]


def test_edge_eaten_by_costs_scores_down():
    healthy = _score(metrics=_metrics(200, net=100.0, fee=1.0, slip=1.0))
    eaten = _score(metrics=_metrics(200, net=2.0, fee=50.0, slip=50.0))
    assert healthy["components"]["cost_robustness"] > 0.9
    assert eaten["components"]["cost_robustness"] < 0.1
    assert "edge_largely_consumed_by_costs" in eaten["warnings"]


def test_losing_strategy_retains_no_edge():
    assert _score(metrics=_metrics(200, net=-5.0))["components"]["cost_robustness"] == 0.0


def test_more_parameters_is_less_parsimonious():
    lean = _spec([{"feature": "rsi", "comparison": "<=", "value": 50}])
    busy = _spec([
        {"feature": "rsi", "comparison": "<=", "value": 50},
        {"feature": "adx", "comparison": ">=", "value": 20},
        {"feature": "volume_zscore", "comparison": ">", "value": 1.0},
        {"feature": "bb_percent_b", "comparison": "<", "value": 0.2},
    ])
    assert _score(spec=busy)["components"]["parameter_parsimony"] < _score(spec=lean)["components"][
        "parameter_parsimony"
    ]


def test_zero_trades_does_not_divide_by_zero():
    result = _score(metrics=_metrics(0, net=0.0))
    assert result["trades_per_parameter"] == 0.0
    assert result["verdict"] == rs.FRAGILE


def test_score_is_deterministic_and_identified():
    first, second = _score(), _score()
    assert first["robustness_id"] == second["robustness_id"]
    assert first["robustness_score"] == second["robustness_score"]


def test_weights_sum_to_one():
    assert round(sum(rs.WEIGHTS.values()), 6) == 1.0

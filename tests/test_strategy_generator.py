"""Phase S2: StrategyGenerationAgent batch generation tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec
from crypto_ai_system.strategy_factory.strategy_generator_agent import (
    build_spec_dict,
    generate_batch,
    mutate_params,
)
from crypto_ai_system.strategy_factory.strategy_template_library import TREND_PULLBACK, TEMPLATES
from crypto_ai_system.strategy_factory.strategy_validator_agent import validate_strategy
import random


def test_batch_produces_four_valid_specs():
    batch = generate_batch("GEN-001", seed=7)
    assert batch["batch_complete"] is True
    assert batch["accepted_count"] == 4
    assert len(batch["specs"]) == 4
    ids = [s["strategy_id"] for s in batch["specs"]]
    assert ids == ["S001", "S002", "S003", "S004"]


def test_every_generated_spec_passes_validation():
    batch = generate_batch("GEN-002", seed=42, start_index=5)
    for spec_dict in batch["specs"]:
        spec = StrategySpec.from_dict(spec_dict)
        verdict = validate_strategy(spec)
        assert verdict["approved_for_backtest"] is True, (spec_dict["strategy_id"], verdict["block_reasons"])


def test_generation_is_reproducible():
    a = generate_batch("GEN-003", seed=99)
    b = generate_batch("GEN-003", seed=99)
    a_hashes = [s["strategy_rule_hash"] for s in a["specs"]]
    b_hashes = [s["strategy_rule_hash"] for s in b["specs"]]
    assert a_hashes == b_hashes


def test_different_seed_changes_batch():
    a = generate_batch("GEN-004", seed=1)
    b = generate_batch("GEN-004", seed=2)
    a_hashes = {s["strategy_rule_hash"] for s in a["specs"]}
    b_hashes = {s["strategy_rule_hash"] for s in b["specs"]}
    assert a_hashes != b_hashes


def test_specs_are_distinct_within_batch():
    batch = generate_batch("GEN-005", seed=13)
    hashes = [s["strategy_rule_hash"] for s in batch["specs"]]
    assert len(set(hashes)) == len(hashes)


def test_families_rotate_across_batch():
    batch = generate_batch("GEN-006", seed=3)
    families = [s["strategy_family"] for s in batch["specs"]]
    # 3 templates, 4 specs -> first three distinct, at least 3 families seen.
    assert len(set(families)) >= 3
    assert set(families).issubset(set(TEMPLATES.keys()))


def test_generated_specs_carry_no_authority():
    batch = generate_batch("GEN-007", seed=8)
    for spec_dict in batch["specs"]:
        assert spec_dict["can_submit_orders"] is False
        assert spec_dict["can_modify_runtime"] is False
        assert spec_dict["generation_id"] == "GEN-007"


def test_custom_count_and_start_index():
    batch = generate_batch("GEN-008", seed=5, start_index=10, count=2)
    assert batch["accepted_count"] == 2
    assert [s["strategy_id"] for s in batch["specs"]] == ["S010", "S011"]


def test_mutate_params_stays_in_bounds():
    rng = random.Random(0)
    for _ in range(200):
        params = mutate_params(TREND_PULLBACK.base_params, TREND_PULLBACK.param_space, rng)
        for name, spec in TREND_PULLBACK.param_space.items():
            assert spec.lo <= params[name] <= spec.hi
            if spec.integer:
                assert isinstance(params[name], int)


def test_build_spec_dict_shape():
    d = build_spec_dict(
        TREND_PULLBACK, TREND_PULLBACK.base_params,
        strategy_id="S001", generation_id="GEN-001",
    )
    spec = StrategySpec.from_dict(d)
    assert spec.strategy_family == "trend_pullback"
    assert spec.timeframe == "1h"

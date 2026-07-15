"""Phase S6: active strategy pool tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.strategy_factory.strategy_spec import StrategyStatus
from crypto_ai_system.strategy_factory import active_strategy_pool as pool_mod
from crypto_ai_system.strategy_factory.active_strategy_pool import (
    ACTION_ADDED,
    ACTION_REJECTED_ALREADY_ACTIVE,
    ACTION_REJECTED_POOL_FULL,
    ACTION_REPLACED,
    add_champion,
    empty_pool,
    find_entry,
    load_pool,
    occupying_entries,
    paper_active_specs,
    register_champion,
    set_status,
)

NOW = "2026-07-16T00:00:00Z"


def _spec(strategy_id, rule_hash=None, generation_id="GEN-001"):
    return {
        "strategy_id": strategy_id,
        "strategy_rule_hash": rule_hash or f"hash_{strategy_id}",
        "generation_id": generation_id,
        "strategy_family": "trend_pullback",
        "entry_rules": {"operator": "AND", "conditions": [{"feature": "rsi", "comparison": "<=", "value": 50}]},
    }


# -- basic add ----------------------------------------------------------------

def test_add_champion_to_empty_pool():
    pool, decision = add_champion(empty_pool(), _spec("S001"), 0.7, now=NOW)
    assert decision["action"] == ACTION_ADDED
    entry = find_entry(pool, "S001")
    assert entry["status"] == StrategyStatus.PAPER_ACTIVE.value
    assert entry["stage"] == "paper"
    assert len(occupying_entries(pool)) == 1


def test_reject_duplicate_rule_hash():
    pool, _ = add_champion(empty_pool(), _spec("S001", rule_hash="H"), 0.7, now=NOW)
    # Different id, same rule set -> already active.
    pool2, decision = add_champion(pool, _spec("S099", rule_hash="H"), 0.9, now=NOW)
    assert decision["action"] == ACTION_REJECTED_ALREADY_ACTIVE
    assert len(occupying_entries(pool2)) == 1


def test_reject_duplicate_strategy_id():
    pool, _ = add_champion(empty_pool(), _spec("S004", rule_hash="H1"), 0.7, now=NOW)
    # Same id from a later generation (different rules) -> id collision, rejected.
    pool2, decision = add_champion(pool, _spec("S004", rule_hash="H2"), 0.9, now=NOW)
    assert decision["action"] == ACTION_REJECTED_ALREADY_ACTIVE
    assert "globally unique" in decision["reason"]
    assert len(occupying_entries(pool2)) == 1


# -- capacity -----------------------------------------------------------------

def _fill(cap=5, base_score=0.5):
    pool = empty_pool()
    for i in range(cap):
        pool, _ = add_champion(pool, _spec(f"S00{i+1}"), base_score + i * 0.01, cap=cap, now=NOW)
    return pool


def test_pool_respects_cap():
    pool = _fill(cap=5)
    assert len(occupying_entries(pool)) == 5
    # 6th, not clearly better than weakest (0.50), is rejected.
    pool2, decision = add_champion(pool, _spec("S010"), 0.52, cap=5, min_improvement=0.05, now=NOW)
    assert decision["action"] == ACTION_REJECTED_POOL_FULL
    assert len(occupying_entries(pool2)) == 5
    assert find_entry(pool2, "S010") is None


def test_pool_full_replaces_weakest_when_clearly_better():
    pool = _fill(cap=5)  # scores 0.50..0.54, weakest S001=0.50
    pool2, decision = add_champion(pool, _spec("S010"), 0.80, cap=5, min_improvement=0.05, now=NOW)
    assert decision["action"] == ACTION_REPLACED
    assert decision["displaced_strategy_id"] == "S001"
    # Weakest suspended (slot freed), new one active; occupancy still 5.
    assert find_entry(pool2, "S001")["status"] == StrategyStatus.SUSPENDED.value
    assert find_entry(pool2, "S010")["status"] == StrategyStatus.PAPER_ACTIVE.value
    assert len(occupying_entries(pool2)) == 5


def test_replacement_needs_min_improvement():
    pool = _fill(cap=5)  # weakest 0.50
    _, decision = add_champion(pool, _spec("S010"), 0.53, cap=5, min_improvement=0.05, now=NOW)
    assert decision["action"] == ACTION_REJECTED_POOL_FULL  # 0.53 - 0.50 < 0.05


def test_suspended_frees_a_slot():
    pool = _fill(cap=5)
    pool, _ = set_status(pool, "S001", StrategyStatus.SUSPENDED, now=NOW)
    assert len(occupying_entries(pool)) == 4
    # Now a fresh champion fits without displacing anyone.
    pool2, decision = add_champion(pool, _spec("S010"), 0.4, cap=5, now=NOW)
    assert decision["action"] == ACTION_ADDED
    assert len(occupying_entries(pool2)) == 5


# -- status model -------------------------------------------------------------

def test_set_status_transitions():
    pool, _ = add_champion(empty_pool(), _spec("S001"), 0.7, now=NOW)
    for status in (StrategyStatus.WARNING, StrategyStatus.PROBATION):
        pool, changed = set_status(pool, "S001", status, now=NOW)
        assert changed is True
        assert find_entry(pool, "S001")["status"] == status.value
    # Warning/probation still occupy a slot.
    assert len(occupying_entries(pool)) == 1


def test_warning_and_probation_still_occupy():
    pool, _ = add_champion(empty_pool(), _spec("S001"), 0.7, now=NOW)
    pool, _ = set_status(pool, "S001", StrategyStatus.PROBATION, now=NOW)
    assert len(occupying_entries(pool)) == 1


def test_paper_active_specs_excludes_non_active():
    pool, _ = add_champion(empty_pool(), _spec("S001"), 0.7, now=NOW)
    pool, _ = add_champion(pool, _spec("S002"), 0.6, now=NOW)
    pool, _ = set_status(pool, "S002", StrategyStatus.PROBATION, now=NOW)
    specs = paper_active_specs(pool)
    ids = [s["strategy_id"] for s in specs]
    assert ids == ["S001"]  # only PAPER_ACTIVE is routed


# -- persistence --------------------------------------------------------------

def test_register_champion_persists_and_audits(tmp_path):
    pool_file = tmp_path / "active_strategy_pool.json"
    registry = tmp_path / "active_strategy_registry.jsonl"

    decision = register_champion(str(pool_file), str(registry), _spec("S001"), 0.7, now=NOW)
    assert decision["action"] == ACTION_ADDED
    assert pool_file.exists()

    reloaded = load_pool(str(pool_file))
    assert find_entry(reloaded, "S001")["status"] == StrategyStatus.PAPER_ACTIVE.value

    # A rejected decision is still audited but must not change the snapshot.
    dup = register_champion(str(pool_file), str(registry), _spec("S099", rule_hash="hash_S001"), 0.9, now=NOW)
    assert dup["action"] == ACTION_REJECTED_ALREADY_ACTIVE
    from core.json_io import read_jsonl
    assert len(read_jsonl(str(registry))) == 2  # both decisions logged


def test_load_missing_pool_is_empty(tmp_path):
    pool = load_pool(str(tmp_path / "nope.json"))
    assert pool["active_strategies"] == []
    assert pool["pool_version"] == pool_mod.POOL_VERSION

"""Phase S8: strategy outcome attribution tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.strategy_factory.strategy_outcome_attribution import (
    REQUIRED_CHAIN_IDS,
    OutcomeAttributionError,
    append_attributed_outcome,
    attribute_outcome,
    build_strategy_attribution,
    chain_missing_ids,
    load_attributed_outcomes,
    outcomes_for_strategy,
)

NOW = "2026-07-16T00:00:00Z"


def _candidate(primary="S004", matched=("S004", "S008"), direction="LONG"):
    return {
        "status": "ENTRY_CANDIDATE",
        "direction": direction,
        "order_candidate_count": 1,
        "matched_strategy_ids": list(matched),
        "matched_strategy_count": len(matched),
        "primary_strategy_id": primary,
        "primary_strategy_rule_hash": f"hash_{primary}",
        "strategy_pool_version": "active_strategy_pool.v1",
    }


def _primary_spec(strategy_id="S004", version="1.0", generation_id="GEN-001"):
    return {"strategy_id": strategy_id, "strategy_version": version, "generation_id": generation_id,
            "strategy_rule_hash": f"hash_{strategy_id}"}


def _full_chain():
    return {cid: f"{cid}_x" for cid in REQUIRED_CHAIN_IDS}


def _outcome(r=1.8, **extra):
    base = {"r_multiple": r, "net_pnl": 180.0, "exit_reason": "TARGET", "entry_regime": "TREND_UP", "bars_held": 4}
    base.update(extra)
    return base


# -- attribution block --------------------------------------------------------

def test_build_attribution_splits_primary_and_supporting():
    attr = build_strategy_attribution(_candidate(), _primary_spec(), cycle_id="cycle_1")
    assert attr["strategy_id"] == "S004"
    assert attr["supporting_strategy_ids"] == ["S008"]
    assert attr["matched_strategy_count"] == 2
    assert attr["strategy_version"] == "1.0"
    assert attr["strategy_generation_id"] == "GEN-001"
    assert attr["strategy_entry_evaluation_id"].startswith("strategy_entry_evaluation_")


def test_single_match_has_no_supporting():
    attr = build_strategy_attribution(_candidate(primary="S004", matched=("S004",)), _primary_spec())
    assert attr["supporting_strategy_ids"] == []


def test_attribution_requires_candidate_status():
    blocked = {"status": "BLOCKED", "primary_strategy_id": None}
    with pytest.raises(OutcomeAttributionError):
        build_strategy_attribution(blocked, _primary_spec())


def test_attribution_primary_spec_must_match():
    with pytest.raises(OutcomeAttributionError):
        build_strategy_attribution(_candidate(primary="S004"), _primary_spec("S999"))


def test_entry_evaluation_id_varies_by_cycle():
    a = build_strategy_attribution(_candidate(), _primary_spec(), cycle_id="cycle_1")
    b = build_strategy_attribution(_candidate(), _primary_spec(), cycle_id="cycle_2")
    assert a["strategy_entry_evaluation_id"] != b["strategy_entry_evaluation_id"]


# -- outcome attribution ------------------------------------------------------

def test_attribute_outcome_full_chain():
    attr = build_strategy_attribution(_candidate(), _primary_spec(), cycle_id="c1")
    record = attribute_outcome(attr, _outcome(), _full_chain(), now=NOW)
    assert record["strategy_id"] == "S004"
    assert record["supporting_strategy_ids"] == ["S008"]
    assert record["r_multiple"] == 1.8
    assert record["chain_complete"] is True
    assert record["outcome_id"].startswith("strategy_outcome_")
    for cid in REQUIRED_CHAIN_IDS:
        assert record[cid] == f"{cid}_x"


def test_primary_owns_outcome_supporting_recorded_not_credited():
    attr = build_strategy_attribution(_candidate(primary="S004", matched=("S004", "S008")), _primary_spec())
    record = attribute_outcome(attr, _outcome(), _full_chain(), now=NOW)
    # The owner is the primary; the supporter is metadata only.
    assert record["strategy_id"] == "S004"
    assert "S008" in record["supporting_strategy_ids"]
    assert record["strategy_id"] != "S008"


def test_missing_chain_id_flags_incomplete():
    attr = build_strategy_attribution(_candidate(), _primary_spec())
    partial = _full_chain()
    del partial["execution_id"]
    record = attribute_outcome(attr, _outcome(), partial, now=NOW)
    assert record["chain_complete"] is False
    assert "execution_id" in chain_missing_ids(record)


def test_connectivity_test_outcome_refused():
    attr = build_strategy_attribution(_candidate(), _primary_spec())
    with pytest.raises(OutcomeAttributionError, match="connectivity"):
        attribute_outcome(attr, _outcome(connectivity_test=True), _full_chain(), now=NOW)


def test_attributed_record_is_not_connectivity_test():
    attr = build_strategy_attribution(_candidate(), _primary_spec())
    record = attribute_outcome(attr, _outcome(), _full_chain(), now=NOW)
    assert record["connectivity_test"] is False


# -- persistence / query ------------------------------------------------------

def test_persist_and_query_by_strategy(tmp_path):
    registry = str(tmp_path / "strategy_attributed_outcome_registry.jsonl")
    attr_a = build_strategy_attribution(_candidate(primary="S004"), _primary_spec("S004"), cycle_id="c1")
    attr_b = build_strategy_attribution(_candidate(primary="S008", matched=("S008",)), _primary_spec("S008"), cycle_id="c2")
    append_attributed_outcome(registry, attribute_outcome(attr_a, _outcome(r=2.0), _full_chain(), now=NOW))
    append_attributed_outcome(registry, attribute_outcome(attr_a, _outcome(r=-1.0), _full_chain(), now=NOW))
    append_attributed_outcome(registry, attribute_outcome(attr_b, _outcome(r=1.0), _full_chain(), now=NOW))

    records = load_attributed_outcomes(registry)
    assert len(records) == 3
    s004 = outcomes_for_strategy(records, "S004")
    assert len(s004) == 2
    assert [r["r_multiple"] for r in s004] == [2.0, -1.0]
    assert len(outcomes_for_strategy(records, "S008")) == 1


def test_supporting_appearance_not_counted_as_ownership(tmp_path):
    registry = str(tmp_path / "reg.jsonl")
    # S004 primary, S008 supporting on the same order.
    attr = build_strategy_attribution(_candidate(primary="S004", matched=("S004", "S008")), _primary_spec("S004"))
    append_attributed_outcome(registry, attribute_outcome(attr, _outcome(), _full_chain(), now=NOW))
    records = load_attributed_outcomes(registry)
    # S008 co-fired but owns zero outcomes -> no double counting.
    assert outcomes_for_strategy(records, "S008") == []
    assert len(outcomes_for_strategy(records, "S004")) == 1

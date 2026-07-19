"""Multibook M1: the book kernel holds one position per strategy book,
enforces the open caps, settles books independently, and — disabled — is the
single-book kernel, unchanged."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.config import load_config
from crypto_ai_system.execution import paper_book_kernel as books
from crypto_ai_system.execution import paper_position_kernel as single


def _cfg(tmp_path):
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "storage" / "registries")
    cfg.settings.setdefault("storage", {})["latest_dir"] = str(tmp_path / "storage" / "latest")
    return cfg


def _intent(direction: str = "LONG", strategy_id: str | None = "S271"):
    long = direction == "LONG"
    intent = {
        "side": "BUY" if long else "SELL",
        "direction": direction,
        "entry_price": 100.0,
        "stop_loss": 98.0 if long else 102.0,
        "take_profit": 104.0 if long else 96.0,
        "quantity": 0.1,
    }
    if strategy_id is not None:
        intent["strategy_id"] = strategy_id
    return intent


def _execution(direction: str = "LONG", strategy_id: str | None = "S271", execution_id: str = "e1"):
    return {
        "execution_id": execution_id,
        "order_intent_id": f"oi_{execution_id}",
        "decision_id": "d1",
        "risk_gate_id": "rg1",
        "research_signal_id": "rs1",
        "simulated_fill": {"avg_fill_price": 100.0, "filled_quantity": 0.1, "fill_status": "FILLED"},
        "expected_order_intent": _intent(direction, strategy_id),
    }


def _reconciliation(execution_id: str = "e1"):
    return {
        "reconciliation_id": f"r_{execution_id}",
        "execution_id": execution_id,
        "order_intent_id": f"oi_{execution_id}",
        "decision_id": "d1",
        "risk_gate_id": "rg1",
        "research_signal_id": "rs1",
        "profile_id": "p1",
        "reconciled": True,
        "reconciliation_mismatch": False,
        "reconciliation_evidence_hash": "hash1",
        "expected_order_intent": _intent(),
        "simulated_fill": {"avg_fill_price": 100.0, "filled_quantity": 0.1, "fill_status": "FILLED"},
    }


def _open(cfg, direction="LONG", strategy_id="S271", execution_id="e1", enabled=True):
    return books.open_in_book(
        _execution(direction, strategy_id, execution_id), _reconciliation(execution_id),
        cycle_id="cyc1", cfg=cfg, enabled=enabled,
    )


# --- disabled: the single-book kernel, unchanged --------------------------------


def test_disabled_delegates_to_the_single_kernel(tmp_path):
    cfg = _cfg(tmp_path)
    pos, refusal = _open(cfg, enabled=False)
    assert refusal is None
    assert pos["status"] == "OPEN" and "book_id" not in pos
    # the single kernel's file is the store; no books file appears
    assert single.has_open_position(cfg) is True
    assert not (tmp_path / "storage" / "latest" / "paper_books.json").exists()

    closed = books.settle_books({"high": 99.0, "low": 97.0}, last_close=97.5, cfg=cfg, enabled=False)
    assert len(closed) == 1 and closed[0]["close_reason"] == "stop_loss"
    assert single.has_open_position(cfg) is False


def test_disabled_position_fields_match_the_single_kernel(tmp_path):
    cfg_a = _cfg(tmp_path / "a")
    cfg_b = _cfg(tmp_path / "b")
    via_books, _ = _open(cfg_a, enabled=False)
    direct = single.open_from_execution(_execution(), _reconciliation(), cycle_id="cyc1", cfg=cfg_b)
    volatile = {"opened_at_utc", "position_id"}
    assert {k: v for k, v in via_books.items() if k not in volatile} == \
           {k: v for k, v in direct.items() if k not in volatile}


# --- enabled: independent books under the caps ----------------------------------


def test_two_books_hold_positions_simultaneously(tmp_path):
    cfg = _cfg(tmp_path)
    pos1, r1 = _open(cfg, "LONG", "S271", "e1")
    pos2, r2 = _open(cfg, "SHORT", "S1218", "e2")
    assert (r1, r2) == (None, None)
    assert pos1["book_id"] == "S271" and pos2["book_id"] == "S1218"
    assert set(books.open_books(cfg)) == {"S271", "S1218"}
    # multibook mode never touches the single kernel's slot
    assert single.has_open_position(cfg) is False


def test_research_entries_share_the_default_book(tmp_path):
    cfg = _cfg(tmp_path)
    pos, refusal = _open(cfg, "LONG", None, "e1")
    assert refusal is None and pos["book_id"] == books.DEFAULT_BOOK_ID
    pos2, refusal2 = _open(cfg, "LONG", "research_bridge_v2", "e2")
    assert pos2 is None and refusal2 == books.REFUSED_BOOK_ALREADY_OPEN


def test_one_position_per_book(tmp_path):
    cfg = _cfg(tmp_path)
    _open(cfg, "LONG", "S271", "e1")
    pos, refusal = _open(cfg, "SHORT", "S271", "e2")
    assert pos is None and refusal == books.REFUSED_BOOK_ALREADY_OPEN


def test_global_open_book_cap(tmp_path):
    cfg = _cfg(tmp_path)
    for i, direction in enumerate(("LONG", "LONG", "LONG", "SHORT", "SHORT")):
        _, refusal = _open(cfg, direction, f"S{i}", f"e{i}")
        assert refusal is None
    pos, refusal = _open(cfg, "SHORT", "S9", "e9")
    assert pos is None and refusal == books.REFUSED_MAX_OPEN_BOOKS
    assert len(books.open_books(cfg)) == 5


def test_same_direction_cap(tmp_path):
    cfg = _cfg(tmp_path)
    for i in range(3):
        _, refusal = _open(cfg, "LONG", f"S{i}", f"e{i}")
        assert refusal is None
    pos, refusal = _open(cfg, "LONG", "S3", "e3")
    assert pos is None and refusal == books.REFUSED_MAX_SAME_DIRECTION
    # the other direction is still allowed
    pos, refusal = _open(cfg, "SHORT", "S4", "e4")
    assert refusal is None and pos["book_id"] == "S4"


def test_books_settle_independently_with_attribution(tmp_path):
    cfg = _cfg(tmp_path)
    _open(cfg, "LONG", "S271", "e1")   # sl 98
    _open(cfg, "SHORT", "S1218", "e2")  # sl 102, tp 96

    closed = books.settle_books({"high": 99.0, "low": 97.0}, last_close=97.5, cfg=cfg, enabled=True)
    assert len(closed) == 1
    assert closed[0]["book_id"] == "S271"
    assert closed[0]["close_reason"] == "stop_loss"
    assert closed[0]["result_R"] == -1.0
    assert closed[0]["outcome_id"]
    # the short book is untouched and its holding clock advanced
    remaining = books.open_books(cfg)
    assert set(remaining) == {"S1218"}
    assert remaining["S1218"]["holding_candles"] == 1


def test_settled_book_frees_its_slot(tmp_path):
    cfg = _cfg(tmp_path)
    _open(cfg, "LONG", "S271", "e1")
    books.settle_books({"high": 99.0, "low": 97.0}, last_close=97.5, cfg=cfg, enabled=True)
    pos, refusal = _open(cfg, "LONG", "S271", "e3")
    assert refusal is None and pos["book_id"] == "S271"


def test_close_summary_carries_the_position_for_attribution(tmp_path):
    """The caller has no single slot to read the closed position back from."""
    cfg = _cfg(tmp_path)
    _open(cfg, "LONG", "S271", "e1")
    closed = books.settle_books({"high": 99.0, "low": 97.0}, last_close=97.5, cfg=cfg, enabled=True)
    position = closed[0]["position"]
    assert position["strategy_id"] == "S271"
    assert position["entry_price"] == 100.0


def test_paper_gate_max_open_positions_follows_the_flag(monkeypatch):
    import config.settings as settings

    assert books.paper_gate_max_open_positions(enabled=False) == 1
    monkeypatch.setattr(settings, "MULTIBOOK_MAX_OPEN_BOOKS", 5, raising=False)
    assert books.paper_gate_max_open_positions(enabled=True) == 5

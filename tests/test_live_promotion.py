"""L5 (partial): live promotion evidence from clean canary orders."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.execution import live_promotion as promo


def _reg(tmp_path):
    return str(tmp_path / "live_canary_order_registry.jsonl")


def test_only_clean_orders_count(tmp_path):
    reg = _reg(tmp_path)
    promo.record_canary_order(reconcile_status="RECONCILED", registry_file=reg)
    promo.record_canary_order(reconcile_status="MISMATCH", mismatches=["x"], registry_file=reg)
    promo.record_canary_order(reconcile_status="RECONCILED", mismatches=["y"], registry_file=reg)  # not clean
    promo.record_canary_order(reconcile_status="NO_SUBMISSION", registry_file=reg)
    assert promo.clean_canary_order_count(registry_file=reg) == 1


def test_promotion_ready_threshold(tmp_path):
    reg = _reg(tmp_path)
    for _ in range(3):
        promo.record_canary_order(reconcile_status="RECONCILED", registry_file=reg)
    assert promo.live_promotion_ready(3, registry_file=reg) is True
    assert promo.live_promotion_ready(4, registry_file=reg) is False


def test_no_evidence_is_not_ready(tmp_path):
    reg = _reg(tmp_path)
    assert promo.live_promotion_ready(3, registry_file=reg) is False


def test_nonpositive_requirement_refused(tmp_path):
    reg = _reg(tmp_path)
    for _ in range(3):
        promo.record_canary_order(reconcile_status="RECONCILED", registry_file=reg)
    # A promotion with no required evidence is refused, not auto-approved.
    assert promo.live_promotion_ready(0, registry_file=reg) is False

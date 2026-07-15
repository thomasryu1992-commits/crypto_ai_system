"""P0-2: strategy signed-testnet orders require a real, registry-backed RiskGate
record — a bare boolean + free-form id must not authorise execution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.time_utils import parse_time
from crypto_ai_system.config import load_config
from crypto_ai_system.registry.base_registry import registry_path
from crypto_ai_system.registry.risk_gate_registry import (
    REASON_EXPIRED,
    REASON_INTEGRITY,
    REASON_INTENT_HASH_MISMATCH,
    REASON_NOT_APPROVED,
    REASON_PROFILE_MISMATCH,
    REASON_RECORD_MISSING,
    REASON_STAGE_MISMATCH,
    get_risk_gate_record,
    persist_risk_gate_record,
    verify_strategy_risk_gate,
)
from crypto_ai_system.utils.audit import sha256_json

_HASH = "risk_gate_registry_record_sha256"
_NOW = parse_time("2026-07-15T00:00:00Z")


def _record(**over):
    rec = {
        "risk_gate_id": "rg_1",
        "approved": True,
        "stage": "signed_testnet",
        "profile_id": "p1",
        "expires_at_utc": "2999-01-01T00:00:00Z",
    }
    rec.update(over)
    rec[_HASH] = sha256_json({k: v for k, v in rec.items() if k != _HASH})
    return rec


def _intent(**over):
    base = {"profile_id": "p1", "risk_gate_id": "rg_1"}
    base.update(over)
    return base


# -- pure verification --------------------------------------------------

def test_missing_record_denied():
    v = verify_strategy_risk_gate(None, _intent(), execution_stage="signed_testnet", now=_NOW)
    assert v["approved"] is False
    assert REASON_RECORD_MISSING in v["reasons"]


def test_valid_record_approved():
    v = verify_strategy_risk_gate(_record(), _intent(), execution_stage="signed_testnet", now=_NOW)
    assert v["approved"] is True
    assert v["reasons"] == []


def test_not_approved_denied():
    v = verify_strategy_risk_gate(_record(approved=False), _intent(), execution_stage="signed_testnet", now=_NOW)
    assert REASON_NOT_APPROVED in v["reasons"]


def test_stage_mismatch_denied():
    v = verify_strategy_risk_gate(_record(stage="paper"), _intent(), execution_stage="signed_testnet", now=_NOW)
    assert REASON_STAGE_MISMATCH in v["reasons"]


def test_profile_mismatch_denied():
    v = verify_strategy_risk_gate(_record(profile_id="other"), _intent(), execution_stage="signed_testnet", now=_NOW)
    assert REASON_PROFILE_MISMATCH in v["reasons"]


def test_expired_denied():
    v = verify_strategy_risk_gate(
        _record(expires_at_utc="2000-01-01T00:00:00Z"), _intent(), execution_stage="signed_testnet", now=_NOW
    )
    assert REASON_EXPIRED in v["reasons"]


def test_tampered_record_denied():
    rec = _record()
    rec["approved"] = True
    rec["profile_id"] = "tampered_after_hash"  # mutate without recomputing hash
    v = verify_strategy_risk_gate(rec, _intent(profile_id="tampered_after_hash"), execution_stage="signed_testnet", now=_NOW)
    assert REASON_INTEGRITY in v["reasons"]


def test_bound_intent_hash_mismatch_denied():
    v = verify_strategy_risk_gate(
        _record(order_intent_hash="abc"),
        _intent(order_intent_hash="xyz"),
        execution_stage="signed_testnet",
        now=_NOW,
    )
    assert REASON_INTENT_HASH_MISMATCH in v["reasons"]


def test_bound_intent_hash_match_ok():
    v = verify_strategy_risk_gate(
        _record(order_intent_hash="abc"),
        _intent(order_intent_hash="abc"),
        execution_stage="signed_testnet",
        now=_NOW,
    )
    assert v["approved"] is True


# -- registry persistence -----------------------------------------------

def _cfg(tmp_path):
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "storage" / "registries")
    cfg.settings.setdefault("storage", {})["latest_dir"] = str(tmp_path / "storage" / "latest")
    return cfg


def test_persist_and_get_roundtrip(tmp_path):
    cfg = _cfg(tmp_path)
    result = {"risk_gate_id": "rg_1", "approved": True, "stage": "signed_testnet", "profile_id": "p1"}
    persisted = persist_risk_gate_record(result, cfg=cfg, ttl_seconds=300)

    assert persisted["expires_at_utc"]
    assert registry_path(cfg, "risk_gate_registry").exists()

    got = get_risk_gate_record("rg_1", cfg=cfg)
    assert got is not None
    assert got["risk_gate_id"] == "rg_1"

    # A record just persisted (TTL 300s) verifies against a matching intent.
    verdict = verify_strategy_risk_gate(got, _intent(), execution_stage="signed_testnet")
    assert verdict["approved"] is True, verdict


def test_get_unknown_id_returns_none(tmp_path):
    cfg = _cfg(tmp_path)
    assert get_risk_gate_record("nope", cfg=cfg) is None
    assert get_risk_gate_record("", cfg=cfg) is None

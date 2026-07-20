"""Ambiguous-submit resolution (QA fix): a failed submit that may have reached
the venue is settled by querying the client order id — never assumed away.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.execution.retry_policy import (
    classify_exchange_error,
    is_ambiguous_submit,
    resolve_ambiguous_submit,
)


# -- is_ambiguous_submit -------------------------------------------------------

def test_confirmed_submit_is_not_ambiguous() -> None:
    assert is_ambiguous_submit({"submitted": True}) is False


def test_definitive_4xx_rejection_is_not_ambiguous() -> None:
    submit = {"submitted": False, "classification": classify_exchange_error(status_code=400)}
    assert is_ambiguous_submit(submit) is False


def test_timeout_is_ambiguous() -> None:
    submit = {"submitted": False,
              "classification": classify_exchange_error(error_name="ReadTimeout")}
    assert is_ambiguous_submit(submit) is True


def test_5xx_and_rate_limit_are_ambiguous() -> None:
    for status in (500, 503, 429):
        submit = {"submitted": False, "classification": classify_exchange_error(status_code=status)}
        assert is_ambiguous_submit(submit) is True, status


def test_missing_classification_fails_toward_ambiguous() -> None:
    assert is_ambiguous_submit({"submitted": False}) is True


# -- resolve_ambiguous_submit --------------------------------------------------

def test_order_found_at_venue_resolves_to_exists() -> None:
    def query(symbol, client_order_id):
        return {"ok": True, "response": {"status": "FILLED", "orderId": 1}}

    resolution = resolve_ambiguous_submit(query, "BTCUSDT", "cid1")
    assert resolution["order_exists"] is True
    assert resolution["order_status"] == "FILLED"


def test_order_not_found_code_resolves_to_not_exists() -> None:
    def query(symbol, client_order_id):
        return {"ok": False, "error": {"code": -2013, "msg": "Order does not exist."}}

    resolution = resolve_ambiguous_submit(query, "BTCUSDT", "cid1")
    assert resolution["order_exists"] is False


def test_query_failure_stays_unresolved() -> None:
    def query(symbol, client_order_id):
        return {"ok": False, "error": {"code": -1000, "msg": "unknown"}}

    assert resolve_ambiguous_submit(query, "BTCUSDT", "cid1")["order_exists"] is None


def test_query_exception_stays_unresolved_and_never_raises() -> None:
    def query(symbol, client_order_id):
        raise ConnectionError("network down")

    assert resolve_ambiguous_submit(query, "BTCUSDT", "cid1")["order_exists"] is None

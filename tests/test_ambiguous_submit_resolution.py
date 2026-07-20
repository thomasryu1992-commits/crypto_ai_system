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
    scrub_secret_params,
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


# -- scrub_secret_params -------------------------------------------------------

def test_signature_is_scrubbed_from_exception_text() -> None:
    # The shape a requests MaxRetryError message takes: full URL with query.
    text = ("HTTPSConnectionPool(host='fapi.binance.com', port=443): Max retries "
            "exceeded with url: /fapi/v1/order?symbol=BTCUSDT&quantity=0.001"
            "&timestamp=1700000000000&signature=0a1b2c3d4e5f67890a1b2c3d4e5f6789")
    scrubbed = scrub_secret_params(text)
    assert "0a1b2c3d4e5f" not in scrubbed
    assert "signature=***redacted***" in scrubbed
    assert "symbol=BTCUSDT" in scrubbed  # non-secret params untouched


def test_scrub_is_a_noop_without_a_signature() -> None:
    assert scrub_secret_params("ReadTimeout: timed out") == "ReadTimeout: timed out"


def test_adapter_transport_error_is_scrubbed_end_to_end() -> None:
    from crypto_ai_system.execution.live_canary_adapter import LiveCanaryAdapter

    def leaking_transport(method, url, params, headers, timeout):
        raise ConnectionError(
            f"Max retries exceeded with url: {url}?symbol=BTCUSDT&signature={params['signature']}"
        )

    adapter = LiveCanaryAdapter("k", "s", base_url="https://fapi.binance.com",
                                transport=leaking_transport)
    result = adapter.submit_order({"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.001,
                                   "client_order_id": "c1"})
    assert "signature=***redacted***" in result["error"]
    assert params_signature_absent(result["error"])


def params_signature_absent(text: str) -> bool:
    import re

    return re.search(r"signature=[0-9a-fA-F]{10,}", text) is None

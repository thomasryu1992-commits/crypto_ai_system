from __future__ import annotations

from typing import Any, Callable, Mapping

# Binance: "Order does not exist" — the only venue answer that PROVES an
# ambiguous submit never reached the book.
ORDER_NOT_FOUND_CODES = {-2013}


def classify_exchange_error(status_code: int | None = None, error_name: str | None = None) -> dict:
    if status_code == 429:
        return {
            "state": "UNKNOWN",
            "retry": False,
            "action": "BACKOFF_AND_QUERY_BY_CLIENT_ORDER_ID",
            "reason": "rate_limit",
        }
    if error_name and "timeout" in error_name.lower():
        return {
            "state": "UNKNOWN",
            "retry": False,
            "action": "QUERY_BY_CLIENT_ORDER_ID_BEFORE_RETRY",
            "reason": "network_timeout",
        }
    if status_code and 400 <= status_code < 500:
        return {"state": "REJECTED", "retry": False, "action": "DO_NOT_RETRY", "reason": "client_error"}
    if status_code and status_code >= 500:
        return {
            "state": "UNKNOWN",
            "retry": True,
            "action": "LIMITED_BACKOFF_THEN_QUERY",
            "reason": "exchange_server_error",
        }
    return {"state": "UNKNOWN", "retry": False, "action": "MANUAL_REVIEW", "reason": "unknown_error"}


def is_ambiguous_submit(submit: Mapping[str, Any]) -> bool:
    """True when a failed submit may still have reached the venue.

    A definitive venue rejection (4xx classification REJECTED) is the only
    failure that proves nothing happened; a timeout / 5xx / rate-limit /
    unclassified failure after the POST left this process is ambiguous and must
    be resolved by querying the client order id — never assumed away.
    """
    if submit.get("submitted"):
        return False
    classification = submit.get("classification") or {}
    return classification.get("state") != "REJECTED"


def resolve_ambiguous_submit(
    query_order: Callable[[str, str], dict],
    symbol: str,
    client_order_id: str,
) -> dict[str, Any]:
    """Query the venue by client order id to settle an ambiguous submit.

    Returns ``order_exists``: True (it reached the book — treat as submitted),
    False (venue says the order does not exist — genuinely not submitted), or
    None (the query itself failed — still unresolved; the caller must account
    for the order as possibly-live, never as "nothing happened").
    """
    try:
        query = query_order(symbol, client_order_id)
    except Exception as exc:  # noqa: BLE001 - resolution must never raise into the submit path
        return {"order_exists": None, "error": f"{type(exc).__name__}", "query_result": None}
    if not isinstance(query, dict):
        return {"order_exists": None, "query_result": None}
    if query.get("ok"):
        response = query.get("response") if isinstance(query.get("response"), dict) else {}
        return {
            "order_exists": True,
            "order_status": response.get("status"),
            "query_result": query,
        }
    error = query.get("error") if isinstance(query.get("error"), dict) else {}
    if error.get("code") in ORDER_NOT_FOUND_CODES:
        return {"order_exists": False, "query_result": query}
    return {"order_exists": None, "query_result": query}

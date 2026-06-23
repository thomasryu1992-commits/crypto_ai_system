from __future__ import annotations


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

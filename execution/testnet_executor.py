from __future__ import annotations

"""Disabled compatibility surface for legacy `execution.testnet_executor` imports.

Step257 policy:
- this module is intentionally not ported to `crypto_ai_system.execution.testnet_executor`;
- default behavior is a local TESTNET_ORDER_SKIPPED audit row;
- enabling signed testnet orders still fails closed with NotImplementedError;
- root package deletion remains postponed while this explicit surface exists.
"""

from core.json_io import append_jsonl
from core.time_utils import utc_now_iso
from config.settings import ENABLE_TESTNET_ORDERS, TESTNET_ORDER_LOG_PATH


def _classify_disabled_stub_recovery_policy(error_name: str | None = None) -> dict:
    """Local policy for the disabled testnet stub.

    This deliberately avoids importing `execution.retry_policy` because that file is a
    thin canonical wrapper and requires `src/crypto_ai_system` to be importable.
    Step257 locks this module as a plain-checkout-safe disabled compatibility
    surface, not as a canonical execution implementation.
    """
    if error_name and "timeout" in error_name.lower():
        return {
            "state": "UNKNOWN",
            "retry": False,
            "action": "QUERY_BY_CLIENT_ORDER_ID_BEFORE_RETRY",
            "reason": "network_timeout",
            "source": "local_disabled_testnet_stub_policy",
        }
    return {
        "state": "UNKNOWN",
        "retry": False,
        "action": "MANUAL_REVIEW",
        "reason": "disabled_testnet_stub_recovery_not_implemented",
        "source": "local_disabled_testnet_stub_policy",
    }


COMPATIBILITY_SURFACE = "DISABLED_EXECUTION_COMPATIBILITY_SURFACE"
DISPOSITION = "KEEP_EXPLICIT_LEGACY_COMPATIBILITY"
PORT_TO_CANONICAL_ALLOWED = False
CANONICAL_LIVE_EXECUTION_PORT_ALLOWED = False
CANONICAL_TESTNET_EXECUTION_PORT_ALLOWED = False
ROOT_PACKAGE_DELETION_ALLOWED = False
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
ORDER_ROUTING_ENABLED_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED = False
SKIPPED_BEHAVIOR_SUPPORTED = True
NOT_IMPLEMENTED_BEHAVIOR_LOCKED = True
DISABLED_REASON = (
    "execution.testnet_executor is a Step257 disabled compatibility surface; "
    "signed testnet execution must be designed separately and must not be ported from this root module."
)


def compatibility_status() -> dict:
    """Return the locked Step257 policy for tests, reports, and operators."""
    return {
        "module": "execution.testnet_executor",
        "compatibility_surface": COMPATIBILITY_SURFACE,
        "disposition": DISPOSITION,
        "port_to_canonical_allowed": PORT_TO_CANONICAL_ALLOWED,
        "canonical_live_execution_port_allowed": CANONICAL_LIVE_EXECUTION_PORT_ALLOWED,
        "canonical_testnet_execution_port_allowed": CANONICAL_TESTNET_EXECUTION_PORT_ALLOWED,
        "root_package_deletion_allowed": ROOT_PACKAGE_DELETION_ALLOWED,
        "live_trading_allowed_by_this_module": LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        "order_routing_enabled_by_this_module": ORDER_ROUTING_ENABLED_BY_THIS_MODULE,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED,
        "skipped_behavior_supported": SKIPPED_BEHAVIOR_SUPPORTED,
        "not_implemented_behavior_locked": NOT_IMPLEMENTED_BEHAVIOR_LOCKED,
        "disabled_reason": DISABLED_REASON,
    }


class TestnetExecutor:
    """Fail-closed legacy Binance testnet stub."""

    def place_order(self, intent: dict) -> dict:
        if not ENABLE_TESTNET_ORDERS:
            result = {
                "created_at": utc_now_iso(),
                "state": "VALIDATED",
                "status": "TESTNET_ORDER_SKIPPED",
                "reason": "ENABLE_TESTNET_ORDERS_false",
                "intent_id": intent.get("intent_id"),
                "client_order_id": intent.get("client_order_id"),
                "compatibility_surface": COMPATIBILITY_SURFACE,
                "disposition": DISPOSITION,
                "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED,
                "root_package_deletion_allowed": ROOT_PACKAGE_DELETION_ALLOWED,
            }
            append_jsonl(TESTNET_ORDER_LOG_PATH, result)
            return result

        raise NotImplementedError(DISABLED_REASON)

    def recover_unknown_order(self, client_order_id: str) -> dict:
        result = {
            "created_at": utc_now_iso(),
            "state": "UNKNOWN",
            "status": "RECOVERY_QUERY_NOT_IMPLEMENTED",
            "client_order_id": client_order_id,
            "policy": _classify_disabled_stub_recovery_policy(error_name="timeout"),
            "compatibility_surface": COMPATIBILITY_SURFACE,
            "disposition": DISPOSITION,
            "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED,
        }
        append_jsonl(TESTNET_ORDER_LOG_PATH, result)
        return result

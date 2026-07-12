from __future__ import annotations

"""Disabled compatibility surface for legacy `execution.live_executor` imports.

Step257 policy:
- this module is intentionally not ported to `crypto_ai_system.execution.live_executor`;
- it exists only so old imports fail closed instead of disappearing silently;
- it must never submit live orders from the root compatibility package;
- root package deletion remains postponed while this explicit surface exists.
"""

COMPATIBILITY_SURFACE = "DISABLED_EXECUTION_COMPATIBILITY_SURFACE"
DISPOSITION = "KEEP_EXPLICIT_LEGACY_COMPATIBILITY"
PORT_TO_CANONICAL_ALLOWED = False
CANONICAL_LIVE_EXECUTION_PORT_ALLOWED = False
ROOT_PACKAGE_DELETION_ALLOWED = False
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
ORDER_ROUTING_ENABLED_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED = False
SKIPPED_BEHAVIOR_SUPPORTED = False
NOT_IMPLEMENTED_BEHAVIOR_LOCKED = True
DISABLED_REASON = (
    "execution.live_executor is a Step257 disabled compatibility surface; "
    "canonical live execution must be designed separately and must not be ported from this root module."
)


def compatibility_status() -> dict:
    """Return the locked Step257 policy for tests, reports, and operators."""
    return {
        "module": "execution.live_executor",
        "compatibility_surface": COMPATIBILITY_SURFACE,
        "disposition": DISPOSITION,
        "port_to_canonical_allowed": PORT_TO_CANONICAL_ALLOWED,
        "canonical_live_execution_port_allowed": CANONICAL_LIVE_EXECUTION_PORT_ALLOWED,
        "root_package_deletion_allowed": ROOT_PACKAGE_DELETION_ALLOWED,
        "live_trading_allowed_by_this_module": LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        "order_routing_enabled_by_this_module": ORDER_ROUTING_ENABLED_BY_THIS_MODULE,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED,
        "skipped_behavior_supported": SKIPPED_BEHAVIOR_SUPPORTED,
        "not_implemented_behavior_locked": NOT_IMPLEMENTED_BEHAVIOR_LOCKED,
        "disabled_reason": DISABLED_REASON,
    }


class LiveExecutor:
    """Fail-closed legacy live executor stub."""

    def place_order(self, intent: dict) -> dict:
        raise NotImplementedError(DISABLED_REASON)

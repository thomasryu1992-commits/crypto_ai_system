from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

EXCHANGE_ADAPTER_CONTRACT_VERSION = "step273_exchange_adapter_contract_v1"
ORDER_SUBMISSION_ENABLED_BY_CONTRACT = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED = False


@dataclass(frozen=True)
class AdapterCapability:
    """Review-only exchange adapter capability declaration.

    Step273 intentionally defines the adapter contract before enabling any signed
    testnet order submission.  Capabilities are metadata used by pre-testnet
    readiness checks; they must not be treated as permission to place orders.
    """

    venue: str
    environment: str = "testnet"
    supports_balance_read: bool = False
    supports_positions_read: bool = False
    supports_open_orders_read: bool = False
    supports_orderbook_read: bool = False
    supports_fee_estimate: bool = False
    supports_slippage_estimate: bool = False
    supports_min_order_validation: bool = False
    supports_place_order: bool = False
    supports_cancel_order: bool = False
    supports_fetch_order: bool = False
    supported_order_types: list[str] = field(default_factory=lambda: ["MARKET", "LIMIT"])
    supported_time_in_force: list[str] = field(default_factory=lambda: ["GTC", "IOC"])
    testnet_only: bool = True
    base_url: str | None = None
    contract_version: str = EXCHANGE_ADAPTER_CONTRACT_VERSION
    created_at_utc: str = field(default_factory=utc_now_canonical)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["capability_sha256"] = sha256_json({k: v for k, v in payload.items() if k != "created_at_utc"})
        return payload


def required_pretestnet_capability_names() -> list[str]:
    return [
        "supports_balance_read",
        "supports_positions_read",
        "supports_open_orders_read",
        "supports_orderbook_read",
        "supports_fee_estimate",
        "supports_slippage_estimate",
        "supports_min_order_validation",
        "supports_fetch_order",
    ]


def validate_adapter_capabilities(capabilities: Mapping[str, Any] | AdapterCapability) -> dict[str, Any]:
    data = capabilities.to_dict() if isinstance(capabilities, AdapterCapability) else dict(capabilities or {})
    missing: list[str] = []
    blockers: list[str] = []

    for name in required_pretestnet_capability_names():
        if data.get(name) is not True:
            missing.append(name)
            blockers.append(f"ADAPTER_CAPABILITY_{name.upper()}_MISSING")

    environment = str(data.get("environment") or "").strip().lower()
    if environment not in {"testnet", "signed_testnet", "paper_testnet_contract"}:
        blockers.append("ADAPTER_ENVIRONMENT_NOT_TESTNET_BLOCKED")
    if data.get("testnet_only") is not True:
        blockers.append("ADAPTER_TESTNET_ONLY_FALSE_BLOCKED")
    if data.get("supports_place_order") is True:
        blockers.append("ADAPTER_PLACE_ORDER_CAPABILITY_MUST_REMAIN_DISABLED_STEP273")

    payload = {
        "contract_version": EXCHANGE_ADAPTER_CONTRACT_VERSION,
        "venue": data.get("venue"),
        "environment": data.get("environment"),
        "missing_capabilities": sorted(missing),
        "blockers": sorted(set(blockers)),
    }
    return {
        "adapter_contract_validation_id": stable_id("adapter_contract_validation", payload),
        "contract_version": EXCHANGE_ADAPTER_CONTRACT_VERSION,
        "valid": not blockers,
        "contract_ready": not blockers,
        "missing_capabilities": sorted(missing),
        "block_reasons": sorted(set(blockers)),
        "capabilities": data,
        "created_at_utc": utc_now_canonical(),
    }


class DisabledExchangeAdapter:
    """Step273 adapter contract implementation that never submits orders.

    Read methods return deterministic contract stubs.  place_order/cancel_order
    are hard-blocked to prevent accidental signed testnet or live submission.
    """

    def __init__(self, *, venue: str = "binance_futures", environment: str = "testnet") -> None:
        self.venue = venue
        self.environment = environment
        self.capability = AdapterCapability(
            venue=venue,
            environment=environment,
            supports_balance_read=True,
            supports_positions_read=True,
            supports_open_orders_read=True,
            supports_orderbook_read=True,
            supports_fee_estimate=True,
            supports_slippage_estimate=True,
            supports_min_order_validation=True,
            supports_place_order=False,
            supports_cancel_order=False,
            supports_fetch_order=True,
            testnet_only=True,
        )

    def get_capabilities(self) -> dict[str, Any]:
        return self.capability.to_dict()

    def get_balance(self) -> dict[str, Any]:
        return self._read_stub("BALANCE_READ_CONTRACT_ONLY")

    def get_positions(self) -> dict[str, Any]:
        return self._read_stub("POSITIONS_READ_CONTRACT_ONLY")

    def get_open_orders(self) -> dict[str, Any]:
        return self._read_stub("OPEN_ORDERS_READ_CONTRACT_ONLY")

    def get_orderbook(self, symbol: str) -> dict[str, Any]:
        payload = self._read_stub("ORDERBOOK_READ_CONTRACT_ONLY")
        payload["symbol"] = symbol
        payload["spread_bps"] = None
        return payload

    def estimate_fee(self, order_intent: Mapping[str, Any]) -> dict[str, Any]:
        return {
            **self._read_stub("FEE_ESTIMATE_CONTRACT_ONLY"),
            "order_intent_id": order_intent.get("order_intent_id"),
            "fee_bps": None,
            "fee_usd": None,
        }

    def estimate_slippage(self, order_intent: Mapping[str, Any]) -> dict[str, Any]:
        return {
            **self._read_stub("SLIPPAGE_ESTIMATE_CONTRACT_ONLY"),
            "order_intent_id": order_intent.get("order_intent_id"),
            "slippage_bps": None,
        }

    def validate_min_order_size(self, order_intent: Mapping[str, Any]) -> dict[str, Any]:
        notional = float(order_intent.get("notional_usdt") or order_intent.get("notional_usdc") or 0.0)
        min_notional = float(order_intent.get("min_notional_usdt") or 0.0)
        return {
            **self._read_stub("MIN_ORDER_SIZE_VALIDATION_CONTRACT_ONLY"),
            "order_intent_id": order_intent.get("order_intent_id"),
            "notional": notional,
            "min_notional": min_notional,
            "min_order_size_valid": notional >= min_notional,
        }

    def fetch_order(self, order_id: str) -> dict[str, Any]:
        return {**self._read_stub("FETCH_ORDER_CONTRACT_ONLY"), "exchange_order_id": order_id}

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return self._blocked_submission("CANCEL_ORDER_DISABLED_STEP273", {"exchange_order_id": order_id})

    def place_order(self, order_request: Mapping[str, Any]) -> dict[str, Any]:
        return self._blocked_submission("PLACE_ORDER_DISABLED_STEP273", dict(order_request or {}))

    def _read_stub(self, status: str) -> dict[str, Any]:
        return {
            "status": status,
            "venue": self.venue,
            "environment": self.environment,
            "contract_version": EXCHANGE_ADAPTER_CONTRACT_VERSION,
            "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED,
            "order_submission_enabled_by_contract": ORDER_SUBMISSION_ENABLED_BY_CONTRACT,
            "created_at_utc": utc_now_canonical(),
        }

    def _blocked_submission(self, status: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "status": status,
            "venue": self.venue,
            "environment": self.environment,
            "request": dict(payload),
            "submitted": False,
            "exchange_order_id": None,
            "reason": "Step273 defines the signed testnet adapter contract only; order submission remains disabled.",
            "contract_version": EXCHANGE_ADAPTER_CONTRACT_VERSION,
            "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED,
            "order_submission_enabled_by_contract": ORDER_SUBMISSION_ENABLED_BY_CONTRACT,
            "created_at_utc": utc_now_canonical(),
        }

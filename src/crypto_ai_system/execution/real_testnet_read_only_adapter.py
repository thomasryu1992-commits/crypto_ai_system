from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from core.json_io import atomic_write_json

STEP303_REAL_TESTNET_READ_ONLY_ADAPTER_VERSION = "step303_real_testnet_read_only_adapter_v1"
REAL_TESTNET_READ_ONLY_ADAPTER_REGISTRY_NAME = "real_testnet_read_only_adapter_registry"

READ_ONLY_ADAPTER_ORDER_SUBMISSION_ALLOWED = False
READ_ONLY_ADAPTER_PLACE_ORDER_ENABLED = False
READ_ONLY_ADAPTER_CANCEL_ORDER_ENABLED = False
READ_ONLY_ADAPTER_SIGNED_ORDER_EXECUTOR_ENABLED = False
READ_ONLY_ADAPTER_EXTERNAL_ORDER_SUBMISSION_PERFORMED = False
READ_ONLY_ADAPTER_LIVE_TRADING_ALLOWED = False

ReadTransport = Callable[[str, str, Mapping[str, Any]], Mapping[str, Any]]

_REQUIRED_READ_METHODS = [
    "get_balance",
    "get_positions",
    "get_open_orders",
    "get_orderbook",
    "estimate_fee",
    "estimate_slippage",
    "validate_min_order_size",
    "fetch_order",
]


@dataclass(frozen=True)
class RealTestnetReadOnlyAdapterCapability:
    """Step303 read-only venue adapter capability declaration.

    The adapter may be wired to real testnet read endpoints later through a
    transport function, but this contract never enables write methods or signed
    order submission. It is therefore safe to include in source handoff and
    review-only validation without API key value access.
    """

    venue: str
    environment: str = "testnet"
    base_url: str | None = None
    supports_balance_read: bool = True
    supports_positions_read: bool = True
    supports_open_orders_read: bool = True
    supports_orderbook_read: bool = True
    supports_fee_estimate: bool = True
    supports_slippage_estimate: bool = True
    supports_min_order_validation: bool = True
    supports_fetch_order: bool = True
    supports_place_order: bool = False
    supports_cancel_order: bool = False
    supported_order_types: list[str] = field(default_factory=lambda: ["MARKET", "LIMIT"])
    supported_time_in_force: list[str] = field(default_factory=lambda: ["GTC", "IOC"])
    testnet_only: bool = True
    read_only: bool = True
    metadata_only_secret_policy: bool = True
    api_key_value_access_allowed: bool = False
    api_secret_value_access_allowed: bool = False
    secret_file_access_allowed: bool = False
    secret_file_creation_allowed: bool = False
    place_order_enabled: bool = False
    cancel_order_enabled: bool = False
    testnet_order_submission_allowed: bool = False
    signed_order_executor_enabled: bool = False
    external_order_submission_allowed: bool = False
    live_trading_allowed: bool = False
    adapter_version: str = STEP303_REAL_TESTNET_READ_ONLY_ADAPTER_VERSION
    created_at_utc: str = field(default_factory=utc_now_canonical)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["capability_sha256"] = sha256_json(
            {k: v for k, v in payload.items() if k not in {"created_at_utc", "capability_sha256"}}
        )
        return payload


class ReadOnlyAdapterPolicyError(RuntimeError):
    """Raised only for developer misuse of the Step303 read-only adapter."""


def _as_bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_testnet_base_url(base_url: str | None) -> bool:
    text = str(base_url or "").strip().lower()
    if not text:
        return True
    if "mainnet" in text or "api.binance.com" in text or "fapi.binance.com" in text:
        return False
    return "testnet" in text or "sepolia" in text or "sandbox" in text


def _payload_without_hash(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in dict(payload).items() if k not in {"adapter_evidence_sha256", "created_at_utc"}}


def _probe_hash(probe: Mapping[str, Any]) -> str:
    return sha256_json({k: v for k, v in dict(probe).items() if k != "probe_hash"})


class RealTestnetReadOnlyAdapterBase:
    """Read-only testnet adapter base with optional read transport injection.

    The default transport is deterministic and does not perform network IO. A
    real testnet client can be injected as `read_transport`; the adapter will
    still block place_order/cancel_order and will mark all responses as read-only.
    """

    venue = "generic_testnet"
    default_base_url: str | None = None

    def __init__(
        self,
        *,
        environment: str = "testnet",
        base_url: str | None = None,
        read_transport: ReadTransport | None = None,
        transport_name: str | None = None,
    ) -> None:
        self.environment = str(environment or "testnet")
        self.base_url = base_url if base_url is not None else self.default_base_url
        self.read_transport = read_transport
        self.transport_name = transport_name or ("injected_read_transport" if read_transport else "deterministic_no_network_stub")
        if not _is_testnet_base_url(self.base_url):
            raise ReadOnlyAdapterPolicyError("Step303 read-only adapter requires a testnet/sepolia/sandbox base URL.")

    def get_capabilities(self) -> dict[str, Any]:
        capability = RealTestnetReadOnlyAdapterCapability(
            venue=self.venue,
            environment=self.environment,
            base_url=self.base_url,
        )
        return capability.to_dict()

    def get_balance(self) -> dict[str, Any]:
        return self._read("get_balance", "/account/balance", {})

    def get_positions(self) -> dict[str, Any]:
        return self._read("get_positions", "/positionRisk", {})

    def get_open_orders(self, symbol: str | None = None) -> dict[str, Any]:
        params = {"symbol": symbol} if symbol else {}
        return self._read("get_open_orders", "/openOrders", params)

    def get_orderbook(self, symbol: str = "BTCUSDT", limit: int = 50) -> dict[str, Any]:
        return self._read("get_orderbook", "/depth", {"symbol": symbol, "limit": limit})

    def estimate_fee(self, order_intent: Mapping[str, Any]) -> dict[str, Any]:
        notional = _safe_float(order_intent.get("notional_usdt") or order_intent.get("notional_usdc"), 0.0)
        fee_bps = _safe_float(order_intent.get("fee_bps"), 2.5)
        response = self._read("estimate_fee", "/commissionRate", {"symbol": order_intent.get("symbol", "BTCUSDT")})
        response.update(
            {
                "order_intent_id": order_intent.get("order_intent_id"),
                "fee_bps": fee_bps,
                "estimated_fee_usdt": round(notional * fee_bps / 10000.0, 8),
                "fee_model_source": "step303_read_only_estimate",
            }
        )
        return response

    def estimate_slippage(self, order_intent: Mapping[str, Any]) -> dict[str, Any]:
        slippage_bps = _safe_float(order_intent.get("slippage_bps"), 3.0)
        response = self._read("estimate_slippage", "/depth", {"symbol": order_intent.get("symbol", "BTCUSDT"), "limit": 50})
        response.update(
            {
                "order_intent_id": order_intent.get("order_intent_id"),
                "slippage_bps": slippage_bps,
                "slippage_model_source": "step303_read_only_orderbook_estimate",
            }
        )
        return response

    def validate_min_order_size(self, order_intent: Mapping[str, Any]) -> dict[str, Any]:
        notional = _safe_float(order_intent.get("notional_usdt") or order_intent.get("notional_usdc"), 0.0)
        min_notional = _safe_float(order_intent.get("min_notional_usdt"), 1.0)
        response = self._read("validate_min_order_size", "/exchangeInfo", {"symbol": order_intent.get("symbol", "BTCUSDT")})
        response.update(
            {
                "order_intent_id": order_intent.get("order_intent_id"),
                "notional_usdt": notional,
                "min_notional_usdt": min_notional,
                "min_order_size_valid": notional >= min_notional,
            }
        )
        return response

    def fetch_order(self, order_id: str, symbol: str | None = None) -> dict[str, Any]:
        response = self._read("fetch_order", "/order", {"orderId": order_id, "symbol": symbol or "BTCUSDT"})
        response.update({"exchange_order_id": order_id})
        return response

    def place_order(self, order_request: Mapping[str, Any]) -> dict[str, Any]:
        return self._blocked_write("PLACE_ORDER_DISABLED_STEP303_READ_ONLY_ADAPTER", dict(order_request or {}))

    def cancel_order(self, order_id: str, **kwargs: Any) -> dict[str, Any]:
        payload = {"exchange_order_id": order_id, **kwargs}
        return self._blocked_write("CANCEL_ORDER_DISABLED_STEP303_READ_ONLY_ADAPTER", payload)

    def _read(self, method_name: str, path: str, params: Mapping[str, Any]) -> dict[str, Any]:
        transport_response: dict[str, Any]
        transport_called = self.read_transport is not None
        transport_error: str | None = None
        if self.read_transport is not None:
            try:
                transport_response = dict(self.read_transport("GET", path, dict(params)))
            except Exception as exc:  # pragma: no cover - defensive; tests cover blocked evidence via response status.
                transport_response = {}
                transport_error = f"{exc.__class__.__name__}: {exc}"
        else:
            transport_response = self._deterministic_stub_payload(method_name, params)

        return {
            "status": f"{method_name.upper()}_READ_ONLY_TESTNET_READY",
            "method_name": method_name,
            "http_method": "GET",
            "path": path,
            "params": dict(params or {}),
            "venue": self.venue,
            "environment": self.environment,
            "base_url": self.base_url,
            "adapter_version": STEP303_REAL_TESTNET_READ_ONLY_ADAPTER_VERSION,
            "read_only": True,
            "transport_name": self.transport_name,
            "read_transport_called": transport_called,
            "transport_error": transport_error,
            "transport_response": transport_response,
            "external_order_submission_performed": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "live_trading_allowed_by_this_module": False,
            "created_at_utc": utc_now_canonical(),
        }

    def _deterministic_stub_payload(self, method_name: str, params: Mapping[str, Any]) -> dict[str, Any]:
        symbol = str(params.get("symbol") or "BTCUSDT")
        if method_name == "get_balance":
            return {"asset": "USDT", "available_balance": "0", "wallet_balance": "0", "stubbed": True}
        if method_name == "get_positions":
            return {"positions": [], "stubbed": True}
        if method_name == "get_open_orders":
            return {"open_orders": [], "stubbed": True}
        if method_name in {"get_orderbook", "estimate_slippage"}:
            return {"symbol": symbol, "bids": [], "asks": [], "spread_bps": None, "stubbed": True}
        if method_name == "estimate_fee":
            return {"symbol": symbol, "maker_fee_bps": 2.0, "taker_fee_bps": 5.0, "stubbed": True}
        if method_name == "validate_min_order_size":
            return {"symbol": symbol, "filters": [], "stubbed": True}
        if method_name == "fetch_order":
            return {"symbol": symbol, "order": None, "stubbed": True}
        return {"stubbed": True}

    def _blocked_write(self, status: str, request: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "status": status,
            "venue": self.venue,
            "environment": self.environment,
            "base_url": self.base_url,
            "request": dict(request or {}),
            "submitted": False,
            "exchange_order_id": None,
            "reason": "Step303 adapter is read-only. Signed testnet place_order/cancel_order remain disabled.",
            "adapter_version": STEP303_REAL_TESTNET_READ_ONLY_ADAPTER_VERSION,
            "read_transport_called": False,
            "external_order_submission_performed": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "live_trading_allowed_by_this_module": False,
            "created_at_utc": utc_now_canonical(),
        }


class BinanceFuturesTestnetReadOnlyAdapter(RealTestnetReadOnlyAdapterBase):
    venue = "binance_futures_testnet"
    default_base_url = "https://testnet.binancefuture.com"


class ExtendedTestnetReadOnlyAdapter(RealTestnetReadOnlyAdapterBase):
    venue = "extended_testnet"
    default_base_url = "https://api.starknet.sepolia.extended.exchange/api/v1"


def build_read_only_testnet_adapter(kind: str = "binance_futures_testnet", **kwargs: Any) -> RealTestnetReadOnlyAdapterBase:
    normalized = str(kind or "binance_futures_testnet").strip().lower()
    if normalized in {"binance", "binance_futures", "binance_futures_testnet"}:
        return BinanceFuturesTestnetReadOnlyAdapter(**kwargs)
    if normalized in {"extended", "extended_testnet"}:
        return ExtendedTestnetReadOnlyAdapter(**kwargs)
    raise ValueError(f"Unsupported Step303 read-only testnet adapter kind: {kind}")


def validate_real_testnet_read_only_capabilities(capabilities: Mapping[str, Any] | RealTestnetReadOnlyAdapterCapability) -> dict[str, Any]:
    data = capabilities.to_dict() if isinstance(capabilities, RealTestnetReadOnlyAdapterCapability) else dict(capabilities or {})
    blockers: list[str] = []
    for method in _REQUIRED_READ_METHODS:
        flag = {
            "get_balance": "supports_balance_read",
            "get_positions": "supports_positions_read",
            "get_open_orders": "supports_open_orders_read",
            "get_orderbook": "supports_orderbook_read",
            "estimate_fee": "supports_fee_estimate",
            "estimate_slippage": "supports_slippage_estimate",
            "validate_min_order_size": "supports_min_order_validation",
            "fetch_order": "supports_fetch_order",
        }[method]
        if data.get(flag) is not True:
            blockers.append(f"STEP303_{flag.upper()}_MISSING")
    if data.get("read_only") is not True:
        blockers.append("STEP303_ADAPTER_NOT_READ_ONLY")
    if data.get("testnet_only") is not True:
        blockers.append("STEP303_ADAPTER_TESTNET_ONLY_FALSE")
    if not _is_testnet_base_url(data.get("base_url")):
        blockers.append("STEP303_ADAPTER_BASE_URL_NOT_TESTNET")
    if data.get("supports_place_order") is True or data.get("place_order_enabled") is True:
        blockers.append("STEP303_PLACE_ORDER_CAPABILITY_ENABLED_BLOCKED")
    if data.get("supports_cancel_order") is True or data.get("cancel_order_enabled") is True:
        blockers.append("STEP303_CANCEL_ORDER_CAPABILITY_ENABLED_BLOCKED")
    if data.get("testnet_order_submission_allowed") is True:
        blockers.append("STEP303_TESTNET_ORDER_SUBMISSION_ALLOWED_BLOCKED")
    if data.get("signed_order_executor_enabled") is True:
        blockers.append("STEP303_SIGNED_ORDER_EXECUTOR_ENABLED_BLOCKED")
    if data.get("external_order_submission_allowed") is True:
        blockers.append("STEP303_EXTERNAL_ORDER_SUBMISSION_ALLOWED_BLOCKED")
    if data.get("live_trading_allowed") is True:
        blockers.append("STEP303_LIVE_TRADING_ALLOWED_BLOCKED")
    if data.get("api_key_value_access_allowed") is True or data.get("api_secret_value_access_allowed") is True:
        blockers.append("STEP303_API_KEY_VALUE_ACCESS_ALLOWED_BLOCKED")
    if data.get("secret_file_access_allowed") is True or data.get("secret_file_creation_allowed") is True:
        blockers.append("STEP303_SECRET_FILE_ACCESS_OR_CREATION_ALLOWED_BLOCKED")

    payload = {
        "version": STEP303_REAL_TESTNET_READ_ONLY_ADAPTER_VERSION,
        "venue": data.get("venue"),
        "environment": data.get("environment"),
        "base_url": data.get("base_url"),
        "blockers": sorted(set(blockers)),
    }
    return {
        "step303_capability_validation_id": stable_id("step303_capability_validation", payload),
        "version": STEP303_REAL_TESTNET_READ_ONLY_ADAPTER_VERSION,
        "valid": not blockers,
        "read_only_adapter_ready": not blockers,
        "block_reasons": sorted(set(blockers)),
        "capabilities": data,
        "created_at_utc": utc_now_canonical(),
    }


def _build_probe(probe_name: str, response: Mapping[str, Any], *, require_min_valid: bool = False) -> dict[str, Any]:
    data = dict(response or {})
    blockers: list[str] = []
    if not str(data.get("status") or "").endswith("_READ_ONLY_TESTNET_READY"):
        blockers.append(f"STEP303_{probe_name.upper()}_STATUS_INVALID")
    if data.get("external_order_submission_performed") is not False:
        blockers.append(f"STEP303_{probe_name.upper()}_EXTERNAL_ORDER_SUBMISSION_PERFORMED")
    if data.get("testnet_order_submission_allowed") is not False:
        blockers.append(f"STEP303_{probe_name.upper()}_TESTNET_ORDER_SUBMISSION_ALLOWED")
    if data.get("place_order_enabled") is not False or data.get("cancel_order_enabled") is not False:
        blockers.append(f"STEP303_{probe_name.upper()}_WRITE_METHOD_ENABLED")
    if data.get("signed_order_executor_enabled") is not False:
        blockers.append(f"STEP303_{probe_name.upper()}_SIGNED_EXECUTOR_ENABLED")
    if data.get("live_trading_allowed_by_this_module") is not False:
        blockers.append(f"STEP303_{probe_name.upper()}_LIVE_TRADING_ALLOWED")
    if require_min_valid and data.get("min_order_size_valid") is not True:
        blockers.append("STEP303_MIN_ORDER_SIZE_PROBE_INVALID")
    probe = {
        "probe_name": probe_name,
        "status": data.get("status"),
        "adapter_response": data,
        "valid": not blockers,
        "block_reasons": sorted(set(blockers)),
        "external_order_submission_performed": False,
        "testnet_order_submission_allowed": False,
        "created_at_utc": utc_now_canonical(),
    }
    probe["probe_hash"] = _probe_hash(probe)
    return probe


def _build_blocked_write_probe(probe_name: str, response: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(response or {})
    blockers: list[str] = []
    if data.get("submitted") is not False:
        blockers.append(f"STEP303_{probe_name.upper()}_SUBMITTED_BLOCKED")
    if data.get("read_transport_called") is not False:
        blockers.append(f"STEP303_{probe_name.upper()}_TRANSPORT_CALLED_BLOCKED")
    if data.get("external_order_submission_performed") is not False:
        blockers.append(f"STEP303_{probe_name.upper()}_EXTERNAL_SUBMISSION_PERFORMED")
    if data.get("place_order_enabled") is not False or data.get("cancel_order_enabled") is not False:
        blockers.append(f"STEP303_{probe_name.upper()}_WRITE_METHOD_ENABLED")
    if data.get("testnet_order_submission_allowed") is not False:
        blockers.append(f"STEP303_{probe_name.upper()}_TESTNET_ORDER_SUBMISSION_ALLOWED")
    probe = {
        "probe_name": probe_name,
        "status": data.get("status"),
        "adapter_response": data,
        "adapter_method_called": True,
        "write_submission_blocked": not blockers,
        "valid": not blockers,
        "block_reasons": sorted(set(blockers)),
        "external_order_submission_performed": False,
        "testnet_order_submission_allowed": False,
        "created_at_utc": utc_now_canonical(),
    }
    probe["probe_hash"] = _probe_hash(probe)
    return probe


def build_real_testnet_read_only_adapter_evidence(
    *,
    adapter: RealTestnetReadOnlyAdapterBase,
    order_intent: Mapping[str, Any] | None = None,
    symbol: str = "BTCUSDT",
    fetch_order_id: str = "read_only_fetch_probe",
) -> dict[str, Any]:
    intent = dict(order_intent or {"order_intent_id": "step303_read_only_probe", "symbol": symbol, "notional_usdt": 5, "min_notional_usdt": 1})
    capabilities = adapter.get_capabilities()
    capability_validation = validate_real_testnet_read_only_capabilities(capabilities)
    probes = {
        "balance_read_probe": _build_probe("balance_read_probe", adapter.get_balance()),
        "positions_read_probe": _build_probe("positions_read_probe", adapter.get_positions()),
        "open_orders_read_probe": _build_probe("open_orders_read_probe", adapter.get_open_orders(symbol)),
        "orderbook_read_probe": _build_probe("orderbook_read_probe", adapter.get_orderbook(symbol)),
        "fee_estimate_probe": _build_probe("fee_estimate_probe", adapter.estimate_fee(intent)),
        "slippage_estimate_probe": _build_probe("slippage_estimate_probe", adapter.estimate_slippage(intent)),
        "min_order_size_probe": _build_probe(
            "min_order_size_probe",
            adapter.validate_min_order_size(intent),
            require_min_valid=True,
        ),
        "fetch_order_probe": _build_probe("fetch_order_probe", adapter.fetch_order(fetch_order_id, symbol=symbol)),
    }
    blocked_write_probes = {
        "place_order_block_probe": _build_blocked_write_probe("place_order_block_probe", adapter.place_order(intent)),
        "cancel_order_block_probe": _build_blocked_write_probe("cancel_order_block_probe", adapter.cancel_order(fetch_order_id, symbol=symbol)),
    }
    all_probe_values = [*probes.values(), *blocked_write_probes.values()]
    blockers = [] if capability_validation.get("valid") else list(capability_validation.get("block_reasons", []))
    for probe in all_probe_values:
        blockers.extend(probe.get("block_reasons", []))
    payload_base = {
        "version": STEP303_REAL_TESTNET_READ_ONLY_ADAPTER_VERSION,
        "venue": capabilities.get("venue"),
        "environment": capabilities.get("environment"),
        "base_url": capabilities.get("base_url"),
        "capability_validation_id": capability_validation.get("step303_capability_validation_id"),
        "read_probe_names": sorted(probes),
        "blocked_write_probe_names": sorted(blocked_write_probes),
        "blockers": sorted(set(blockers)),
    }
    evidence = {
        "real_testnet_read_only_adapter_evidence_id": stable_id("step303_read_only_adapter_evidence", payload_base),
        "version": STEP303_REAL_TESTNET_READ_ONLY_ADAPTER_VERSION,
        "venue": capabilities.get("venue"),
        "environment": capabilities.get("environment"),
        "base_url": capabilities.get("base_url"),
        "capabilities": capabilities,
        "capability_validation": capability_validation,
        "read_only_probes": probes,
        "blocked_write_probes": blocked_write_probes,
        "all_read_probes_valid": all(probe.get("valid") is True for probe in probes.values()),
        "place_cancel_disabled_evidence_valid": all(probe.get("valid") is True for probe in blocked_write_probes.values()),
        "adapter_ready_for_read_only_testnet_probe": not blockers,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "live_trading_allowed_by_this_module": False,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }
    evidence["adapter_evidence_sha256"] = sha256_json(_payload_without_hash(evidence))
    return evidence


def build_real_testnet_read_only_adapter_registry_record(evidence: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(evidence or {})
    record = {
        "version": STEP303_REAL_TESTNET_READ_ONLY_ADAPTER_VERSION,
        "real_testnet_read_only_adapter_evidence_id": data.get("real_testnet_read_only_adapter_evidence_id"),
        "adapter_evidence_sha256": data.get("adapter_evidence_sha256"),
        "venue": data.get("venue"),
        "environment": data.get("environment"),
        "base_url": data.get("base_url"),
        "all_read_probes_valid": data.get("all_read_probes_valid") is True,
        "place_cancel_disabled_evidence_valid": data.get("place_cancel_disabled_evidence_valid") is True,
        "adapter_ready_for_read_only_testnet_probe": data.get("adapter_ready_for_read_only_testnet_probe") is True,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "live_trading_allowed_by_this_module": False,
        "block_reasons": list(data.get("block_reasons") or []),
        "created_at_utc": utc_now_canonical(),
    }
    record["real_testnet_read_only_adapter_registry_record_id"] = stable_id("step303_read_only_adapter_registry", record, 24)
    record["real_testnet_read_only_adapter_registry_record_sha256"] = sha256_json(record)
    return record


def persist_real_testnet_read_only_adapter_evidence(
    cfg: AppConfig,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    latest_dir = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    latest_dir.mkdir(parents=True, exist_ok=True)
    evidence_payload = dict(evidence)
    registry_record = build_real_testnet_read_only_adapter_registry_record(evidence_payload)
    persisted = append_registry_record(
        registry_path(cfg, REAL_TESTNET_READ_ONLY_ADAPTER_REGISTRY_NAME),
        registry_record,
        registry_name=REAL_TESTNET_READ_ONLY_ADAPTER_REGISTRY_NAME,
        id_field="real_testnet_read_only_adapter_registry_record_id",
        hash_field="real_testnet_read_only_adapter_registry_record_sha256",
        id_prefix="step303_read_only_adapter_registry",
    )
    evidence_payload["real_testnet_read_only_adapter_registry_record_id"] = persisted.get(
        "real_testnet_read_only_adapter_registry_record_id"
    )
    evidence_payload["real_testnet_read_only_adapter_registry_record_sha256"] = persisted.get(
        "real_testnet_read_only_adapter_registry_record_sha256"
    )
    atomic_write_json(latest_dir / "real_testnet_read_only_adapter_evidence.json", evidence_payload)
    atomic_write_json(latest_dir / "real_testnet_read_only_adapter_registry_record.json", persisted)
    return evidence_payload


def run_real_testnet_read_only_adapter_latest(
    *,
    project_root: str | Path | None = None,
    adapter_kind: str = "binance_futures_testnet",
    symbol: str = "BTCUSDT",
) -> dict[str, Any]:
    cfg = load_config(project_root)
    adapter = build_read_only_testnet_adapter(adapter_kind)
    order_intent = {
        "order_intent_id": "step303_read_only_probe_order_intent",
        "symbol": symbol,
        "notional_usdt": 5,
        "min_notional_usdt": 1,
        "fee_bps": 2.5,
        "slippage_bps": 3.0,
    }
    evidence = build_real_testnet_read_only_adapter_evidence(adapter=adapter, order_intent=order_intent, symbol=symbol)
    return persist_real_testnet_read_only_adapter_evidence(cfg, evidence)

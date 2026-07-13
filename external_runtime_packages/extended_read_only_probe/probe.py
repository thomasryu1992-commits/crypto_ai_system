from __future__ import annotations

import hashlib
import json
import random
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Iterable, Mapping, Sequence

import requests

P71_PRIVATE_RECEIPT_VERSION = "p71_extended_private_read_only_receipt_v2"
API_BASE_URL = "https://api.starknet.sepolia.extended.exchange/api/v1"
STREAM_BASE_URL = "wss://api.starknet.sepolia.extended.exchange/stream.extended.exchange/v1"
ACCOUNT_STREAM_PATH = "/account"
MARKET = "BTC-USD"
P71_SERVER_PING_INTERVAL_SECONDS = 15
P71_PONG_TIMEOUT_SECONDS = 10
P71_HEARTBEAT_OBSERVATION_SECONDS = 27
P71_MAX_CLOCK_OFFSET_MS = 5_000
P71_EVIDENCE_MAX_AGE_SECONDS = 600
P71_MAX_REST_RETRIES = 3
P71_MAX_STREAM_ATTEMPTS = 3

ALLOWED_GET_PATHS: tuple[tuple[str, str, Mapping[str, Any]], ...] = (
    ("account_info", "/user/account/info", {}),
    ("balance", "/user/balance", {}),
    ("positions", "/user/positions", {"market": MARKET}),
    ("open_orders", "/user/orders", {"market": MARKET}),
)

PrivateGet = Callable[[str, Mapping[str, Any], Mapping[str, str], float], Any]
PrivateStreamProbe = Callable[[str, Mapping[str, str], float], Mapping[str, Any]]
SleepFn = Callable[[float], None]


class PrivateStreamResyncRequired(RuntimeError):
    def __init__(self, reason: str, *, previous_sequence: int | None = None, received_sequence: int | None = None):
        super().__init__(reason)
        self.reason = reason
        self.previous_sequence = previous_sequence
        self.received_sequence = received_sequence


def _epoch_ms() -> int:
    return int(time.time() * 1000)


def _canonical_from_epoch_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_json(value: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_headers(headers: Mapping[str, Any] | None) -> dict[str, str]:
    source = {str(k).lower(): str(v) for k, v in dict(headers or {}).items()}
    return {name: source[name] for name in ("date", "retry-after", "content-type") if name in source}


def _parse_retry_after_seconds(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(text)
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        return max(0.0, (target - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def _requests_get(url: str, params: Mapping[str, Any], headers: Mapping[str, str], timeout: float) -> tuple[int, Mapping[str, Any], Mapping[str, str]]:
    response = requests.get(
        url,
        params=dict(params),
        headers=dict(headers),
        timeout=timeout,
        allow_redirects=False,
    )
    try:
        payload = response.json()
    except requests.exceptions.JSONDecodeError:
        raw_body = response.content or b""
        payload = {
            "status": "NON_JSON_RESPONSE",
            "content_type": response.headers.get("Content-Type", ""),
            "body_length": len(raw_body),
            "body_sha256": hashlib.sha256(raw_body).hexdigest(),
        }
    if not isinstance(payload, Mapping):
        payload = {
            "status": "NON_OBJECT_JSON_RESPONSE",
            "json_type": type(payload).__name__,
            "body_sha256": hashlib.sha256(response.content or b"").hexdigest(),
        }
    return int(response.status_code), dict(payload), _safe_headers(response.headers)


def _normalize_transport_result(result: Any) -> tuple[int, dict[str, Any], dict[str, str]]:
    if isinstance(result, tuple):
        if len(result) == 2:
            status, payload = result
            headers: Mapping[str, Any] = {}
        elif len(result) == 3:
            status, payload, headers = result
        else:
            raise ValueError("P71 private REST transport tuple must have 2 or 3 elements")
        if not isinstance(payload, Mapping):
            raise ValueError("P71 private REST payload must be an object")
        return int(status), dict(payload), _safe_headers(headers if isinstance(headers, Mapping) else {})
    if isinstance(result, Mapping):
        return 200, dict(result), {}
    raise ValueError("P71 private REST transport result must be a mapping or tuple")


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _extract_account_info(data: Any) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        return {"valid": False, "status": None, "account_id": None, "l2_vault": None}
    status = str(data.get("status") or "").upper()
    account_id = data.get("id") if "id" in data else data.get("accountId")
    l2_vault = data.get("l2Vault") if "l2Vault" in data else data.get("l2_vault")
    return {
        "valid": status == "ACTIVE" and _as_int(account_id) is not None,
        "status": status or None,
        "account_id": _as_int(account_id),
        "l2_vault": _as_int(l2_vault),
    }


def _validate_balance_data(data: Any) -> bool:
    if not isinstance(data, Mapping):
        return False
    numeric_alias_groups = (
        ("balance",),
        ("equity",),
        ("availableForTrade", "available_for_trade"),
    )
    return all(any(_as_decimal(data.get(alias)) is not None for alias in aliases) for aliases in numeric_alias_groups)


def _validate_market_list(data: Any) -> tuple[bool, int]:
    if not isinstance(data, list):
        return False, 0
    for item in data:
        if not isinstance(item, Mapping):
            return False, len(data)
        market = str(item.get("market") or "")
        if market and market != MARKET:
            return False, len(data)
    return True, len(data)


def _recursive_forbidden_key_matches(value: Any, path: str = "$") -> list[str]:
    forbidden = {"api_key", "api-secret", "api_secret", "private_key", "stark_private", "x-api-key", "secret_value", "raw_response"}
    matches: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key).lower()
            child_path = f"{path}.{key}"
            if key_text in forbidden:
                matches.append(child_path)
            matches.extend(_recursive_forbidden_key_matches(child, child_path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            matches.extend(_recursive_forbidden_key_matches(child, f"{path}[{index}]"))
    return matches


def _value_contains_secret(value: Any, secret: str) -> bool:
    if isinstance(value, Mapping):
        return any(_value_contains_secret(child, secret) for child in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_value_contains_secret(child, secret) for child in value)
    return isinstance(value, str) and secret in value


def _stream_projection(message: Mapping[str, Any]) -> dict[str, Any]:
    data = message.get("data") if isinstance(message.get("data"), Mapping) else {}
    return {
        "type": str(message.get("type") or "").upper() or None,
        "sequence": _as_int(message.get("seq") if "seq" in message else message.get("sequence")),
        "server_timestamp_ms": _as_int(message.get("ts") if "ts" in message else message.get("timestamp")),
        "data": dict(data),
    }


def _private_snapshot_state(data: Mapping[str, Any]) -> dict[str, Any]:
    positions = data.get("positions")
    orders = data.get("orders")
    balance = data.get("balance")
    positions_valid, position_count = _validate_market_list(positions)
    orders_valid, order_count = _validate_market_list(orders)
    balance_valid = balance is None or _validate_balance_data(balance)
    required_keys_present = all(key in data for key in ("positions", "orders", "balance"))
    return {
        "valid": required_keys_present and positions_valid and orders_valid and balance_valid,
        "required_keys_present": required_keys_present,
        "position_count": position_count,
        "open_order_count": order_count,
        "balance_present": isinstance(balance, Mapping),
        "market_scope_valid": positions_valid and orders_valid,
    }


def _websocket_error_diagnostic(exc: Exception) -> dict[str, Any]:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code is None:
        status_code = getattr(response, "status", None)
    if status_code is None:
        status_code = getattr(exc, "status_code", None)
    if status_code is None:
        match = re.search(r"\bHTTP\s+(\d{3})\b", str(exc), flags=re.IGNORECASE)
        if match:
            status_code = match.group(1)
    return {
        "error_type": exc.__class__.__name__,
        "http_status": _as_int(status_code),
        "error": str(exc)[:500],
    }


def websocket_private_account_snapshot_probe(
    url: str,
    headers: Mapping[str, str],
    timeout_seconds: float,
    *,
    connect_fn: Callable[..., Any] | None = None,
    monotonic_fn: Callable[[], float] = time.monotonic,
    wall_time_fn: Callable[[], float] = time.time,
    sleep_fn: SleepFn = time.sleep,
    observation_seconds: float | None = None,
) -> Mapping[str, Any]:
    if connect_fn is None:
        from websockets.sync.client import connect as connect_fn

    api_key = str(headers.get("X-Api-Key") or "")
    if not api_key:
        raise ValueError("P71 private account stream requires API key inside external process memory")
    required_observation = float(P71_HEARTBEAT_OBSERVATION_SECONDS)
    observation = max(float(observation_seconds or timeout_seconds), required_observation)
    started = monotonic_fn()
    diagnostics: list[dict[str, Any]] = []
    reconnect_reasons: list[str] = []

    for attempt in range(1, P71_MAX_STREAM_ATTEMPTS + 1):
        attempt_started = monotonic_fn()
        messages: list[dict[str, Any]] = []
        last_sequence: int | None = None
        max_abs_clock_offset_ms: int | None = None
        try:
            with connect_fn(
                url,
                additional_headers={"X-Api-Key": api_key},
                user_agent_header=str(headers.get("User-Agent") or "crypto-ai-system-p71-external-read-only/2"),
                open_timeout=min(observation, 15.0),
                close_timeout=2,
            ) as ws:
                deadline = monotonic_fn() + observation
                snapshot_state: dict[str, Any] | None = None
                while monotonic_fn() < deadline:
                    remaining = max(0.1, deadline - monotonic_fn())
                    try:
                        raw = ws.recv(timeout=remaining)
                    except TimeoutError:
                        break
                    received_ms = int(wall_time_fn() * 1000)
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    payload = json.loads(str(raw))
                    if not isinstance(payload, Mapping):
                        raise ValueError("Extended private stream message must be an object")
                    message = dict(payload)
                    projection = _stream_projection(message)
                    sequence = projection["sequence"]
                    if not messages:
                        if projection["type"] != "SNAPSHOT":
                            raise PrivateStreamResyncRequired("INITIAL_MESSAGE_NOT_SNAPSHOT", received_sequence=sequence)
                        if sequence != 1:
                            raise PrivateStreamResyncRequired("INITIAL_SNAPSHOT_SEQUENCE_NOT_ONE", received_sequence=sequence)
                        snapshot_state = _private_snapshot_state(projection["data"])
                        if not snapshot_state["valid"]:
                            raise PrivateStreamResyncRequired("INITIAL_ACCOUNT_SNAPSHOT_SCHEMA_INVALID", received_sequence=sequence)
                    elif sequence is None or last_sequence is None or sequence != last_sequence + 1:
                        raise PrivateStreamResyncRequired("SEQUENCE_GAP", previous_sequence=last_sequence, received_sequence=sequence)
                    last_sequence = sequence
                    server_ts = projection["server_timestamp_ms"]
                    if server_ts is not None:
                        offset = abs(received_ms - server_ts)
                        max_abs_clock_offset_ms = offset if max_abs_clock_offset_ms is None else max(max_abs_clock_offset_ms, offset)
                    messages.append(message)

                duration_ms = round((monotonic_fn() - attempt_started) * 1000, 3)
                if not messages or snapshot_state is None:
                    raise TimeoutError("Extended private stream produced no valid snapshot")
                heartbeat_window_observed = duration_ms >= required_observation * 1000
                if not heartbeat_window_observed:
                    raise RuntimeError("Extended private stream heartbeat observation window was not completed")
                return {
                    "actual_network_read_performed": True,
                    "first_message_sha256": _sha256_json(messages[0]),
                    "last_message_sha256": _sha256_json(messages[-1]),
                    "session_duration_ms": duration_ms,
                    "connection_attempts": attempt,
                    "reconnect_count": attempt - 1,
                    "reconnect_reasons": list(reconnect_reasons),
                    "resync_performed": attempt > 1,
                    "resync_snapshot_received": attempt > 1,
                    "message_count": len(messages),
                    "initial_snapshot_valid": True,
                    "first_sequence": 1,
                    "last_sequence": last_sequence,
                    "sequence_valid": True,
                    "position_count": snapshot_state["position_count"],
                    "open_order_count": snapshot_state["open_order_count"],
                    "balance_present": snapshot_state["balance_present"],
                    "market_scope_valid": snapshot_state["market_scope_valid"],
                    "server_timestamp_present": max_abs_clock_offset_ms is not None,
                    "max_abs_clock_offset_ms": max_abs_clock_offset_ms,
                    "clock_evidence_valid": max_abs_clock_offset_ms is not None and max_abs_clock_offset_ms <= P71_MAX_CLOCK_OFFSET_MS,
                    "heartbeat_policy_valid": True,
                    "server_ping_interval_seconds": P71_SERVER_PING_INTERVAL_SECONDS,
                    "pong_timeout_seconds": P71_PONG_TIMEOUT_SECONDS,
                    "automatic_control_frame_pong_capability": True,
                    "server_ping_observed_directly": False,
                    "client_pong_observed_directly": False,
                    "heartbeat_evidence_mode": "INFERRED_FROM_CONNECTION_SURVIVAL",
                    "heartbeat_observation_required_seconds": required_observation,
                    "heartbeat_window_observed": heartbeat_window_observed,
                    "connection_survived_heartbeat_window": heartbeat_window_observed,
                    "no_secret_scan_passed": True,
                    "attempt_diagnostics": diagnostics,
                }
        except PrivateStreamResyncRequired as exc:
            reconnect_reasons.append(exc.reason)
            diagnostics.append(
                {
                    "attempt": attempt,
                    "error_type": exc.__class__.__name__,
                    "error": exc.reason,
                    "previous_sequence": exc.previous_sequence,
                    "received_sequence": exc.received_sequence,
                    "reconnect_required": True,
                }
            )
            if attempt < P71_MAX_STREAM_ATTEMPTS:
                sleep_fn(float(attempt))
                continue
        except Exception as exc:
            reconnect_reasons.append(exc.__class__.__name__)
            diagnostics.append(
                {
                    "attempt": attempt,
                    **_websocket_error_diagnostic(exc),
                    "reconnect_required": True,
                }
            )
            if attempt < P71_MAX_STREAM_ATTEMPTS:
                sleep_fn(float(attempt))
                continue

    last = diagnostics[-1] if diagnostics else {}
    raise RuntimeError(
        "Extended private account stream unavailable after bounded attempts: "
        f"{last.get('error_type')} status={last.get('http_status')} {last.get('error')}"
    )


@dataclass(frozen=True)
class PrivateReadOnlyProbePolicy:
    credential_reference_id: str
    api_base_url: str = API_BASE_URL
    stream_base_url: str = STREAM_BASE_URL
    market: str = MARKET
    network_enabled: bool = False
    timeout_seconds: float = 30.0
    user_agent: str = "crypto-ai-system-p71-external-read-only/2"
    source_is_fixture: bool = False


class ExtendedPrivateReadOnlyProbe:
    def __init__(
        self,
        *,
        api_key: str,
        policy: PrivateReadOnlyProbePolicy,
        transport: PrivateGet | None = None,
        stream_probe: PrivateStreamProbe | None = None,
        sleep_fn: SleepFn = time.sleep,
        random_fn: Callable[[], float] = random.random,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("P71 external probe requires an API key in process memory")
        if policy.api_base_url != API_BASE_URL or policy.stream_base_url != STREAM_BASE_URL or policy.market != MARKET:
            raise ValueError("P71 external probe is restricted to pinned Extended Sepolia BTC-USD endpoints")
        self._api_key = api_key.strip()
        self.policy = policy
        self.transport = transport or _requests_get
        self.stream_probe = stream_probe or websocket_private_account_snapshot_probe
        self.sleep_fn = sleep_fn
        self.random_fn = random_fn

    def _request_endpoint(self, *, name: str, path: str, params: Mapping[str, Any]) -> tuple[dict[str, Any], Any]:
        attempts: list[dict[str, Any]] = []
        retry_delays: list[float] = []
        status = 0
        payload: dict[str, Any] = {}
        response_headers: dict[str, str] = {}
        started = time.monotonic()
        for attempt in range(1, P71_MAX_REST_RETRIES + 1):
            status, payload, response_headers = _normalize_transport_result(
                self.transport(
                    f"{self.policy.api_base_url}{path}",
                    params,
                    {"User-Agent": self.policy.user_agent, "X-Api-Key": self._api_key},
                    self.policy.timeout_seconds,
                )
            )
            attempts.append({"attempt": attempt, "http_status": status, "retry_after_present": "retry-after" in response_headers})
            if status != 429 or attempt >= P71_MAX_REST_RETRIES:
                break
            retry_after = _parse_retry_after_seconds(response_headers.get("retry-after"))
            base = retry_after if retry_after is not None else float(2 ** (attempt - 1))
            delay = min(10.0, base + 0.25 * self.random_fn())
            retry_delays.append(round(delay, 3))
            self.sleep_fn(delay)

        data = payload.get("data") if isinstance(payload, Mapping) else None
        redirect_blocked = 300 <= status < 400
        response_status = str(payload.get("status") or "")
        schema_valid = False
        count: int | None = None
        account_status: str | None = None
        account_id: int | None = None
        l2_vault: int | None = None
        if name == "account_info" and status == 200 and response_status == "OK":
            account = _extract_account_info(data)
            schema_valid = account["valid"]
            account_status = account["status"]
            account_id = account["account_id"]
            l2_vault = account["l2_vault"]
        elif name == "balance" and status == 200 and response_status == "OK":
            schema_valid = _validate_balance_data(data)
        elif name in {"positions", "open_orders"} and status == 200 and response_status == "OK":
            schema_valid, count = _validate_market_list(data)

        receipt = {
            "http_method": "GET",
            "path": path,
            "http_status": status,
            "response_status": response_status or None,
            "redirect_blocked": redirect_blocked,
            "schema_valid": schema_valid,
            "data_present": data is not None,
            "item_count": count,
            "account_status": account_status,
            "account_id": account_id,
            "l2_vault": l2_vault,
            "zero_balance_confirmed": False,
            "zero_balance_basis": None,
            "rate_limit_policy_valid": status != 429 and not redirect_blocked and len(attempts) <= P71_MAX_REST_RETRIES,
            "rate_limit_evidence": {
                "policy_applied": True,
                "attempt_count": len(attempts),
                "retry_count": max(0, len(attempts) - 1),
                "http_429_count": sum(1 for item in attempts if item["http_status"] == 429),
                "retry_after_seen": any(item["retry_after_present"] for item in attempts),
                "retry_delays_seconds": retry_delays,
                "max_attempts": P71_MAX_REST_RETRIES,
                "exhausted": status == 429,
            },
            "response_sha256": _sha256_json(payload),
            "received_at_utc": _canonical_from_epoch_ms(_epoch_ms()),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        }
        return receipt, data

    def run(self) -> dict[str, Any]:
        if not self.policy.network_enabled:
            return self._blocked_receipt("P71_PRIVATE_NETWORK_DISABLED")

        started_ms = _epoch_ms()
        read_session_id = f"p71_private_read_session_{uuid.uuid4().hex}"
        endpoint_receipts: dict[str, Any] = {}
        rest_state: dict[str, Any] = {}

        account_receipt, account_data = self._request_endpoint(name="account_info", path="/user/account/info", params={})
        endpoint_receipts["account_info"] = account_receipt
        rest_state["account_info"] = account_data
        account_auth_valid = account_receipt["schema_valid"] is True and account_receipt["http_status"] == 200

        for name, path, params in ALLOWED_GET_PATHS[1:]:
            item, data = self._request_endpoint(name=name, path=path, params=params)
            if name == "balance" and item["http_status"] == 404 and account_auth_valid and item["redirect_blocked"] is False:
                item["zero_balance_confirmed"] = True
                item["zero_balance_basis"] = "DOCUMENTED_BALANCE_404_AFTER_ACTIVE_ACCOUNT_AUTH"
                item["schema_valid"] = True
            endpoint_receipts[name] = item
            rest_state[name] = data

        stream_receipt = dict(
            self.stream_probe(
                f"{self.policy.stream_base_url}{ACCOUNT_STREAM_PATH}",
                {"User-Agent": self.policy.user_agent, "X-Api-Key": self._api_key},
                self.policy.timeout_seconds,
            )
        )

        rest_position_count = int(endpoint_receipts["positions"].get("item_count") or 0)
        rest_order_count = int(endpoint_receipts["open_orders"].get("item_count") or 0)
        rest_balance_present = endpoint_receipts["balance"].get("http_status") == 200
        rest_ws_consistency = {
            "position_count_match": stream_receipt.get("position_count") == rest_position_count,
            "open_order_count_match": stream_receipt.get("open_order_count") == rest_order_count,
            "balance_presence_match": stream_receipt.get("balance_present") is rest_balance_present,
            "rest_position_count": rest_position_count,
            "stream_position_count": stream_receipt.get("position_count"),
            "rest_open_order_count": rest_order_count,
            "stream_open_order_count": stream_receipt.get("open_order_count"),
            "rest_balance_present": rest_balance_present,
            "stream_balance_present": stream_receipt.get("balance_present"),
        }
        rest_ws_consistency_valid = all(
            rest_ws_consistency[key]
            for key in ("position_count_match", "open_order_count_match", "balance_presence_match")
        )

        completed_ms = _epoch_ms()
        api_fingerprint = hashlib.sha256(self._api_key.encode("utf-8")).hexdigest()
        receipt: dict[str, Any] = {
            "version": P71_PRIVATE_RECEIPT_VERSION,
            "venue": "extended_starknet_sepolia",
            "environment": "testnet",
            "market": MARKET,
            "read_session_id": read_session_id,
            "created_at_utc": _canonical_from_epoch_ms(completed_ms),
            "expires_at_utc": _canonical_from_epoch_ms(completed_ms + P71_EVIDENCE_MAX_AGE_SECONDS * 1000),
            "evidence_max_age_seconds": P71_EVIDENCE_MAX_AGE_SECONDS,
            "credential_reference_id": self.policy.credential_reference_id,
            "api_key_fingerprint_sha256": api_fingerprint,
            "account_id": endpoint_receipts["account_info"].get("account_id"),
            "account_status": endpoint_receipts["account_info"].get("account_status"),
            "l2_vault": endpoint_receipts["account_info"].get("l2_vault"),
            "endpoint_receipts": endpoint_receipts,
            "account_stream_receipt": stream_receipt,
            "rest_ws_consistency": rest_ws_consistency,
            "rest_ws_consistency_valid": rest_ws_consistency_valid,
            "actual_network_read_performed": all(item.get("schema_valid") is True for item in endpoint_receipts.values()) and stream_receipt.get("actual_network_read_performed") is True,
            "source_is_fixture": self.policy.source_is_fixture,
            "all_requests_get": True,
            "write_call_performed": False,
            "order_endpoint_called": False,
            "cancel_endpoint_called": False,
            "signature_created": False,
            "stark_private_key_accessed": False,
            "credential_value_included": False,
            "elapsed_ms": max(0, completed_ms - started_ms),
        }
        key_matches = _recursive_forbidden_key_matches(receipt)
        value_secret_match = _value_contains_secret(receipt, self._api_key)
        receipt["no_secret_scan_passed"] = not key_matches and not value_secret_match
        receipt["no_secret_scan_matches"] = key_matches + (["EXACT_CREDENTIAL_VALUE_MATCH"] if value_secret_match else [])
        receipt["receipt_sha256"] = _sha256_json(receipt)
        return receipt

    def _blocked_receipt(self, reason: str) -> dict[str, Any]:
        now_ms = _epoch_ms()
        receipt: dict[str, Any] = {
            "version": P71_PRIVATE_RECEIPT_VERSION,
            "venue": "extended_starknet_sepolia",
            "environment": "testnet",
            "market": MARKET,
            "read_session_id": f"p71_private_read_session_{uuid.uuid4().hex}",
            "created_at_utc": _canonical_from_epoch_ms(now_ms),
            "expires_at_utc": _canonical_from_epoch_ms(now_ms + P71_EVIDENCE_MAX_AGE_SECONDS * 1000),
            "evidence_max_age_seconds": P71_EVIDENCE_MAX_AGE_SECONDS,
            "credential_reference_id": self.policy.credential_reference_id,
            "api_key_fingerprint_sha256": hashlib.sha256(self._api_key.encode("utf-8")).hexdigest(),
            "endpoint_receipts": {},
            "account_stream_receipt": {},
            "rest_ws_consistency_valid": False,
            "actual_network_read_performed": False,
            "source_is_fixture": self.policy.source_is_fixture,
            "all_requests_get": True,
            "write_call_performed": False,
            "order_endpoint_called": False,
            "cancel_endpoint_called": False,
            "signature_created": False,
            "stark_private_key_accessed": False,
            "credential_value_included": False,
            "no_secret_scan_passed": True,
            "no_secret_scan_matches": [],
            "block_reasons": [reason],
        }
        receipt["receipt_sha256"] = _sha256_json(receipt)
        return receipt


__all__ = [
    "P71_PRIVATE_RECEIPT_VERSION",
    "API_BASE_URL",
    "STREAM_BASE_URL",
    "ACCOUNT_STREAM_PATH",
    "MARKET",
    "P71_HEARTBEAT_OBSERVATION_SECONDS",
    "PrivateReadOnlyProbePolicy",
    "ExtendedPrivateReadOnlyProbe",
    "websocket_private_account_snapshot_probe",
    "_requests_get",
]

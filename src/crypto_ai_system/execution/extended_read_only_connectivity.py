from __future__ import annotations

import json
import random
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

import requests

from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P71_VERSION = "p71_extended_testnet_read_only_connectivity_v3"
P71_PRIVATE_RECEIPT_VERSION = "p71_extended_private_read_only_receipt_v2"
EXTENDED_TESTNET_API_BASE_URL = "https://api.starknet.sepolia.extended.exchange/api/v1"
EXTENDED_TESTNET_STREAM_BASE_URL = "wss://api.starknet.sepolia.extended.exchange/stream.extended.exchange/v1"
EXTENDED_TESTNET_MARKET = "BTC-USD"
PUBLIC_MARKET_PATH = "/info/markets"
PUBLIC_ORDERBOOK_PATH = "/info/markets/BTC-USD/orderbook"
PUBLIC_ORDERBOOK_STREAM_PATH = "/orderbooks/BTC-USD?depth=1"
P71_SDK_USER_AGENT = "X10PythonTradingClient/2.4.0"
P71_SERVER_PING_INTERVAL_SECONDS = 15
P71_PONG_TIMEOUT_SECONDS = 10
P71_HEARTBEAT_OBSERVATION_SECONDS = 27
P71_MAX_CLOCK_OFFSET_MS = 5_000
P71_MARKET_RULE_MAX_AGE_MS = 60_000
P71_ORDERBOOK_MAX_AGE_MS = 5_000
P71_EVIDENCE_MAX_AGE_SECONDS = 600
P71_MAX_REST_RETRIES = 3
P71_MAX_STREAM_ATTEMPTS = 3
P71_MAX_ORDERBOOK_MID_DIVERGENCE_BPS = Decimal("200")

RestGet = Callable[[str, Mapping[str, Any], Mapping[str, str], float], Any]
SleepFn = Callable[[float], None]


class PublicStreamProbe(Protocol):
    def __call__(self, url: str, headers: Mapping[str, str], timeout_seconds: float) -> Mapping[str, Any]: ...


class ExtendedReadOnlyPolicyError(RuntimeError):
    pass


class ExtendedStreamResyncRequired(RuntimeError):
    def __init__(self, reason: str, *, previous_sequence: int | None = None, received_sequence: int | None = None):
        super().__init__(reason)
        self.reason = reason
        self.previous_sequence = previous_sequence
        self.received_sequence = received_sequence


def _epoch_ms() -> int:
    return int(time.time() * 1000)


def _canonical_from_epoch_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_canonical_utc_ms(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return int(parsed.timestamp() * 1000)


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text.lower())


def _hash_without_field(payload: Mapping[str, Any], field: str) -> str:
    data = dict(payload)
    data.pop(field, None)
    return sha256_json(data)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
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


def _safe_headers(headers: Mapping[str, Any] | None) -> dict[str, str]:
    source = {str(k).lower(): str(v) for k, v in dict(headers or {}).items()}
    allowed = ("date", "retry-after", "content-type")
    return {name: source[name] for name in allowed if name in source}


def _parse_retry_after_seconds(value: Any, *, now: datetime | None = None) -> float | None:
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
        current = now or datetime.now(timezone.utc)
        return max(0.0, (target - current).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def _sanitize_response_payload(response: requests.Response) -> Mapping[str, Any]:
    try:
        payload = response.json()
    except requests.exceptions.JSONDecodeError:
        raw_body = response.content or b""
        return {
            "status": "NON_JSON_RESPONSE",
            "content_type": response.headers.get("Content-Type", ""),
            "body_length": len(raw_body),
            "body_sha256": __import__("hashlib").sha256(raw_body).hexdigest(),
        }
    if isinstance(payload, Mapping):
        return dict(payload)
    raw_body = response.content or b""
    return {
        "status": "NON_OBJECT_JSON_RESPONSE",
        "json_type": type(payload).__name__,
        "body_sha256": __import__("hashlib").sha256(raw_body).hexdigest(),
    }


def _requests_get(url: str, params: Mapping[str, Any], headers: Mapping[str, str], timeout: float) -> tuple[int, Mapping[str, Any], Mapping[str, str]]:
    response = requests.get(
        url,
        params=dict(params),
        headers=dict(headers),
        timeout=timeout,
        allow_redirects=False,
    )
    return int(response.status_code), _sanitize_response_payload(response), _safe_headers(response.headers)


def _normalize_rest_result(result: Any) -> tuple[int, dict[str, Any], dict[str, str]]:
    if isinstance(result, tuple):
        if len(result) == 2:
            status, payload = result
            headers: Mapping[str, Any] = {}
        elif len(result) == 3:
            status, payload, headers = result
        else:
            raise ValueError("P71 REST transport tuple must have 2 or 3 elements")
        if not isinstance(payload, Mapping):
            raise ValueError("P71 REST response payload must be an object")
        return int(status), dict(payload), _safe_headers(headers if isinstance(headers, Mapping) else {})
    if isinstance(result, Mapping):
        if result.get("_p71_transport_envelope") is True:
            payload = result.get("payload") or {}
            if not isinstance(payload, Mapping):
                raise ValueError("P71 REST envelope payload must be an object")
            return int(result.get("http_status") or 0), dict(payload), _safe_headers(result.get("headers") or {})
        return 200, dict(result), {}
    raise ValueError("P71 REST transport result must be a mapping or tuple")


def _rest_call_with_policy(
    *,
    transport: RestGet,
    url: str,
    params: Mapping[str, Any],
    headers: Mapping[str, str],
    timeout: float,
    sleep_fn: SleepFn = time.sleep,
    random_fn: Callable[[], float] = random.random,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    retry_delays: list[float] = []
    last_status = 0
    last_payload: dict[str, Any] = {}
    last_headers: dict[str, str] = {}
    started = time.monotonic()
    request_started_ms = _epoch_ms()

    for attempt in range(1, P71_MAX_REST_RETRIES + 1):
        status, payload, response_headers = _normalize_rest_result(transport(url, params, headers, timeout))
        received_ms = _epoch_ms()
        last_status, last_payload, last_headers = status, payload, response_headers
        attempt_record = {
            "attempt": attempt,
            "http_status": status,
            "received_at_utc": _canonical_from_epoch_ms(received_ms),
            "retry_after_present": "retry-after" in response_headers,
        }
        attempts.append(attempt_record)
        if status != 429:
            break
        if attempt >= P71_MAX_REST_RETRIES:
            break
        retry_after = _parse_retry_after_seconds(response_headers.get("retry-after"))
        base_delay = retry_after if retry_after is not None else float(2 ** (attempt - 1))
        delay = min(10.0, base_delay + (0.25 * random_fn()))
        retry_delays.append(round(delay, 3))
        sleep_fn(delay)

    received_ms = _epoch_ms()
    redirect_blocked = 300 <= last_status < 400
    return {
        "called": True,
        "blocked": redirect_blocked or last_status == 429 or not (200 <= last_status < 300),
        "http_status": last_status,
        "payload": last_payload,
        "response_headers": last_headers,
        "request_started_at_utc": _canonical_from_epoch_ms(request_started_ms),
        "received_at_utc": _canonical_from_epoch_ms(received_ms),
        "received_at_epoch_ms": received_ms,
        "latency_ms": round((time.monotonic() - started) * 1000, 3),
        "redirect_blocked": redirect_blocked,
        "rate_limit_evidence": {
            "policy_applied": True,
            "attempt_count": len(attempts),
            "retry_count": max(0, len(attempts) - 1),
            "http_429_count": sum(1 for item in attempts if item["http_status"] == 429),
            "retry_after_seen": any(item["retry_after_present"] for item in attempts),
            "retry_delays_seconds": retry_delays,
            "max_attempts": P71_MAX_REST_RETRIES,
            "exhausted": last_status == 429,
        },
    }


def _stream_message_projection(message: Mapping[str, Any]) -> dict[str, Any]:
    data = message.get("data")
    data_map = data if isinstance(data, Mapping) else {}
    return {
        "type": str(message.get("type") or "").upper() or None,
        "market": str(data_map.get("market") or data_map.get("m") or message.get("market") or "") or None,
        "sequence": _as_int(message.get("seq") if "seq" in message else message.get("sequence")),
        "server_timestamp_ms": _as_int(message.get("ts") if "ts" in message else message.get("timestamp")),
        "data": dict(data_map),
    }


def _websocket_error_diagnostic(exc: Exception) -> dict[str, Any]:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code is None:
        status_code = getattr(exc, "status_code", None)
    return {
        "error_type": exc.__class__.__name__,
        "http_status": _as_int(status_code),
        "error": str(exc)[:500],
    }


def _extract_levels(payload: Mapping[str, Any], side: str) -> list[tuple[Decimal, Decimal]]:
    aliases = ("bids", "bid", "b") if side == "bid" else ("asks", "ask", "a")
    raw: Any = None
    for alias in aliases:
        if alias in payload:
            raw = payload.get(alias)
            break
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        return []
    levels: list[tuple[Decimal, Decimal]] = []
    for item in raw:
        price: Decimal | None = None
        qty: Decimal | None = None
        if isinstance(item, Mapping):
            price = _as_decimal(item.get("price") if "price" in item else item.get("p"))
            qty = _as_decimal(item.get("qty") if "qty" in item else item.get("q"))
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)) and len(item) >= 2:
            price = _as_decimal(item[0])
            qty = _as_decimal(item[1])
        if price is not None and qty is not None and price > 0 and qty >= 0:
            levels.append((price, qty))
    return levels


def _orderbook_mid(payload: Mapping[str, Any]) -> Decimal | None:
    bids = _extract_levels(payload, "bid")
    asks = _extract_levels(payload, "ask")
    if not bids or not asks:
        return None
    best_bid = max(price for price, _ in bids)
    best_ask = min(price for price, _ in asks)
    if best_ask < best_bid:
        return None
    return (best_bid + best_ask) / Decimal("2")


def _orderbook_consistency(rest_orderbook: Mapping[str, Any], stream_message: Mapping[str, Any]) -> dict[str, Any]:
    stream_data = stream_message.get("data") if isinstance(stream_message.get("data"), Mapping) else stream_message
    rest_mid = _orderbook_mid(rest_orderbook)
    stream_mid = _orderbook_mid(stream_data if isinstance(stream_data, Mapping) else {})
    market = str((stream_data or {}).get("market") or (stream_data or {}).get("m") or stream_message.get("market") or "")
    divergence_bps: Decimal | None = None
    if rest_mid is not None and stream_mid is not None and rest_mid > 0:
        divergence_bps = abs(stream_mid - rest_mid) / rest_mid * Decimal("10000")
    valid = (
        market == EXTENDED_TESTNET_MARKET
        and rest_mid is not None
        and stream_mid is not None
        and divergence_bps is not None
        and divergence_bps <= P71_MAX_ORDERBOOK_MID_DIVERGENCE_BPS
    )
    return {
        "valid": valid,
        "rest_mid": str(rest_mid) if rest_mid is not None else None,
        "stream_mid": str(stream_mid) if stream_mid is not None else None,
        "mid_divergence_bps": str(divergence_bps.quantize(Decimal("0.001"))) if divergence_bps is not None else None,
        "max_mid_divergence_bps": str(P71_MAX_ORDERBOOK_MID_DIVERGENCE_BPS),
        "market_match": market == EXTENDED_TESTNET_MARKET,
    }


def websocket_public_snapshot_probe(
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
    """Run a bounded Extended public orderbook session with fail-closed resync.

    ``websockets`` handles control-frame pongs automatically, but its sync API
    doesn't expose server ping / client pong counters. Therefore heartbeat proof
    is explicitly labelled as *inferred from continuous connection survival*
    across the documented 15s ping + 10s pong deadline plus a 2s margin. It is
    never represented as direct control-frame telemetry.
    """

    if connect_fn is None:
        from websockets.sync.client import connect as connect_fn

    required_observation = float(P71_HEARTBEAT_OBSERVATION_SECONDS)
    observation = max(float(observation_seconds or timeout_seconds), required_observation)
    started = monotonic_fn()
    attempt_diagnostics: list[dict[str, Any]] = []
    reconnect_reasons: list[str] = []

    for attempt in range(1, P71_MAX_STREAM_ATTEMPTS + 1):
        attempt_started = monotonic_fn()
        messages: list[dict[str, Any]] = []
        first_sequence: int | None = None
        last_sequence: int | None = None
        max_abs_clock_offset_ms: int | None = None
        try:
            with connect_fn(
                url,
                user_agent_header=str(headers.get("User-Agent") or P71_SDK_USER_AGENT),
                open_timeout=min(observation, 15.0),
                ping_interval=P71_SERVER_PING_INTERVAL_SECONDS,
                ping_timeout=P71_PONG_TIMEOUT_SECONDS,
                close_timeout=2,
            ) as ws:
                deadline = monotonic_fn() + observation
                while monotonic_fn() < deadline:
                    remaining = max(0.1, deadline - monotonic_fn())
                    try:
                        raw = ws.recv(timeout=remaining)
                    except TimeoutError:
                        break
                    client_received_at_ms = int(wall_time_fn() * 1000)
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    payload = json.loads(str(raw))
                    if not isinstance(payload, Mapping):
                        raise ValueError("Extended stream message must be an object")
                    message = dict(payload)
                    projection = _stream_message_projection(message)
                    message_type = projection["type"]
                    market = projection["market"]
                    sequence = projection["sequence"]
                    server_ts = projection["server_timestamp_ms"]

                    if not messages:
                        if message_type != "SNAPSHOT":
                            raise ExtendedStreamResyncRequired("INITIAL_MESSAGE_NOT_SNAPSHOT", received_sequence=sequence)
                        if sequence != 1:
                            raise ExtendedStreamResyncRequired("INITIAL_SNAPSHOT_SEQUENCE_NOT_ONE", received_sequence=sequence)
                        if market != EXTENDED_TESTNET_MARKET:
                            raise ExtendedStreamResyncRequired("INITIAL_SNAPSHOT_MARKET_MISMATCH", received_sequence=sequence)
                        first_sequence = sequence
                    elif sequence is None or last_sequence is None or sequence != last_sequence + 1:
                        raise ExtendedStreamResyncRequired(
                            "SEQUENCE_GAP",
                            previous_sequence=last_sequence,
                            received_sequence=sequence,
                        )
                    if market and market != EXTENDED_TESTNET_MARKET:
                        raise ExtendedStreamResyncRequired(
                            "STREAM_MARKET_MISMATCH",
                            previous_sequence=last_sequence,
                            received_sequence=sequence,
                        )
                    last_sequence = sequence
                    if server_ts is not None:
                        offset = abs(client_received_at_ms - server_ts)
                        max_abs_clock_offset_ms = offset if max_abs_clock_offset_ms is None else max(max_abs_clock_offset_ms, offset)
                    messages.append(message)

                duration_ms = round((monotonic_fn() - attempt_started) * 1000, 3)
                if not messages:
                    raise TimeoutError("Extended stream produced no message in the bounded observation window")
                heartbeat_window_observed = duration_ms >= required_observation * 1000
                if not heartbeat_window_observed:
                    raise RuntimeError("Extended stream heartbeat observation window was not completed")
                first_message = messages[0]
                last_message = messages[-1]
                return {
                    "message": first_message,
                    "first_message_sha256": sha256_json(first_message),
                    "last_message_sha256": sha256_json(last_message),
                    "latency_ms": round((monotonic_fn() - started) * 1000, 3),
                    "session_duration_ms": duration_ms,
                    "received": True,
                    "connection_attempts": attempt,
                    "reconnect_count": attempt - 1,
                    "reconnect_reasons": list(reconnect_reasons),
                    "resync_performed": attempt > 1,
                    "resync_snapshot_received": attempt > 1,
                    "message_count": len(messages),
                    "initial_snapshot_valid": True,
                    "snapshot_received": True,
                    "first_sequence": first_sequence,
                    "last_sequence": last_sequence,
                    "sequence_valid": True,
                    "sequence_gap_count": sum(1 for reason in reconnect_reasons if reason == "SEQUENCE_GAP"),
                    "stream_market_valid": True,
                    "server_timestamp_present": max_abs_clock_offset_ms is not None,
                    "max_abs_clock_offset_ms": max_abs_clock_offset_ms,
                    "clock_offset_within_limit": max_abs_clock_offset_ms is not None and max_abs_clock_offset_ms <= P71_MAX_CLOCK_OFFSET_MS,
                    "heartbeat_policy_configured": True,
                    "server_ping_interval_seconds": P71_SERVER_PING_INTERVAL_SECONDS,
                    "pong_timeout_seconds": P71_PONG_TIMEOUT_SECONDS,
                    "automatic_control_frame_pong_capability": True,
                    "server_ping_observed_directly": False,
                    "client_pong_observed_directly": False,
                    "heartbeat_evidence_mode": "INFERRED_FROM_CONNECTION_SURVIVAL",
                    "heartbeat_observation_required_seconds": required_observation,
                    "heartbeat_window_observed": heartbeat_window_observed,
                    "connection_survived_heartbeat_window": heartbeat_window_observed,
                    "attempt_diagnostics": attempt_diagnostics,
                }
        except ExtendedStreamResyncRequired as exc:
            reconnect_reasons.append(exc.reason)
            attempt_diagnostics.append(
                {
                    "attempt": attempt,
                    "elapsed_ms": round((monotonic_fn() - attempt_started) * 1000, 3),
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
            attempt_diagnostics.append(
                {
                    "attempt": attempt,
                    "elapsed_ms": round((monotonic_fn() - attempt_started) * 1000, 3),
                    **_websocket_error_diagnostic(exc),
                    "reconnect_required": True,
                }
            )
            reconnect_reasons.append(exc.__class__.__name__)
            if attempt < P71_MAX_STREAM_ATTEMPTS:
                sleep_fn(float(attempt))
                continue

    last = attempt_diagnostics[-1] if attempt_diagnostics else {}
    raise RuntimeError(
        "Extended public stream unavailable after bounded attempts: "
        f"{last.get('error_type', 'unknown')} status={last.get('http_status')} {last.get('error', '')}"
    )


@dataclass(frozen=True)
class ExtendedPublicReadOnlyPolicy:
    api_base_url: str = EXTENDED_TESTNET_API_BASE_URL
    stream_base_url: str = EXTENDED_TESTNET_STREAM_BASE_URL
    market: str = EXTENDED_TESTNET_MARKET
    network_enabled: bool = False
    write_calls_allowed: bool = False
    credential_headers_allowed: bool = False
    timeout_seconds: float = 30.0
    user_agent: str = P71_SDK_USER_AGENT


class ExtendedPublicReadOnlyClient:
    def __init__(
        self,
        policy: ExtendedPublicReadOnlyPolicy,
        *,
        rest_get: RestGet | None = None,
        stream_probe: PublicStreamProbe | None = None,
        sleep_fn: SleepFn = time.sleep,
        random_fn: Callable[[], float] = random.random,
    ) -> None:
        self.policy = policy
        self.rest_get = rest_get or _requests_get
        self.stream_probe = stream_probe or websocket_public_snapshot_probe
        self.sleep_fn = sleep_fn
        self.random_fn = random_fn
        if policy.api_base_url != EXTENDED_TESTNET_API_BASE_URL:
            raise ExtendedReadOnlyPolicyError("P71 API base URL must be the pinned Extended Starknet Sepolia endpoint")
        if policy.stream_base_url != EXTENDED_TESTNET_STREAM_BASE_URL:
            raise ExtendedReadOnlyPolicyError("P71 stream URL must be the pinned official-SDK Starknet Sepolia WSS endpoint")
        if policy.market != EXTENDED_TESTNET_MARKET:
            raise ExtendedReadOnlyPolicyError("P71 market must be BTC-USD")
        if policy.write_calls_allowed:
            raise ExtendedReadOnlyPolicyError("P71 write calls must remain disabled")
        if policy.credential_headers_allowed:
            raise ExtendedReadOnlyPolicyError("P71 public client must not accept credential headers")

    @property
    def headers(self) -> dict[str, str]:
        return {"User-Agent": self.policy.user_agent}

    def _get(self, path: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if not self.policy.network_enabled:
            return {"called": False, "blocked": True, "reason": "P71_NETWORK_DISABLED", "path": path, "params": dict(params or {})}
        if not path.startswith("/info/"):
            raise ExtendedReadOnlyPolicyError("P71 public REST allowlist permits only /info/* GET paths")
        result = _rest_call_with_policy(
            transport=self.rest_get,
            url=f"{self.policy.api_base_url}{path}",
            params=dict(params or {}),
            headers=self.headers,
            timeout=self.policy.timeout_seconds,
            sleep_fn=self.sleep_fn,
            random_fn=self.random_fn,
        )
        return {"method": "GET", "path": path, **result}

    def get_market(self) -> dict[str, Any]:
        return self._get(PUBLIC_MARKET_PATH, {"market": self.policy.market})

    def get_orderbook(self) -> dict[str, Any]:
        return self._get(PUBLIC_ORDERBOOK_PATH)

    def get_orderbook_stream_snapshot(self) -> dict[str, Any]:
        path = PUBLIC_ORDERBOOK_STREAM_PATH
        if not self.policy.network_enabled:
            return {"called": False, "blocked": True, "reason": "P71_NETWORK_DISABLED", "path": path}
        try:
            result = dict(self.stream_probe(f"{self.policy.stream_base_url}{path}", self.headers, self.policy.timeout_seconds))
            return {"called": True, "blocked": False, "path": path, **result}
        except Exception as exc:
            return {"called": True, "blocked": True, "received": False, "path": path, **_websocket_error_diagnostic(exc)}

    def post(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"called": False, "blocked": True, "reason": "P71_WRITE_CALL_BLOCKED", "http_method": "POST"}

    def patch(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"called": False, "blocked": True, "reason": "P71_WRITE_CALL_BLOCKED", "http_method": "PATCH"}

    def delete(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"called": False, "blocked": True, "reason": "P71_WRITE_CALL_BLOCKED", "http_method": "DELETE"}


def _unwrap_data(response: Mapping[str, Any]) -> Any:
    payload = response.get("payload") or {}
    if isinstance(payload, Mapping) and "data" in payload:
        return payload.get("data")
    return payload


def _first_market(data: Any) -> Mapping[str, Any]:
    if isinstance(data, list):
        for item in data:
            if isinstance(item, Mapping) and str(item.get("name") or item.get("market") or "") == EXTENDED_TESTNET_MARKET:
                return item
        return data[0] if data and isinstance(data[0], Mapping) else {}
    return data if isinstance(data, Mapping) else {}


def _response_age_ms(response: Mapping[str, Any], observed_epoch_ms: int) -> int | None:
    received = _as_int(response.get("received_at_epoch_ms"))
    if received is None:
        return None
    return max(0, observed_epoch_ms - received)


def _rate_limit_evidence_valid(response: Mapping[str, Any]) -> bool:
    evidence = response.get("rate_limit_evidence")
    if not isinstance(evidence, Mapping):
        return False
    return (
        evidence.get("policy_applied") is True
        and _as_int(evidence.get("attempt_count")) is not None
        and 1 <= int(evidence.get("attempt_count")) <= P71_MAX_REST_RETRIES
        and evidence.get("exhausted") is False
        and response.get("http_status") != 429
    )


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


def build_p71_public_connectivity_evidence(
    *,
    market_response: Mapping[str, Any],
    orderbook_response: Mapping[str, Any],
    stream_response: Mapping[str, Any],
    write_block_probe: Mapping[str, Any] | None = None,
    observed_at_utc: str | None = None,
    observed_at_epoch_ms: int | None = None,
) -> dict[str, Any]:
    observed_ms = observed_at_epoch_ms if observed_at_epoch_ms is not None else _epoch_ms()
    observed_at = observed_at_utc or _canonical_from_epoch_ms(observed_ms)
    expires_at = _canonical_from_epoch_ms(observed_ms + P71_EVIDENCE_MAX_AGE_SECONDS * 1000)
    blockers: list[str] = []
    market = _first_market(_unwrap_data(market_response))
    orderbook = _unwrap_data(orderbook_response)
    stream_message = stream_response.get("message")
    stream_message_map = dict(stream_message) if isinstance(stream_message, Mapping) else {}
    market_name = str(market.get("name") or market.get("market") or "")
    market_status = str(market.get("status") or "").upper()
    trading_config = market.get("tradingConfig") or market.get("trading_config")

    market_age_ms = _response_age_ms(market_response, observed_ms)
    orderbook_age_ms = _response_age_ms(orderbook_response, observed_ms)
    market_rules_fresh = market_age_ms is not None and market_age_ms <= P71_MARKET_RULE_MAX_AGE_MS
    orderbook_fresh = orderbook_age_ms is not None and orderbook_age_ms <= P71_ORDERBOOK_MAX_AGE_MS
    market_rate_limit_valid = _rate_limit_evidence_valid(market_response)
    orderbook_rate_limit_valid = _rate_limit_evidence_valid(orderbook_response)

    if market_response.get("called") is not True:
        blockers.append("P71_MARKET_REST_NOT_CALLED")
    if market_response.get("blocked") is True or market_response.get("http_status") != 200:
        blockers.append("P71_MARKET_REST_INVALID")
    if market_response.get("redirect_blocked") is True:
        blockers.append("P71_MARKET_REST_REDIRECT_BLOCKED")
    if market_name != EXTENDED_TESTNET_MARKET:
        blockers.append("P71_BTC_USD_MARKET_NOT_CONFIRMED")
    if market_status not in {"ACTIVE", "TRADING"}:
        blockers.append("P71_MARKET_NOT_ACTIVE")
    if not isinstance(trading_config, Mapping) or not trading_config:
        blockers.append("P71_TRADING_RULES_MISSING")
    if not market_rules_fresh:
        blockers.append("P71_MARKET_RULES_STALE_OR_UNTIMED")
    if not market_rate_limit_valid:
        blockers.append("P71_MARKET_RATE_LIMIT_POLICY_INVALID")

    if orderbook_response.get("called") is not True:
        blockers.append("P71_ORDERBOOK_REST_NOT_CALLED")
    if orderbook_response.get("blocked") is True or orderbook_response.get("http_status") != 200:
        blockers.append("P71_ORDERBOOK_REST_INVALID")
    if orderbook_response.get("redirect_blocked") is True:
        blockers.append("P71_ORDERBOOK_REST_REDIRECT_BLOCKED")
    if not isinstance(orderbook, Mapping) or not _extract_levels(orderbook, "bid") or not _extract_levels(orderbook, "ask"):
        blockers.append("P71_ORDERBOOK_LEVELS_MISSING")
    if not orderbook_fresh:
        blockers.append("P71_ORDERBOOK_STALE_OR_UNTIMED")
    if not orderbook_rate_limit_valid:
        blockers.append("P71_ORDERBOOK_RATE_LIMIT_POLICY_INVALID")

    stream_called = stream_response.get("called") is True
    stream_received = stream_response.get("received") is True and isinstance(stream_message, Mapping)
    initial_snapshot_valid = stream_response.get("initial_snapshot_valid") is True
    sequence_valid = stream_response.get("sequence_valid") is True
    stream_market_valid = stream_response.get("stream_market_valid") is True
    heartbeat_policy_valid = (
        stream_response.get("heartbeat_policy_configured") is True
        and stream_response.get("server_ping_interval_seconds") == P71_SERVER_PING_INTERVAL_SECONDS
        and stream_response.get("pong_timeout_seconds") == P71_PONG_TIMEOUT_SECONDS
        and stream_response.get("automatic_control_frame_pong_capability") is True
        and stream_response.get("heartbeat_evidence_mode") == "INFERRED_FROM_CONNECTION_SURVIVAL"
        and stream_response.get("server_ping_observed_directly") is False
        and stream_response.get("client_pong_observed_directly") is False
    )
    heartbeat_window_observed = (
        stream_response.get("heartbeat_window_observed") is True
        and stream_response.get("connection_survived_heartbeat_window") is True
        and float(stream_response.get("session_duration_ms") or 0) >= P71_HEARTBEAT_OBSERVATION_SECONDS * 1000
    )
    clock_evidence_valid = (
        stream_response.get("server_timestamp_present") is True
        and stream_response.get("clock_offset_within_limit") is True
        and _as_int(stream_response.get("max_abs_clock_offset_ms")) is not None
    )
    consistency = _orderbook_consistency(orderbook if isinstance(orderbook, Mapping) else {}, stream_message_map)

    if not stream_called or not stream_received:
        blockers.append("P71_PUBLIC_STREAM_SNAPSHOT_MISSING")
    if not initial_snapshot_valid:
        blockers.append("P71_PUBLIC_STREAM_INITIAL_SNAPSHOT_INVALID")
    if not sequence_valid:
        blockers.append("P71_PUBLIC_STREAM_SEQUENCE_INVALID")
    if not stream_market_valid:
        blockers.append("P71_PUBLIC_STREAM_MARKET_MISMATCH")
    if not heartbeat_policy_valid:
        blockers.append("P71_PUBLIC_STREAM_HEARTBEAT_POLICY_INVALID")
    if not heartbeat_window_observed:
        blockers.append("P71_PUBLIC_STREAM_HEARTBEAT_WINDOW_NOT_OBSERVED")
    if not clock_evidence_valid:
        blockers.append("P71_PUBLIC_STREAM_CLOCK_EVIDENCE_INVALID")
    if not consistency["valid"]:
        blockers.append("P71_PUBLIC_REST_WS_ORDERBOOK_INCONSISTENT")

    write_probe = dict(write_block_probe or {})
    write_block_probe_valid = (
        write_probe.get("called") is False
        and write_probe.get("blocked") is True
        and write_probe.get("reason") == "P71_WRITE_CALL_BLOCKED"
    )
    if not write_block_probe_valid:
        blockers.append("P71_WRITE_BLOCK_PROBE_INVALID")

    safe_projection = {
        "market": market,
        "orderbook": orderbook,
        "stream_message": stream_message_map,
        "market_response": dict(market_response),
        "orderbook_response": dict(orderbook_response),
        "stream_response": dict(stream_response),
        "write_block_probe": write_probe,
        "observed_at_utc": observed_at,
    }
    secret_matches = _recursive_forbidden_key_matches(safe_projection)
    if secret_matches:
        blockers.append("P71_NO_SECRET_SCAN_FAILED")

    public_rest_valid = all(
        (
            market_response.get("called") is True,
            market_response.get("blocked") is False,
            market_response.get("http_status") == 200,
            orderbook_response.get("called") is True,
            orderbook_response.get("blocked") is False,
            orderbook_response.get("http_status") == 200,
            market_name == EXTENDED_TESTNET_MARKET,
            market_status in {"ACTIVE", "TRADING"},
            isinstance(trading_config, Mapping) and bool(trading_config),
            isinstance(orderbook, Mapping) and bool(_extract_levels(orderbook, "bid")) and bool(_extract_levels(orderbook, "ask")),
            market_rules_fresh,
            orderbook_fresh,
            market_rate_limit_valid,
            orderbook_rate_limit_valid,
        )
    )
    public_stream_valid = all(
        (
            stream_called,
            stream_received,
            initial_snapshot_valid,
            sequence_valid,
            stream_market_valid,
            heartbeat_policy_valid,
            heartbeat_window_observed,
            clock_evidence_valid,
            consistency["valid"],
        )
    )
    public_valid = not blockers
    evidence = {
        "version": P71_VERSION,
        "evidence_id": stable_id("p71_extended_public_read_only", {"session": uuid.uuid4().hex, "observed_at_utc": observed_at}),
        "public_read_session_id": f"p71_public_read_session_{uuid.uuid4().hex}",
        "venue": "extended_starknet_sepolia",
        "environment": "testnet",
        "market": EXTENDED_TESTNET_MARKET,
        "observed_at_utc": observed_at,
        "observed_at_epoch_ms": observed_ms,
        "expires_at_utc": expires_at,
        "evidence_max_age_seconds": P71_EVIDENCE_MAX_AGE_SECONDS,
        "public_rest_valid": public_rest_valid,
        "market_rules_fresh": market_rules_fresh,
        "market_rules_age_ms": market_age_ms,
        "market_rules_max_age_ms": P71_MARKET_RULE_MAX_AGE_MS,
        "orderbook_fresh": orderbook_fresh,
        "orderbook_age_ms": orderbook_age_ms,
        "orderbook_max_age_ms": P71_ORDERBOOK_MAX_AGE_MS,
        "public_rest_rate_limit_policy_valid": market_rate_limit_valid and orderbook_rate_limit_valid,
        "market_rate_limit_evidence": market_response.get("rate_limit_evidence"),
        "orderbook_rate_limit_evidence": orderbook_response.get("rate_limit_evidence"),
        "public_stream_valid": public_stream_valid,
        "public_stream_error_type": stream_response.get("error_type"),
        "public_stream_http_status": stream_response.get("http_status"),
        "public_stream_error": stream_response.get("error"),
        "public_stream_initial_snapshot_valid": initial_snapshot_valid,
        "public_stream_sequence_valid": sequence_valid,
        "public_stream_sequence_gap_count": stream_response.get("sequence_gap_count"),
        "public_stream_reconnect_count": stream_response.get("reconnect_count"),
        "public_stream_reconnect_reasons": stream_response.get("reconnect_reasons"),
        "public_stream_resync_performed": stream_response.get("resync_performed") is True,
        "public_stream_resync_snapshot_received": stream_response.get("resync_snapshot_received") is True,
        "public_stream_heartbeat_policy_valid": heartbeat_policy_valid,
        "public_stream_heartbeat_evidence_mode": stream_response.get("heartbeat_evidence_mode"),
        "public_stream_server_ping_observed_directly": False,
        "public_stream_client_pong_observed_directly": False,
        "public_stream_heartbeat_window_observed": heartbeat_window_observed,
        "public_stream_clock_evidence_valid": clock_evidence_valid,
        "public_stream_max_abs_clock_offset_ms": stream_response.get("max_abs_clock_offset_ms"),
        "public_rest_ws_consistency": consistency,
        "public_rest_ws_consistency_valid": consistency["valid"],
        "market_status": market_status or None,
        "trading_rules_present": isinstance(trading_config, Mapping) and bool(trading_config),
        "no_secret_scan_passed": not secret_matches,
        "no_secret_scan_matches": secret_matches,
        "public_connectivity_valid": public_valid,
        "private_account_read_evidence_valid": False,
        "private_account_stream_evidence_valid": False,
        "p71_complete": False,
        "status": "P71_PUBLIC_READ_ONLY_VALID_PRIVATE_EVIDENCE_PENDING" if public_valid else "P71_PUBLIC_READ_ONLY_BLOCKED",
        "block_reasons": sorted(set(blockers + ["P71_PRIVATE_READ_AND_STREAM_EVIDENCE_PENDING"])),
        "write_block_probe": write_probe,
        "write_block_probe_valid": write_block_probe_valid,
        "network_write_call_performed": False,
        "order_endpoint_called": False,
        "cancel_endpoint_called": False,
        "signature_created": False,
        "stark_private_key_accessed": False,
        "testnet_order_submission_allowed": False,
        "market_response_hash": sha256_json(dict(market_response)),
        "orderbook_response_hash": sha256_json(dict(orderbook_response)),
        "stream_response_hash": sha256_json(dict(stream_response)),
    }
    evidence["evidence_sha256"] = sha256_json(evidence)
    return evidence


def run_p71_public_probe(
    *,
    network_enabled: bool,
    rest_get: RestGet | None = None,
    stream_probe: PublicStreamProbe | None = None,
    timeout_seconds: float = 30.0,
    sleep_fn: SleepFn = time.sleep,
    random_fn: Callable[[], float] = random.random,
) -> dict[str, Any]:
    client = ExtendedPublicReadOnlyClient(
        ExtendedPublicReadOnlyPolicy(network_enabled=network_enabled, timeout_seconds=timeout_seconds),
        rest_get=rest_get,
        stream_probe=stream_probe,
        sleep_fn=sleep_fn,
        random_fn=random_fn,
    )
    market = client.get_market()
    orderbook = client.get_orderbook()
    stream = client.get_orderbook_stream_snapshot()
    write_block = client.post("/user/order", {})
    return build_p71_public_connectivity_evidence(
        market_response=market,
        orderbook_response=orderbook,
        stream_response=stream,
        write_block_probe=write_block,
    )


def _validate_timestamp_window(
    *,
    created_at_utc: Any,
    expires_at_utc: Any,
    max_age_seconds: Any,
    now_epoch_ms: int,
    prefix: str,
) -> list[str]:
    blockers: list[str] = []
    created_ms = _parse_canonical_utc_ms(created_at_utc)
    expires_ms = _parse_canonical_utc_ms(expires_at_utc)
    max_age = _as_int(max_age_seconds)
    if created_ms is None or expires_ms is None or max_age is None or max_age <= 0:
        return [f"{prefix}_TIMESTAMP_CONTRACT_INVALID"]
    if expires_ms != created_ms + max_age * 1000:
        blockers.append(f"{prefix}_EXPIRY_CONTRACT_INVALID")
    if now_epoch_ms < created_ms - P71_MAX_CLOCK_OFFSET_MS:
        blockers.append(f"{prefix}_CREATED_IN_FUTURE")
    if now_epoch_ms > expires_ms or now_epoch_ms - created_ms > max_age * 1000:
        blockers.append(f"{prefix}_EVIDENCE_STALE")
    return blockers


def validate_p71_private_account_evidence(
    receipt: Mapping[str, Any] | None,
    *,
    now_epoch_ms: int | None = None,
    seen_session_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    data = dict(receipt or {})
    blockers: list[str] = []
    now_ms = now_epoch_ms if now_epoch_ms is not None else _epoch_ms()
    if data.get("version") != P71_PRIVATE_RECEIPT_VERSION:
        blockers.append("P71_PRIVATE_RECEIPT_VERSION_INVALID")
    if data.get("venue") != "extended_starknet_sepolia" or data.get("environment") != "testnet" or data.get("market") != "BTC-USD":
        blockers.append("P71_PRIVATE_RECEIPT_SCOPE_INVALID")
    session_id = str(data.get("read_session_id") or "")
    if not session_id.startswith("p71_private_read_session_"):
        blockers.append("P71_PRIVATE_SESSION_ID_INVALID")
    if seen_session_ids is not None and session_id in set(seen_session_ids):
        blockers.append("P71_PRIVATE_SESSION_REPLAY_DETECTED")
    blockers.extend(
        _validate_timestamp_window(
            created_at_utc=data.get("created_at_utc"),
            expires_at_utc=data.get("expires_at_utc"),
            max_age_seconds=data.get("evidence_max_age_seconds"),
            now_epoch_ms=now_ms,
            prefix="P71_PRIVATE",
        )
    )
    if not str(data.get("credential_reference_id") or "").strip():
        blockers.append("P71_PRIVATE_CREDENTIAL_REFERENCE_MISSING")
    if not _is_sha256(data.get("api_key_fingerprint_sha256")):
        blockers.append("P71_PRIVATE_API_KEY_FINGERPRINT_INVALID")

    endpoints = data.get("endpoint_receipts") or {}
    required = {"account_info", "balance", "positions", "open_orders"}
    if not isinstance(endpoints, Mapping) or set(endpoints) != required:
        blockers.append("P71_PRIVATE_REQUIRED_ENDPOINT_EVIDENCE_MISSING")
    else:
        for name, raw_item in endpoints.items():
            item = raw_item if isinstance(raw_item, Mapping) else {}
            if item.get("http_method") != "GET":
                blockers.append(f"P71_PRIVATE_ENDPOINT_METHOD_INVALID:{name}")
            if item.get("schema_valid") is not True:
                blockers.append(f"P71_PRIVATE_ENDPOINT_SCHEMA_INVALID:{name}")
            if item.get("redirect_blocked") is True:
                blockers.append(f"P71_PRIVATE_ENDPOINT_REDIRECT_BLOCKED:{name}")
            if item.get("rate_limit_policy_valid") is not True:
                blockers.append(f"P71_PRIVATE_ENDPOINT_RATE_LIMIT_INVALID:{name}")
            if not _is_sha256(item.get("response_sha256")):
                blockers.append(f"P71_PRIVATE_ENDPOINT_HASH_INVALID:{name}")
            zero_balance_valid = name == "balance" and item.get("http_status") == 404 and item.get("zero_balance_confirmed") is True
            normal_read_valid = item.get("http_status") == 200 and item.get("response_status") == "OK"
            if not (normal_read_valid or zero_balance_valid):
                blockers.append(f"P71_PRIVATE_ENDPOINT_INVALID:{name}")

    private_stream = data.get("account_stream_receipt") or {}
    if not isinstance(private_stream, Mapping):
        blockers.append("P71_PRIVATE_ACCOUNT_STREAM_RECEIPT_MISSING")
    else:
        for field in (
            "actual_network_read_performed",
            "initial_snapshot_valid",
            "sequence_valid",
            "heartbeat_policy_valid",
            "heartbeat_window_observed",
            "clock_evidence_valid",
            "market_scope_valid",
            "no_secret_scan_passed",
        ):
            if private_stream.get(field) is not True:
                blockers.append(f"P71_PRIVATE_ACCOUNT_STREAM_{field.upper()}_NOT_TRUE")
        if private_stream.get("heartbeat_evidence_mode") != "INFERRED_FROM_CONNECTION_SURVIVAL":
            blockers.append("P71_PRIVATE_ACCOUNT_STREAM_HEARTBEAT_MODE_INVALID")
        if private_stream.get("server_ping_observed_directly") is not False or private_stream.get("client_pong_observed_directly") is not False:
            blockers.append("P71_PRIVATE_ACCOUNT_STREAM_DIRECT_HEARTBEAT_CLAIM_INVALID")
        for hash_field in ("first_message_sha256", "last_message_sha256"):
            if not _is_sha256(private_stream.get(hash_field)):
                blockers.append(f"P71_PRIVATE_ACCOUNT_STREAM_HASH_INVALID:{hash_field}")

    if data.get("rest_ws_consistency_valid") is not True:
        blockers.append("P71_PRIVATE_REST_WS_CONSISTENCY_INVALID")
    if data.get("actual_network_read_performed") is not True:
        blockers.append("P71_PRIVATE_ACTUAL_NETWORK_READ_NOT_PROVEN")
    if data.get("source_is_fixture") is not False:
        blockers.append("P71_PRIVATE_FIXTURE_NOT_REAL_EVIDENCE")
    for field in ("all_requests_get", "no_secret_scan_passed"):
        if data.get(field) is not True:
            blockers.append(f"P71_PRIVATE_{field.upper()}_NOT_TRUE")
    for field in (
        "write_call_performed",
        "order_endpoint_called",
        "cancel_endpoint_called",
        "signature_created",
        "stark_private_key_accessed",
        "credential_value_included",
    ):
        if data.get(field) is not False:
            blockers.append(f"P71_PRIVATE_UNSAFE_FLAG:{field}")
    recursive_matches = _recursive_forbidden_key_matches(data)
    if recursive_matches:
        blockers.append("P71_PRIVATE_RECURSIVE_NO_SECRET_SCAN_FAILED")
    if not _is_sha256(data.get("receipt_sha256")) or data.get("receipt_sha256") != _hash_without_field(data, "receipt_sha256"):
        blockers.append("P71_PRIVATE_RECEIPT_HASH_MISMATCH")
    return {"valid": not blockers, "block_reasons": sorted(set(blockers)), "receipt": data}


def _validate_public_evidence(
    public: Mapping[str, Any],
    *,
    now_epoch_ms: int,
    seen_evidence_ids: Iterable[str] | None = None,
) -> list[str]:
    blockers: list[str] = []
    if public.get("version") != P71_VERSION:
        blockers.append("P71_PUBLIC_EVIDENCE_VERSION_INVALID")
    if public.get("venue") != "extended_starknet_sepolia" or public.get("environment") != "testnet" or public.get("market") != "BTC-USD":
        blockers.append("P71_PUBLIC_EVIDENCE_SCOPE_INVALID")
    evidence_id = str(public.get("evidence_id") or "")
    if not evidence_id.startswith("p71_extended_public_read_only_"):
        blockers.append("P71_PUBLIC_EVIDENCE_ID_INVALID")
    if seen_evidence_ids is not None and evidence_id in set(seen_evidence_ids):
        blockers.append("P71_PUBLIC_EVIDENCE_REPLAY_DETECTED")
    blockers.extend(
        _validate_timestamp_window(
            created_at_utc=public.get("observed_at_utc"),
            expires_at_utc=public.get("expires_at_utc"),
            max_age_seconds=public.get("evidence_max_age_seconds"),
            now_epoch_ms=now_epoch_ms,
            prefix="P71_PUBLIC",
        )
    )
    required_true = (
        "public_rest_valid",
        "market_rules_fresh",
        "orderbook_fresh",
        "public_rest_rate_limit_policy_valid",
        "public_stream_valid",
        "public_stream_initial_snapshot_valid",
        "public_stream_sequence_valid",
        "public_stream_heartbeat_policy_valid",
        "public_stream_heartbeat_window_observed",
        "public_stream_clock_evidence_valid",
        "public_rest_ws_consistency_valid",
        "no_secret_scan_passed",
        "public_connectivity_valid",
        "write_block_probe_valid",
    )
    for field in required_true:
        if public.get(field) is not True:
            blockers.append(f"P71_PUBLIC_REQUIRED_FLAG_NOT_TRUE:{field}")
    for field in (
        "network_write_call_performed",
        "order_endpoint_called",
        "cancel_endpoint_called",
        "signature_created",
        "stark_private_key_accessed",
        "testnet_order_submission_allowed",
    ):
        if public.get(field) is not False:
            blockers.append(f"P71_PUBLIC_UNSAFE_FLAG:{field}")
    if public.get("public_stream_heartbeat_evidence_mode") != "INFERRED_FROM_CONNECTION_SURVIVAL":
        blockers.append("P71_PUBLIC_HEARTBEAT_MODE_INVALID")
    if public.get("public_stream_server_ping_observed_directly") is not False or public.get("public_stream_client_pong_observed_directly") is not False:
        blockers.append("P71_PUBLIC_DIRECT_HEARTBEAT_CLAIM_INVALID")
    if _recursive_forbidden_key_matches(public):
        blockers.append("P71_PUBLIC_RECURSIVE_NO_SECRET_SCAN_FAILED")
    if not _is_sha256(public.get("evidence_sha256")) or public.get("evidence_sha256") != _hash_without_field(public, "evidence_sha256"):
        blockers.append("P71_PUBLIC_EVIDENCE_HASH_MISMATCH")
    return blockers


def build_p71_complete_evidence(
    *,
    public_evidence: Mapping[str, Any],
    private_receipt: Mapping[str, Any],
    now_epoch_ms: int | None = None,
    seen_public_evidence_ids: Iterable[str] | None = None,
    seen_private_session_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    now_ms = now_epoch_ms if now_epoch_ms is not None else _epoch_ms()
    public = dict(public_evidence or {})
    private_validation = validate_p71_private_account_evidence(
        private_receipt,
        now_epoch_ms=now_ms,
        seen_session_ids=seen_private_session_ids,
    )
    blockers = _validate_public_evidence(public, now_epoch_ms=now_ms, seen_evidence_ids=seen_public_evidence_ids)
    blockers.extend(private_validation["block_reasons"])
    complete = not blockers
    result = {
        "version": P71_VERSION,
        "venue": "extended_starknet_sepolia",
        "environment": "testnet",
        "market": "BTC-USD",
        "public_evidence_sha256": public.get("evidence_sha256"),
        "private_receipt_sha256": private_receipt.get("receipt_sha256"),
        "public_rest_valid": public.get("public_rest_valid") is True,
        "public_stream_valid": public.get("public_stream_valid") is True,
        "private_account_read_evidence_valid": private_validation["valid"],
        "private_account_stream_evidence_valid": private_validation["valid"] and bool((private_receipt.get("account_stream_receipt") or {}).get("initial_snapshot_valid")),
        "p71_complete": complete,
        "status": "P71_EXTENDED_TESTNET_READ_ONLY_COMPLETE" if complete else "P71_EXTENDED_TESTNET_READ_ONLY_BLOCKED",
        "block_reasons": sorted(set(blockers)),
        "network_write_call_performed": False,
        "order_endpoint_called": False,
        "cancel_endpoint_called": False,
        "signature_created": False,
        "stark_private_key_accessed": False,
        "testnet_order_submission_allowed": False,
        "ready_for_signed_testnet_execution": False,
        "created_at_utc": _canonical_from_epoch_ms(now_ms),
    }
    result["evidence_sha256"] = sha256_json(result)
    return result


__all__ = [
    "P71_VERSION",
    "P71_PRIVATE_RECEIPT_VERSION",
    "EXTENDED_TESTNET_API_BASE_URL",
    "EXTENDED_TESTNET_STREAM_BASE_URL",
    "EXTENDED_TESTNET_MARKET",
    "PUBLIC_ORDERBOOK_STREAM_PATH",
    "P71_SDK_USER_AGENT",
    "P71_SERVER_PING_INTERVAL_SECONDS",
    "P71_PONG_TIMEOUT_SECONDS",
    "P71_HEARTBEAT_OBSERVATION_SECONDS",
    "P71_MAX_CLOCK_OFFSET_MS",
    "P71_MARKET_RULE_MAX_AGE_MS",
    "P71_ORDERBOOK_MAX_AGE_MS",
    "P71_EVIDENCE_MAX_AGE_SECONDS",
    "ExtendedReadOnlyPolicyError",
    "ExtendedStreamResyncRequired",
    "ExtendedPublicReadOnlyPolicy",
    "ExtendedPublicReadOnlyClient",
    "websocket_public_snapshot_probe",
    "build_p71_public_connectivity_evidence",
    "run_p71_public_probe",
    "validate_p71_private_account_evidence",
    "build_p71_complete_evidence",
]

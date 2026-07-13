from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

import yaml

from core.json_io import atomic_write_json
from core.time_utils import utc_now_iso
from core.event_log import log_event


LIVE_GUARD_MODE = "READINESS_CHECK_ONLY"
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED = False
PROJECT_ROOT = Path(__file__).resolve().parents[3]
LIVE_READINESS_PATH = PROJECT_ROOT / "storage" / "latest" / "live_readiness_check.json"
LIVE_TRADING_CONFIRMATION_PHRASE = "I_UNDERSTAND_THIS_PLACES_REAL_ORDERS"


def _load_settings() -> dict[str, Any]:
    path = PROJECT_ROOT / "config" / "settings.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _get_nested(mapping: Mapping[str, Any], dotted_path: str, default: Any = None) -> Any:
    value: Any = mapping
    for part in dotted_path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return default
        value = value[part]
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_str(name: str, default: str = "") -> str:
    raw = os.getenv(name)
    return default if raw is None else str(raw).strip()


def _live_secret_metadata(settings: Mapping[str, Any]) -> dict[str, Any]:
    node = _get_nested(settings, "execution.live_key_scope_validator", {})
    if not isinstance(node, Mapping):
        node = {}
    return {
        "metadata_only": node.get("metadata_only") is True,
        "secret_reference_id_present": bool(str(node.get("secret_reference_id") or "").strip()),
        "key_fingerprint_sha256_present": bool(str(node.get("key_fingerprint_sha256") or "").strip()),
        "secret_value_accessed": False,
        "secret_file_read": False,
        "secret_file_created": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "secret_reference_id": node.get("secret_reference_id") if node.get("secret_reference_id") else None,
    }


def run_live_readiness_check() -> dict:
    """Review-only live readiness surface.

    This guard must not read API key values, API secret values, passphrases, or
    secret files. It only checks disabled execution flags and metadata-only
    secret references. Real testnet/live submission must be implemented in a
    separate approved runtime boundary.
    """
    settings = _load_settings()
    blockers = []

    trading_mode = _env_str("TRADING_MODE", "paper").lower()
    live_trading_enabled = _env_bool(
        "LIVE_TRADING_ENABLED",
        _get_nested(settings, "safety.live_trading_enabled", False) is True,
    )
    allow_live_trading = _env_bool("ALLOW_LIVE_TRADING", False)
    exchange_order_enabled = _env_bool("EXCHANGE_ORDER_ENABLED", False)
    enable_real_orders = _env_bool("ENABLE_REAL_ORDERS", False)
    enable_testnet_orders = _env_bool(
        "ENABLE_TESTNET_ORDERS",
        _get_nested(settings, "safety.testnet_signed_order_enabled", False) is True,
    )
    live_trading_confirmation = _env_str("LIVE_TRADING_CONFIRMATION", "")
    max_live_position_usdt = _env_float("MAX_LIVE_POSITION_USDT", 20.0)
    max_order_notional_usdt = _env_float("MAX_ORDER_NOTIONAL_USDT", 20.0)
    secret_metadata = _live_secret_metadata(settings)

    if trading_mode != "live":
        blockers.append("TRADING_MODE_not_live")
    if not live_trading_enabled:
        blockers.append("LIVE_TRADING_ENABLED_false")
    if not allow_live_trading:
        blockers.append("ALLOW_LIVE_TRADING_false")
    if not exchange_order_enabled:
        blockers.append("EXCHANGE_ORDER_ENABLED_false")
    if not enable_real_orders:
        blockers.append("ENABLE_REAL_ORDERS_false")
    if live_trading_confirmation != LIVE_TRADING_CONFIRMATION_PHRASE:
        blockers.append("LIVE_TRADING_CONFIRMATION_mismatch")
    if secret_metadata["metadata_only"] is not True:
        blockers.append("live_secret_metadata_not_metadata_only")
    if not secret_metadata["secret_reference_id_present"]:
        blockers.append("missing_exchange_secret_metadata_reference")
    if not secret_metadata["key_fingerprint_sha256_present"]:
        blockers.append("missing_exchange_key_fingerprint_sha256_metadata")
    if max_order_notional_usdt > max_live_position_usdt:
        blockers.append("order_notional_exceeds_live_position_limit")

    result = {
        "created_at": utc_now_iso(),
        "ready": False,
        "ready_if_review_only_ignored": len(blockers) == 0,
        "blockers": blockers + ["live_guard_is_review_only_no_runtime_authority"],
        "testnet_orders_enabled": enable_testnet_orders,
        "live_guard_mode": LIVE_GUARD_MODE,
        "live_trading_allowed_by_this_module": LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED,
        "max_live_position_usdt": max_live_position_usdt,
        "max_order_notional_usdt": max_order_notional_usdt,
        "secret_metadata_boundary": secret_metadata,
    }
    atomic_write_json(LIVE_READINESS_PATH, result)
    log_event("live_readiness_checked", {"ready": result["ready"], "blockers": result["blockers"]})
    return result


def main() -> None:
    result = run_live_readiness_check()
    print(f"Live readiness: ready={result['ready']} blockers={len(result['blockers'])}")


if __name__ == "__main__":
    main()

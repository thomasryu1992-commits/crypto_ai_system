from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import env_bool, env_float, env_int, env_str
from scripts.json_utils import append_json_log, load_json, now_utc_iso, save_json, to_float


def run_order_risk_check(order_request: Dict[str, Any], storage_dir: str | Path = "storage", current_price: Optional[float] = None) -> Dict[str, Any]:
    storage_path = Path(storage_dir)
    context = _load_context(storage_path, current_price, order_request)
    checks = _run_checks(order_request, context)
    approved = all(c.get("passed") for c in checks)
    result = {
        "step": "STEP_45_48_RISK_MANAGER",
        "timestamp_utc": now_utc_iso(),
        "status": "APPROVED" if approved else "REJECTED",
        "approved": approved,
        "order_request": order_request,
        "context": context,
        "checks": checks,
        "failed_checks": [c for c in checks if not c.get("passed")],
        "safety": {
            "live_trading_enabled": context.get("live_trading_enabled"),
            "exchange_order_enabled": context.get("exchange_order_enabled"),
            "exchange_mode": context.get("exchange_mode"),
            "bridge_order_exception_enabled": context.get("is_bridge_order"),
        },
    }
    save_json(storage_path / "risk_check_result.json", result)
    append_json_log(storage_path / "risk_check_log.json", result)
    return result


def _load_context(storage_path: Path, current_price: Optional[float], order_request: Dict[str, Any]) -> Dict[str, Any]:
    positions = load_json(storage_path / "paper_positions.json", default=[])
    history = load_json(storage_path / "paper_trade_history.json", default=[])
    gate = load_json(storage_path / "setup_decision_filter_result.json", default={})
    if not isinstance(positions, list): positions = []
    if not isinstance(history, list): history = []
    open_positions = [p for p in positions if isinstance(p, dict) and p.get("status") == "OPEN"]
    metadata = order_request.get("metadata", {}) if isinstance(order_request, dict) else {}
    if not isinstance(metadata, dict): metadata = {}
    source = str(metadata.get("source") or "")
    position_id = metadata.get("position_id")
    is_bridge_order = source == "trading_bot.order_executor_bridge"
    bridge_position_exists = any(str(p.get("position_id") or p.get("id")) == str(position_id) for p in open_positions if isinstance(p, dict)) if position_id else False
    return {
        "mode": env_str("BOT_MODE", "PAPER_ONLY").upper(),
        "exchange_mode": env_str("EXCHANGE_MODE", "MOCK").upper(),
        "exchange_order_enabled": env_bool("EXCHANGE_ORDER_ENABLED", False),
        "live_trading_enabled": env_bool("LIVE_TRADING_ENABLED", False),
        "max_order_usdt": env_float("MAX_ORDER_USDT", 10.0),
        "max_position_usdt": env_float("MAX_POSITION_USDT", 10.0),
        "max_open_positions": env_int("MAX_OPEN_POSITIONS", 1),
        "max_recent_losses": env_int("MAX_RECENT_LOSSES", 3),
        "current_price": to_float(current_price),
        "open_position_count": len(open_positions),
        "recent_loss_count": _recent_losses(history),
        "setup_decision_gate_status": gate.get("status") if isinstance(gate, dict) else None,
        "setup_weight_decision": gate.get("setup_weight_decision") if isinstance(gate, dict) else None,
        "setup_type": gate.get("setup_type") if isinstance(gate, dict) else metadata.get("setup_type"),
        "order_metadata": {"source": source, "position_id": position_id, "setup_type": metadata.get("setup_type")},
        "is_bridge_order": is_bridge_order,
        "bridge_position_exists": bridge_position_exists,
    }


def _run_checks(order_request: Dict[str, Any], context: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        _check_live_disabled(context),
        _check_mock_only(context),
        _check_exchange_enabled(context),
        _check_order_valid(order_request),
        _check_order_notional(order_request, context),
        _check_max_open_positions(context),
        _check_recent_losses(context),
        _check_setup_not_disabled(context),
    ]


def _check_live_disabled(c: Dict[str, Any]) -> Dict[str, Any]:
    passed = not bool(c.get("live_trading_enabled"))
    return {"name": "LIVE_TRADING_DISABLED", "passed": passed, "message": "Live trading is disabled." if passed else "Live trading is enabled and blocked."}


def _check_mock_only(c: Dict[str, Any]) -> Dict[str, Any]:
    passed = c.get("exchange_mode") == "MOCK"
    return {"name": "EXCHANGE_MODE_MOCK_ONLY", "passed": passed, "message": "Exchange mode is MOCK." if passed else "Only MOCK mode is allowed."}


def _check_exchange_enabled(c: Dict[str, Any]) -> Dict[str, Any]:
    passed = bool(c.get("exchange_order_enabled"))
    return {"name": "EXCHANGE_ORDER_ENABLED", "passed": passed, "message": "Exchange order routing is enabled." if passed else "EXCHANGE_ORDER_ENABLED=false."}


def _check_order_valid(order: Dict[str, Any]) -> Dict[str, Any]:
    validation = order.get("validation", {}) if isinstance(order, dict) else {}
    if not isinstance(validation, dict): validation = {}
    passed = bool(validation.get("valid"))
    return {"name": "ORDER_REQUEST_VALID", "passed": passed, "message": "Order request is valid." if passed else "Order request validation failed.", "errors": validation.get("errors", [])}


def _check_order_notional(order: Dict[str, Any], c: Dict[str, Any]) -> Dict[str, Any]:
    qty = to_float(order.get("quantity"))
    price = to_float(order.get("price")) or to_float(c.get("current_price"))
    max_order = to_float(c.get("max_order_usdt")) or 0.0
    if qty is None or price is None:
        return {"name": "ORDER_NOTIONAL_LIMIT", "passed": False, "message": "Cannot calculate notional."}
    notional = qty * price
    passed = notional <= max_order
    return {"name": "ORDER_NOTIONAL_LIMIT", "passed": passed, "message": f"Order notional {notional:.4f} / limit {max_order:.4f}.", "order_notional_usdt": round(notional, 6), "max_order_usdt": max_order}


def _check_max_open_positions(c: Dict[str, Any]) -> Dict[str, Any]:
    open_count = int(c.get("open_position_count") or 0)
    max_open = int(c.get("max_open_positions") or 1)
    if c.get("is_bridge_order") and c.get("bridge_position_exists") and open_count <= max_open:
        return {"name": "MAX_OPEN_POSITIONS", "passed": True, "message": f"Bridge exception applied. open_position_count={open_count}, max_open_positions={max_open}.", "bridge_exception_applied": True}
    passed = open_count < max_open
    return {"name": "MAX_OPEN_POSITIONS", "passed": passed, "message": f"Open position count {open_count} / limit {max_open}.", "bridge_exception_applied": False}


def _check_recent_losses(c: Dict[str, Any]) -> Dict[str, Any]:
    recent = int(c.get("recent_loss_count") or 0)
    limit = int(c.get("max_recent_losses") or 3)
    passed = recent < limit
    return {"name": "RECENT_LOSS_LIMIT", "passed": passed, "message": f"Recent losses {recent} / limit {limit}."}


def _check_setup_not_disabled(c: Dict[str, Any]) -> Dict[str, Any]:
    gate = str(c.get("setup_decision_gate_status") or "").upper()
    decision = str(c.get("setup_weight_decision") or "").upper()
    blocked = gate == "BLOCKED" or decision == "DISABLED"
    return {"name": "SETUP_NOT_DISABLED", "passed": not blocked, "message": "Setup is not disabled." if not blocked else "Setup is blocked or disabled."}


def _recent_losses(history: List[Any], max_trades: int = 5) -> int:
    recent = history[-max_trades:] if isinstance(history, list) else []
    return sum(1 for t in recent if isinstance(t, dict) and (to_float(t.get("realized_pnl_pct")) or 0.0) < 0)

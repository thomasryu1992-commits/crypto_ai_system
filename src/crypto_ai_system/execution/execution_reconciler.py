from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.json_utils import append_json_log, load_json, now_utc_iso, save_json, to_float


EXECUTION_RECONCILIATION_MODE = "CHECK_ONLY"
LIVE_POSITION_SYNC_ENABLED_BY_THIS_MODULE = False
EXTERNAL_EXECUTION_SYNC_PERFORMED = False


def run_execution_reconciliation(storage_dir: str | Path = "storage") -> Dict[str, Any]:
    storage_path = Path(storage_dir)
    result_path = storage_path / "execution_reconciliation_result.json"
    log_path = storage_path / "execution_reconciliation_log.json"

    paper_positions = load_json(storage_path / "paper_positions.json", default=[])
    order_execution_result = load_json(storage_path / "order_execution_result.json", default={})
    mock_order_result = load_json(storage_path / "mock_order_result.json", default={})
    execution_map = load_json(storage_path / "paper_order_execution_map.json", default={})
    risk_check_result = load_json(storage_path / "risk_check_result.json", default={})
    exchange_router_result = load_json(storage_path / "exchange_router_result.json", default={})

    if not isinstance(paper_positions, list): paper_positions = []
    if not isinstance(order_execution_result, dict): order_execution_result = {}
    if not isinstance(mock_order_result, dict): mock_order_result = {}
    if not isinstance(execution_map, dict): execution_map = {}
    if not isinstance(risk_check_result, dict): risk_check_result = {}
    if not isinstance(exchange_router_result, dict): exchange_router_result = {}

    context = _context(paper_positions, order_execution_result, mock_order_result, execution_map, risk_check_result, exchange_router_result)
    checks = _checks(context)
    status = _status(checks, context)
    result = {
        "step": "STEP_49_EXECUTION_RECONCILIATION_MANAGER",
        "timestamp_utc": now_utc_iso(),
        "status": status,
        "reconciled": status == "RECONCILED",
        "context": context,
        "checks": checks,
        "failed_checks": [c for c in checks if not c.get("passed")],
        "safety": {
            "execution_reconciliation_mode": EXECUTION_RECONCILIATION_MODE,
            "live_position_sync_enabled_by_this_module": LIVE_POSITION_SYNC_ENABLED_BY_THIS_MODULE,
            "external_execution_sync_performed": EXTERNAL_EXECUTION_SYNC_PERFORMED,
            "live_order_executed": context.get("live_order_executed"),
            "exchange": context.get("exchange"),
            "execution_status": context.get("order_execution_status"),
        },
    }
    save_json(result_path, result)
    append_json_log(log_path, result)
    return result


def _context(positions: List[Dict[str, Any]], order_exec: Dict[str, Any], mock: Dict[str, Any], execution_map: Dict[str, Any], risk: Dict[str, Any], router: Dict[str, Any]) -> Dict[str, Any]:
    open_positions = [p for p in positions if isinstance(p, dict) and p.get("status") == "OPEN"]
    latest = open_positions[-1] if open_positions else {}
    order_request = _extract_order_request(order_exec, mock)
    metadata = order_request.get("metadata", {}) if isinstance(order_request, dict) else {}
    if not isinstance(metadata, dict): metadata = {}
    pos_order = metadata.get("position_id")
    pos_paper = latest.get("position_id") or latest.get("id") if isinstance(latest, dict) else None
    filled_price = _filled_price(order_exec, mock, router)
    filled_qty = _filled_quantity(order_exec, mock, router)
    paper_entry = to_float(latest.get("entry_price")) if isinstance(latest, dict) else None
    return {
        "paper_position_count": len(positions),
        "open_position_count": len(open_positions),
        "position_id_from_paper": pos_paper,
        "position_id_from_order": pos_order,
        "execution_map_entry": execution_map.get(str(pos_order)) if pos_order else None,
        "execution_map_size": len(execution_map),
        "order_execution_status": order_exec.get("status"),
        "mock_order_status": mock.get("status"),
        "exchange_router_status": router.get("status"),
        "risk_status": risk.get("status"),
        "risk_approved": risk.get("approved"),
        "exchange": mock.get("exchange") or router.get("exchange_mode"),
        "order_side": str(order_request.get("side") or "").upper() if isinstance(order_request, dict) else None,
        "paper_direction": str(latest.get("direction") or "").upper() if isinstance(latest, dict) else None,
        "expected_side": _expected_side(str(latest.get("direction") or "")) if isinstance(latest, dict) else None,
        "filled_price": filled_price,
        "filled_quantity": filled_qty,
        "paper_entry_price": paper_entry,
        "price_diff_pct": _price_diff_pct(paper_entry, filled_price),
        "live_order_executed": _live_order_executed(order_exec, mock, router),
        "order_request": _compact_order(order_request),
    }


def _checks(c: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        _check("EXECUTION_EXISTS", bool(c.get("order_execution_status") or c.get("mock_order_status") or c.get("exchange_router_status")), "Execution result exists.", "No execution result found."),
        _check("LIVE_ORDER_NOT_EXECUTED", not bool(c.get("live_order_executed")), "live_order_executed=false confirmed.", "Unsafe live_order_executed=true detected."),
        _check("POSITION_ID_EXISTS", bool(c.get("position_id_from_paper") and c.get("position_id_from_order")), "Position IDs exist.", "Missing paper or order position ID."),
        _check("POSITION_ID_MATCH", bool(c.get("position_id_from_paper") and c.get("position_id_from_order") and str(c.get("position_id_from_paper")) == str(c.get("position_id_from_order"))), "Position IDs match.", "Position ID mismatch."),
        _check("EXECUTION_MAP_EXISTS", isinstance(c.get("execution_map_entry"), dict), "Execution map entry exists.", "Execution map entry missing."),
        _check("EXECUTION_STATUS_VALID", str(c.get("order_execution_status") or "").upper() in {"MOCK_ORDER_ACCEPTED", "ORDER_EXECUTION_ATTEMPTED"} or str(c.get("mock_order_status") or "").upper() == "ACCEPTED" or str(c.get("exchange_router_status") or "").upper() == "ROUTED_TO_MOCK", "Execution status valid.", "Execution status invalid."),
        _check("RISK_APPROVED", str(c.get("risk_status") or "").upper() == "APPROVED" and c.get("risk_approved") is True, "Risk approved.", "Risk did not approve."),
        _check("ORDER_SIDE_MATCH", bool(c.get("order_side") and c.get("expected_side") and c.get("order_side") == c.get("expected_side")), "Order side matches paper direction.", "Order side mismatch."),
        _check("FILLED_PRICE_EXISTS", (to_float(c.get("filled_price")) or 0) > 0, "Filled price exists.", "Filled price missing."),
        _check("FILLED_QUANTITY_EXISTS", (to_float(c.get("filled_quantity")) or 0) > 0, "Filled quantity exists.", "Filled quantity missing."),
        _check("PRICE_DIFF_REASONABLE", c.get("price_diff_pct") is not None and abs(float(c.get("price_diff_pct"))) <= 1.0, "Price difference within tolerance.", "Price difference exceeds tolerance or missing."),
        _check("DUPLICATE_EXECUTION_NOT_FOUND", int(c.get("execution_map_size") or 0) <= max(int(c.get("open_position_count") or 0), 1), "No obvious duplicate execution found.", "Potential duplicate execution found."),
    ]


def _check(name: str, passed: bool, ok: str, bad: str) -> Dict[str, Any]:
    return {"name": name, "passed": bool(passed), "message": ok if passed else bad}


def _status(checks: List[Dict[str, Any]], context: Dict[str, Any]) -> str:
    if context.get("live_order_executed") is True:
        return "UNSAFE_EXECUTION_FLAG"
    exists = next((x for x in checks if x.get("name") == "EXECUTION_EXISTS"), {})
    if exists.get("passed") is False:
        return "NO_EXECUTION_FOUND"
    dup = next((x for x in checks if x.get("name") == "DUPLICATE_EXECUTION_NOT_FOUND"), {})
    if dup.get("passed") is False:
        return "DUPLICATE_EXECUTION_FOUND"
    return "RECONCILED" if all(x.get("passed") for x in checks) else "MISMATCH_FOUND"


def _extract_order_request(order_exec: Dict[str, Any], mock: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(order_exec.get("order_request"), dict):
        return order_exec["order_request"]
    exchange_result = order_exec.get("exchange_result")
    if isinstance(exchange_result, dict):
        order_result = exchange_result.get("order_result")
        if isinstance(order_result, dict) and isinstance(order_result.get("order_request"), dict):
            return order_result["order_request"]
    if isinstance(mock.get("order_request"), dict):
        return mock["order_request"]
    return {}


def _filled_price(order_exec: Dict[str, Any], mock: Dict[str, Any], router: Dict[str, Any]) -> Optional[float]:
    for obj in [mock, router.get("order_result") if isinstance(router.get("order_result"), dict) else {}, (order_exec.get("exchange_result") or {}).get("order_result") if isinstance(order_exec.get("exchange_result"), dict) else {}]:
        if isinstance(obj, dict):
            value = to_float(obj.get("filled_price"))
            if value is not None:
                return value
    return None


def _filled_quantity(order_exec: Dict[str, Any], mock: Dict[str, Any], router: Dict[str, Any]) -> Optional[float]:
    for obj in [mock, router.get("order_result") if isinstance(router.get("order_result"), dict) else {}, (order_exec.get("exchange_result") or {}).get("order_result") if isinstance(order_exec.get("exchange_result"), dict) else {}]:
        if isinstance(obj, dict):
            value = to_float(obj.get("filled_quantity"))
            if value is not None:
                return value
    return None


def _live_order_executed(order_exec: Dict[str, Any], mock: Dict[str, Any], router: Dict[str, Any]) -> bool:
    for obj in [order_exec.get("safety"), mock.get("raw_response"), router.get("raw_response")]:
        if isinstance(obj, dict) and obj.get("live_order_executed") is True:
            return True
    order_result = router.get("order_result")
    if isinstance(order_result, dict) and isinstance(order_result.get("raw_response"), dict):
        return order_result["raw_response"].get("live_order_executed") is True
    return False


def _expected_side(direction: str) -> Optional[str]:
    d = direction.lower()
    if d in {"long", "buy"}: return "BUY"
    if d in {"short", "sell"}: return "SELL"
    return None


def _price_diff_pct(paper_entry: Optional[float], fill: Optional[float]) -> Optional[float]:
    if paper_entry is None or fill is None or paper_entry <= 0:
        return None
    return round(((fill - paper_entry) / paper_entry) * 100, 6)


def _compact_order(order: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(order, dict): return {}
    metadata = order.get("metadata", {}) if isinstance(order.get("metadata"), dict) else {}
    return {"request_id": order.get("request_id"), "symbol": order.get("symbol"), "side": order.get("side"), "quantity": order.get("quantity"), "price": order.get("price"), "metadata": metadata}

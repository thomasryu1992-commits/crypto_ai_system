from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path


def test_step255_canonical_order_models_and_state_are_pure_support():
    from crypto_ai_system.execution.order_models import create_order_request, validate_order_request
    from crypto_ai_system.execution.order_state import ORDER_STATES, transition

    request = create_order_request("btcusdt", "buy", 0.001, metadata={"source": "unit"})
    assert request["symbol"] == "BTCUSDT"
    assert request["side"] == "BUY"
    assert request["validation"]["valid"] is True
    assert validate_order_request({"symbol": "", "side": "BAD", "order_type": "MARKET", "quantity": 0})["valid"] is False

    assert "CREATED" in ORDER_STATES
    assert transition("CREATED", "VALIDATED") == "VALIDATED"


def test_step255_canonical_mock_exchange_is_local_only():
    from crypto_ai_system.execution.mock_exchange import (
        EXTERNAL_ORDER_SUBMISSION_PERFORMED,
        MOCK_EXCHANGE_MODE,
        NETWORK_CALLS_PERFORMED,
        MockExchangeClient,
        place_mock_order,
    )

    assert MOCK_EXCHANGE_MODE == "LOCAL_TEST_SUPPORT_ONLY"
    assert NETWORK_CALLS_PERFORMED is False
    assert EXTERNAL_ORDER_SUBMISSION_PERFORMED is False

    result = MockExchangeClient().place_order("BTCUSDT", "BUY", 0.001, price=100000)
    assert result["status"] == "MOCK_FILLED"

    helper = place_mock_order({"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.001}, current_price=100000)
    assert helper["status"] == "MOCK_FILLED"
    assert helper["network_calls_performed"] is False
    assert helper["external_order_submission_performed"] is False


def test_step255_exchange_router_is_disabled_review_only_by_default(tmp_path, monkeypatch):
    import crypto_ai_system.execution.exchange_router as exchange_router

    assert exchange_router.EXCHANGE_ROUTER_MODE == "DISABLED_REVIEW_ONLY_ROUTER"
    assert exchange_router.LIVE_TRADING_ALLOWED_BY_THIS_MODULE is False
    assert exchange_router.ADAPTER_ROUTING_ENABLED_BY_THIS_MODULE is False
    assert exchange_router.EXTERNAL_ORDER_SUBMISSION_PERFORMED is False

    monkeypatch.delenv("EXCHANGE_ORDER_ENABLED", raising=False)
    monkeypatch.delenv("LIVE_TRADING_ENABLED", raising=False)
    result = exchange_router.route_order({"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.001}, current_price=100000, storage_dir=tmp_path)
    assert result["status"] == "EXCHANGE_ORDER_DISABLED"
    assert result["exchange_router_mode"] == "DISABLED_REVIEW_ONLY_ROUTER"
    assert result["external_order_submission_performed"] is False

    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    result = exchange_router.route_order({"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.001}, current_price=100000, storage_dir=tmp_path)
    assert result["status"] == "LIVE_TRADING_BLOCKED"
    assert result["live_trading_allowed_by_this_module"] is False
    assert result["external_order_submission_performed"] is False


def test_step255_legacy_imports_reexport_canonical_modules():
    legacy_order_models = importlib.import_module("execution.order_models")
    legacy_order_state = importlib.import_module("execution.order_state")
    legacy_mock_exchange = importlib.import_module("execution.mock_exchange")
    legacy_exchange_router = importlib.import_module("execution.exchange_router")

    assert callable(legacy_order_models.create_order_request)
    assert callable(legacy_order_state.transition)
    assert legacy_mock_exchange.MOCK_EXCHANGE_MODE == "LOCAL_TEST_SUPPORT_ONLY"
    assert legacy_exchange_router.EXCHANGE_ROUTER_MODE == "DISABLED_REVIEW_ONLY_ROUTER"


def test_step255_report_confirms_missing_count_reduced(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "step255_report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/report_step255_execution_support_port.py",
            "--output",
            str(output),
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "EXECUTION_SUPPORT_CANONICAL_PORT_APPLIED"
    assert payload["direct_root_import_finding_count"] == 0
    assert payload["missing_canonical_module_count_after"] <= 6
    assert len(payload["step255_wrapper_modules"]) == 4
    assert payload["port_performed"] is True
    assert payload["wrapper_conversion_performed"] is True
    assert payload["root_package_deletion_performed"] is False
    assert payload["exchange_router_mode"] == "DISABLED_REVIEW_ONLY_ROUTER"
    assert payload["live_trading_allowed"] is False
    assert payload["external_order_submission_performed"] is False

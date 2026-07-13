from __future__ import annotations

from pathlib import Path

from crypto_ai_system.execution.runtime_disabled_flags import (
    DISABLED_RUNTIME_FLAG_PATHS,
    EXECUTION_FLAGS,
    PHASE_STATUS_MARKERS,
)
from crypto_ai_system.ops.operator_dashboard_status import build_operator_dashboard_status


def test_live_guard_does_not_import_binance_secret_values() -> None:
    source = Path("src/crypto_ai_system/execution/live_guard.py").read_text(encoding="utf-8")

    assert "BINANCE_API_KEY" not in source
    assert "BINANCE_API_SECRET" not in source
    assert "missing_exchange_api_credentials" not in source
    assert "secret_metadata_boundary" in source


def test_execution_disabled_flags_are_centralized() -> None:
    assert "ready_for_signed_testnet_execution" in EXECUTION_FLAGS
    assert "live_scaled_execution_enabled" in EXECUTION_FLAGS
    assert ("safety.live_trading_enabled", False) in DISABLED_RUNTIME_FLAG_PATHS
    assert PHASE_STATUS_MARKERS["phase10"].startswith("blocked_until")


def test_operator_dashboard_uses_central_flag_registry_and_phase_markers() -> None:
    status = build_operator_dashboard_status(Path.cwd())

    assert status["central_execution_flag_source"] == "crypto_ai_system.execution.runtime_disabled_flags.EXECUTION_FLAGS"
    assert status["phase_status_markers"]["phase9_2"] == "closed_review_only_no_order_submit"
    assert status["phase_status_markers"]["phase9_3"] == "status_polling_cancel_boundary_no_endpoint_call"
    assert status["phase_status_markers"]["phase10"].startswith("blocked_until")
    assert status["phase_status_markers"]["phase11"].startswith("blocked_until")

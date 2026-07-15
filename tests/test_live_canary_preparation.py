"""Network-free tests for the live canary preparation gate."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.execution.live_canary_preparation import (
    LiveReadOnlyProbe,
    NonLiveHostError,
    build_live_canary_preparation_report,
    evaluate_testnet_session_evidence,
    run_live_readonly_probe,
)


def _session_report(sessions_ok=5, orders_submitted=10, reconcile_rate=1.0):
    return {
        "created_at": "2026-07-15T00:00:00Z",
        "aggregate": {
            "sessions_ok": sessions_ok,
            "orders_submitted": orders_submitted,
            "orders_reconciled": orders_submitted,
            "reconcile_rate": reconcile_rate,
            "avg_slippage_bps": 1.2,
            "avg_latency_ms": 250.0,
        },
    }


# -- gate 1: testnet session evidence ----------------------------------------

def test_missing_report_blocks():
    result = evaluate_testnet_session_evidence(None)
    assert result["passed"] is False
    assert any("signed_testnet_session_report" in b for b in result["blockers"])


def test_too_few_clean_sessions_blocks():
    result = evaluate_testnet_session_evidence(_session_report(sessions_ok=4))
    assert result["passed"] is False
    assert any("clean testnet sessions 4 < required 5" in b for b in result["blockers"])


def test_partial_reconcile_rate_blocks():
    result = evaluate_testnet_session_evidence(_session_report(reconcile_rate=0.9))
    assert result["passed"] is False
    assert any("reconcile_rate" in b for b in result["blockers"])


def test_clean_sessions_pass():
    result = evaluate_testnet_session_evidence(_session_report())
    assert result["passed"] is True, result
    assert result["blockers"] == []
    assert result["sessions_ok"] == 5


# -- gate 2: live read-only probe ---------------------------------------------

RESTRICTIONS = {
    "enableReading": True,
    "enableWithdrawals": False,
    "enableInternalTransfer": False,
    "enableFutures": True,
    "enableSpotAndMarginTrading": False,
    "ipRestrict": True,
}
ACCOUNT = {
    "canTrade": True,
    "canDeposit": True,
    "canWithdraw": False,
    "totalWalletBalance": "100.0",
    "availableBalance": "100.0",
}
EXCHANGE_INFO = {
    "symbols": [
        {
            "symbol": "BTCUSDT",
            "status": "TRADING",
            "filters": [
                {"filterType": "MIN_NOTIONAL", "notional": "100"},
                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
            ],
        }
    ]
}


def _fake_transport(calls=None, restrictions=RESTRICTIONS):
    responses = {
        "/sapi/v1/account/apiRestrictions": restrictions,
        "/fapi/v2/account": ACCOUNT,
        "/fapi/v2/positionRisk": [{"symbol": "BTCUSDT", "positionAmt": "0"}],
        "/fapi/v1/openOrders": [],
        "/fapi/v1/commissionRate": {
            "makerCommissionRate": "0.0002",
            "takerCommissionRate": "0.0005",
        },
        "/fapi/v1/exchangeInfo": EXCHANGE_INFO,
    }

    def transport(method, url, params, headers, timeout):
        if calls is not None:
            calls.append((method, url, dict(params)))
        path = "/" + url.split("/", 3)[-1]
        return 200, responses[path]

    return transport


def _probe(transport):
    return LiveReadOnlyProbe(api_key="k", api_secret="s", transport=transport)


def test_probe_rejects_testnet_and_unknown_hosts():
    with pytest.raises(NonLiveHostError):
        LiveReadOnlyProbe(
            api_key="k", api_secret="s",
            futures_base_url="https://testnet.binancefuture.com",
        )
    with pytest.raises(NonLiveHostError):
        LiveReadOnlyProbe(
            api_key="k", api_secret="s", spot_base_url="https://evil.example.com"
        )


def test_probe_is_get_only_by_construction():
    for forbidden in ("submit_order", "cancel_order", "place_order", "transfer"):
        assert not hasattr(LiveReadOnlyProbe, forbidden)

    calls = []
    summary = run_live_readonly_probe(_probe(_fake_transport(calls)), "BTCUSDT")
    assert summary["ok"] is True
    assert calls, "probe made no calls"
    assert all(method == "GET" for method, _, _ in calls)


def test_probe_summary_extracts_fields():
    summary = run_live_readonly_probe(_probe(_fake_transport()), "BTCUSDT")
    assert summary["key_restrictions"]["enable_withdrawals"] is False
    assert summary["account"]["can_withdraw"] is False
    assert summary["open_position_count"] == 0
    assert summary["open_order_count"] == 0
    assert summary["commission"]["taker"] == "0.0005"
    assert summary["symbol_filters"]["min_notional"] == "100"


def test_probe_redacts_signature_and_never_returns_secret():
    probe = LiveReadOnlyProbe(
        api_key="distinct-key-value",
        api_secret="distinct-secret-value",
        transport=_fake_transport(),
    )
    result = probe.get_account()
    assert result["request"]["signature"] == "***redacted***"
    flat = repr(result)
    assert "distinct-secret-value" not in flat
    assert "distinct-key-value" not in flat


def test_probe_error_collected_not_raised():
    def failing_transport(method, url, params, headers, timeout):
        return 401, {"code": -2015, "msg": "Invalid API-key"}

    summary = run_live_readonly_probe(_probe(failing_transport), "BTCUSDT")
    assert summary["ok"] is False
    assert summary["errors"]


# -- combined report -----------------------------------------------------------

def _ready_inputs():
    evidence = evaluate_testnet_session_evidence(_session_report())
    probe_summary = run_live_readonly_probe(_probe(_fake_transport()), "BTCUSDT")
    return evidence, probe_summary


def test_report_ready_when_all_gates_pass():
    evidence, probe_summary = _ready_inputs()
    report = build_live_canary_preparation_report(
        evidence, probe_summary, probe_attempted=True
    )
    assert report["preparation_ready"] is True, report["blockers"]
    assert report["blockers"] == []


def test_report_order_authority_always_false():
    evidence, probe_summary = _ready_inputs()
    report = build_live_canary_preparation_report(
        evidence, probe_summary, probe_attempted=True
    )
    # Even a fully ready report never grants order authority.
    assert report["live_canary_execution_enabled"] is False
    assert report["live_order_submission_allowed"] is False
    assert report["external_order_submission_performed"] is False


def test_report_blocks_without_probe():
    evidence, _ = _ready_inputs()
    report = build_live_canary_preparation_report(evidence, None, probe_attempted=False)
    assert report["preparation_ready"] is False
    assert any("probe not run" in b for b in report["blockers"])


def test_report_blocks_withdrawal_enabled_key():
    evidence, _ = _ready_inputs()
    unsafe = dict(RESTRICTIONS, enableWithdrawals=True)
    probe_summary = run_live_readonly_probe(
        _probe(_fake_transport(restrictions=unsafe)), "BTCUSDT"
    )
    report = build_live_canary_preparation_report(
        evidence, probe_summary, probe_attempted=True
    )
    assert report["preparation_ready"] is False
    assert any("withdrawals" in b for b in report["blockers"])


def test_report_blocks_failed_probe():
    evidence, _ = _ready_inputs()
    report = build_live_canary_preparation_report(
        evidence, {"ok": False, "errors": ["account: 401"]}, probe_attempted=True
    )
    assert report["preparation_ready"] is False
    assert any("live probe failed" in b for b in report["blockers"])

"""Extended basis probe (venue design V4): read-only dual-feed sampling,
basis stats, fail-soft error handling. Network-free via injected transports."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.config import load_config
from crypto_ai_system.data.extended_basis_probe import (
    REPORT_NAME,
    SAMPLES_LOG_NAME,
    build_basis_report,
    collect_basis_sample,
    run_extended_basis_probe,
)


def _cfg(tmp_path):
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["latest_dir"] = str(tmp_path / "storage" / "latest")
    cfg.settings.setdefault("storage", {})["logs_dir"] = str(tmp_path / "storage" / "logs")
    return cfg


def _transport(binance_bid="100.0", binance_ask="100.2", ext_bid="99.8", ext_ask="100.0"):
    def transport(url, params):
        if "bookTicker" in url:
            return {"symbol": params.get("symbol"), "bidPrice": binance_bid, "askPrice": binance_ask}
        if "/orderbook" in url:
            return {"status": "OK", "data": {"bid": [{"price": ext_bid}], "ask": [{"price": ext_ask}]}}
        raise AssertionError(f"unexpected url {url}")

    return transport


def test_collect_basis_sample_computes_signed_basis():
    sample = collect_basis_sample(
        "BTC", binance_base_url="https://b", extended_base_url="https://e", transport=_transport()
    )
    assert sample["ok"] is True
    assert sample["binance_symbol"] == "BTCUSDT"
    assert sample["extended_market"] == "BTC-USD"
    # binance mid 100.1, extended mid 99.9 -> basis = +0.2/99.9 -> ~+20 bps
    assert abs(sample["basis_bps"] - 20.02002002) < 1e-6
    assert sample["abs_basis_bps"] > 0
    assert sample["extended_spread_bps"] > 0


def test_collect_basis_sample_never_raises_on_venue_error():
    def broken(url, params):
        raise ConnectionError("extended down")

    sample = collect_basis_sample(
        "ETH", binance_base_url="https://b", extended_base_url="https://e", transport=broken
    )
    assert sample["ok"] is False
    assert "ConnectionError" in sample["error"]


def test_report_stats_percentiles():
    samples = [
        {"base_asset": "BTC", "ok": True, "basis_bps": v, "created_at_utc": f"2026-07-21T00:0{i}:00Z"}
        for i, v in enumerate([1.0, -2.0, 3.0, -4.0, 5.0])
    ]
    report = build_basis_report(samples)
    overall = report["overall"]
    assert overall["ok_count"] == 5
    assert overall["max_abs_basis_bps"] == 5.0
    assert overall["p50_abs_basis_bps"] == 3.0
    assert overall["p99_abs_basis_bps"] == 5.0
    assert report["by_asset"]["BTC"]["sample_count"] == 5
    assert report["guard_threshold_applied"] is False


def test_run_probe_appends_and_writes_report(tmp_path):
    cfg = _cfg(tmp_path)
    result = run_extended_basis_probe(
        cfg=cfg, transport=_transport(), enabled=True, symbols=["BTC", "ETH"]
    )
    assert result["enabled"] is True
    assert result["sampled"] == 2 and result["ok_count"] == 2

    log_path = tmp_path / "storage" / "logs" / SAMPLES_LOG_NAME
    assert log_path.exists()
    lines = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2

    report = json.loads((tmp_path / "storage" / "latest" / REPORT_NAME).read_text(encoding="utf-8"))
    assert report["overall"]["ok_count"] == 2
    assert set(report["by_asset"]) == {"BTC", "ETH"}

    # A second run accumulates instead of overwriting the sample log.
    run_extended_basis_probe(cfg=cfg, transport=_transport(), enabled=True, symbols=["BTC"])
    lines = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 3


def test_run_probe_disabled_is_a_noop(tmp_path):
    cfg = _cfg(tmp_path)
    result = run_extended_basis_probe(cfg=cfg, enabled=False)
    assert result == {"enabled": False, "skipped": True}
    assert not (tmp_path / "storage" / "logs" / SAMPLES_LOG_NAME).exists()


def test_run_probe_short_circuits_when_extended_unreachable(tmp_path):
    cfg = _cfg(tmp_path)
    calls = {"orderbook": 0}

    def transport(url, params):
        if "bookTicker" in url:
            return {"bidPrice": "100.0", "askPrice": "100.2"}
        calls["orderbook"] += 1
        raise ConnectionError("extended unreachable")

    result = run_extended_basis_probe(
        cfg=cfg, transport=transport, enabled=True, symbols=["BTC", "ETH", "SOL"]
    )
    assert result["ok_count"] == 0
    # Only the first symbol pays the venue timeout; the rest short-circuit.
    assert calls["orderbook"] == 1
    log_path = tmp_path / "storage" / "logs" / SAMPLES_LOG_NAME
    lines = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 3
    assert lines[1]["error"] == "venue_unreachable_short_circuit"


def test_torn_tail_line_does_not_kill_history(tmp_path):
    cfg = _cfg(tmp_path)
    run_extended_basis_probe(cfg=cfg, transport=_transport(), enabled=True, symbols=["BTC"])
    log_path = tmp_path / "storage" / "logs" / SAMPLES_LOG_NAME
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write('{"torn": ')
    result = run_extended_basis_probe(cfg=cfg, transport=_transport(), enabled=True, symbols=["BTC"])
    assert result["ok_count"] == 1
    report = json.loads((tmp_path / "storage" / "latest" / REPORT_NAME).read_text(encoding="utf-8"))
    assert report["overall"]["ok_count"] == 2

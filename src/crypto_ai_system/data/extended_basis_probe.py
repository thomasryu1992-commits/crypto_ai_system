"""Extended (USDC venue) read-only basis probe.

Design: docs/architecture/design_venue_cost_calibration_and_extended.md (V4).
Collects (Binance USDT mid, Extended USD/USDC mid) pairs per symbol, appends
them to a sample log, and rebuilds a basis-statistics report. The V3 pre-order
basis guard's threshold will be set from these measurements, not guessed.

Strictly read-only: public GET endpoints, no credentials, no order authority.
Every failure is recorded in the sample (or short-circuits the venue for the
rest of the run) and never raises out of ``run_extended_basis_probe`` —
the probe must never cost a trading cycle.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping

from core.json_io import atomic_write_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.utils.audit import utc_now_canonical

VENUE_BASIS_REPORT_VERSION = "extended_basis_probe.v1"
SAMPLES_LOG_NAME = "venue_basis_samples.jsonl"
REPORT_NAME = "venue_basis_report.json"

DEFAULT_TIMEOUT_SECONDS = 3.0
#: Reading the whole sample log stays cheap for months at the 15-min cadence
#: (5 symbols -> ~500 lines/day); the cap only guards a runaway file.
MAX_SAMPLE_LINES = 100_000

#: transport(url, params) -> parsed JSON body. Injected in tests.
Transport = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]


def _requests_transport(url: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
    import requests

    response = requests.get(
        url,
        params=dict(params),
        timeout=DEFAULT_TIMEOUT_SECONDS,
        headers={"User-Agent": "crypto-ai-system-basis-probe/1.0"},
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, Mapping) else {}


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def fetch_binance_mid(symbol: str, base_url: str, transport: Transport) -> float:
    body = transport(f"{base_url.rstrip('/')}/fapi/v1/ticker/bookTicker", {"symbol": symbol})
    bid = _float(body.get("bidPrice"))
    ask = _float(body.get("askPrice"))
    if not bid or not ask or bid <= 0 or ask <= 0:
        raise ValueError(f"binance bookTicker missing bid/ask for {symbol}")
    return (bid + ask) / 2.0


def fetch_extended_mid(market: str, base_url: str, transport: Transport) -> tuple[float, float | None]:
    """Extended orderbook mid + spread (bps). Payload envelope is {status, data}."""
    body = transport(f"{base_url.rstrip('/')}/info/markets/{market}/orderbook", {})
    data = body.get("data", body)
    if not isinstance(data, Mapping):
        raise ValueError(f"extended orderbook malformed for {market}")
    bids = data.get("bid") or data.get("bids") or []
    asks = data.get("ask") or data.get("asks") or []
    bid = _float(bids[0].get("price")) if bids else None
    ask = _float(asks[0].get("price")) if asks else None
    if not bid or not ask or bid <= 0 or ask <= 0:
        raise ValueError(f"extended orderbook missing bid/ask for {market}")
    mid = (bid + ask) / 2.0
    spread_bps = (ask - bid) / mid * 10_000.0
    return mid, round(spread_bps, 8)


def collect_basis_sample(
    base_asset: str,
    *,
    binance_base_url: str,
    extended_base_url: str,
    transport: Transport,
) -> dict[str, Any]:
    """One (Binance mid, Extended mid) pair for one asset. Never raises."""
    binance_symbol = f"{base_asset}USDT"
    extended_market = f"{base_asset}-USD"
    sample: dict[str, Any] = {
        "created_at_utc": utc_now_canonical(),
        "base_asset": base_asset,
        "binance_symbol": binance_symbol,
        "extended_market": extended_market,
        "ok": False,
    }
    try:
        binance_mid = fetch_binance_mid(binance_symbol, binance_base_url, transport)
        extended_mid, extended_spread_bps = fetch_extended_mid(extended_market, extended_base_url, transport)
    except Exception as exc:  # noqa: BLE001 - recorded, never propagated
        sample["error"] = repr(exc)[:300]
        return sample
    basis_bps = (binance_mid - extended_mid) / extended_mid * 10_000.0
    sample.update(
        ok=True,
        binance_mid=round(binance_mid, 8),
        extended_mid=round(extended_mid, 8),
        basis_bps=round(basis_bps, 8),
        abs_basis_bps=round(abs(basis_bps), 8),
        extended_spread_bps=extended_spread_bps,
    )
    return sample


def _percentile(sorted_values: list[float], q: float) -> float:
    """Nearest-rank percentile; 0.0 on an empty list."""
    if not sorted_values:
        return 0.0
    rank = max(1, math.ceil(q / 100.0 * len(sorted_values)))
    return sorted_values[min(rank, len(sorted_values)) - 1]


def _stats(samples: list[Mapping[str, Any]]) -> dict[str, Any]:
    ok_rows = [s for s in samples if s.get("ok") is True]
    signed = [float(s["basis_bps"]) for s in ok_rows if s.get("basis_bps") is not None]
    abs_sorted = sorted(abs(v) for v in signed)
    mean = sum(signed) / len(signed) if signed else 0.0
    variance = sum((v - mean) ** 2 for v in signed) / len(signed) if signed else 0.0
    return {
        "sample_count": len(samples),
        "ok_count": len(ok_rows),
        "error_count": len(samples) - len(ok_rows),
        "mean_basis_bps": round(mean, 8),
        "std_basis_bps": round(math.sqrt(variance), 8),
        "p50_abs_basis_bps": round(_percentile(abs_sorted, 50.0), 8),
        "p95_abs_basis_bps": round(_percentile(abs_sorted, 95.0), 8),
        "p99_abs_basis_bps": round(_percentile(abs_sorted, 99.0), 8),
        "max_abs_basis_bps": round(abs_sorted[-1], 8) if abs_sorted else 0.0,
        "first_created_at_utc": samples[0].get("created_at_utc") if samples else None,
        "last_created_at_utc": samples[-1].get("created_at_utc") if samples else None,
        "last_basis_bps": signed[-1] if signed else None,
    }


def build_basis_report(samples: list[Mapping[str, Any]]) -> dict[str, Any]:
    by_asset: dict[str, list[Mapping[str, Any]]] = {}
    for sample in samples:
        by_asset.setdefault(str(sample.get("base_asset") or "unknown"), []).append(sample)
    return {
        "venue_basis_report_version": VENUE_BASIS_REPORT_VERSION,
        "created_at_utc": utc_now_canonical(),
        "reference_venue": "binance_usdt_futures",
        "measured_venue": "extended_usd_perp",
        "overall": _stats(samples),
        "by_asset": {asset: _stats(rows) for asset, rows in sorted(by_asset.items())},
        # Guard wiring happens in V3, once the operator reviews the measured
        # distribution; the probe itself never gates anything.
        "guard_threshold_applied": False,
    }


def _latest_path(cfg: AppConfig, name: str) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    base = Path(raw)
    if not base.is_absolute():
        base = cfg.root / base
    base.mkdir(parents=True, exist_ok=True)
    return base / name


def _samples_log_path(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.logs_dir", "storage/logs")
    base = Path(raw)
    if not base.is_absolute():
        base = cfg.root / base
    base.mkdir(parents=True, exist_ok=True)
    return base / SAMPLES_LOG_NAME


def _append_samples(path: Path, samples: list[Mapping[str, Any]]) -> None:
    # A crash can leave a torn tail line without a newline; appending directly
    # onto it would corrupt the NEXT sample too. Terminate the tail first.
    needs_leading_newline = False
    if path.exists() and path.stat().st_size > 0:
        with path.open("rb") as handle:
            handle.seek(-1, 2)
            needs_leading_newline = handle.read(1) != b"\n"
    with path.open("a", encoding="utf-8") as handle:
        if needs_leading_newline:
            handle.write("\n")
        for sample in samples:
            handle.write(json.dumps(dict(sample), ensure_ascii=True) + "\n")


def _load_samples(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue  # a torn tail line must not kill the whole history
            if isinstance(row, dict):
                rows.append(row)
    return rows[-MAX_SAMPLE_LINES:]


def probe_symbols() -> list[str]:
    import config.settings as settings

    raw = str(getattr(settings, "EXTENDED_BASIS_PROBE_SYMBOLS", "BTC,ETH"))
    return [token.strip().upper() for token in raw.split(",") if token.strip()]


def run_extended_basis_probe(
    *,
    cfg: AppConfig | None = None,
    transport: Transport | None = None,
    enabled: bool | None = None,
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    """Sample every probe symbol once, append, and rebuild the report.

    One venue-level short circuit: if Extended is unreachable for the first
    symbol, the remaining symbols are recorded as skipped instead of eating
    a timeout each — the probe's worst case must stay far below a cycle.
    """
    import config.settings as settings

    if enabled is None:
        enabled = bool(getattr(settings, "EXTENDED_BASIS_PROBE_ENABLED", False))
    if not enabled:
        return {"enabled": False, "skipped": True}

    cfg = cfg or load_config(".")
    transport = transport or _requests_transport
    binance_base = str(getattr(settings, "BINANCE_FUTURES_PUBLIC_BASE_URL", "https://fapi.binance.com"))
    extended_base = str(
        getattr(settings, "EXTENDED_MAINNET_PUBLIC_BASE_URL", "https://api.starknet.extended.exchange/api/v1")
    )
    assets = symbols if symbols is not None else probe_symbols()

    samples: list[dict[str, Any]] = []
    venue_down = False
    for asset in assets:
        if venue_down:
            samples.append({
                "created_at_utc": utc_now_canonical(),
                "base_asset": asset,
                "ok": False,
                "error": "venue_unreachable_short_circuit",
            })
            continue
        sample = collect_basis_sample(
            asset,
            binance_base_url=binance_base,
            extended_base_url=extended_base,
            transport=transport,
        )
        samples.append(sample)
        if sample.get("ok") is not True and "extended" in str(sample.get("error", "")).lower():
            venue_down = True

    log_path = _samples_log_path(cfg)
    _append_samples(log_path, samples)
    report = build_basis_report(_load_samples(log_path))
    atomic_write_json(_latest_path(cfg, REPORT_NAME), report)
    return {
        "enabled": True,
        "sampled": len(samples),
        "ok_count": sum(1 for s in samples if s.get("ok") is True),
        "report_path": str(_latest_path(cfg, REPORT_NAME)),
        "overall_p95_abs_basis_bps": report["overall"]["p95_abs_basis_bps"],
    }

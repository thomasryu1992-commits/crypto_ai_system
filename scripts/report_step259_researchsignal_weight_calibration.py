from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.common import bootstrap

ROOT = bootstrap()

from crypto_ai_system.config import load_config
from crypto_ai_system.research.research_signal_calibration import (
    STEP259_CALIBRATION_VERSION,
    compare_weight_profiles,
)


def _synthetic_calibration_matrix(rows: int = 72) -> pd.DataFrame:
    timestamps = pd.date_range("2026-06-01 00:00:00+00:00", periods=rows, freq="h")
    data: list[dict[str, Any]] = []
    for i, ts in enumerate(timestamps):
        phase = i % 12
        bullish = phase in {0, 1, 2, 3, 4}
        risk_off = phase in {8, 9, 10}
        reduced = phase in {6, 7}
        close = 100_000 + i * (60 if bullish else -25) + (phase * 20)
        if bullish:
            ma20 = close - 3500
            ma50 = close - 6200
            rsi = 76
            mtf = 0.80
        else:
            ma20 = close + 2200
            ma50 = close + 4300
            rsi = 34
            mtf = -0.65
        if risk_off:
            exchange_flow = -0.82
            etf_flow = -0.90
            stable = -0.88
        elif reduced:
            exchange_flow = -0.50
            etf_flow = -0.50
            stable = -0.20
        else:
            exchange_flow = 0.72 if bullish else 0.05
            etf_flow = 0.74 if bullish else 0.02
            stable = 0.68 if bullish else 0.05
        data.append({
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S+00:00"),
            "symbol": "BTC-PERP",
            "timeframe": "PT1H",
            "exchange_market": "BTC-USD",
            "data_source": "extended",
            "source": "extended",
            "close": close,
            "ma20": ma20,
            "ma50": ma50,
            "rsi": rsi,
            "adx": 34 if bullish else 24,
            "funding_rate": 0.00012,
            "funding_zscore": 0.15,
            "oi_change_pct": 0.018 if bullish else -0.003,
            "oi_change_4h_pct": 0.035 if bullish else -0.010,
            "atr_pct_of_price": 0.012 if not risk_off else 0.030,
            "spread_bps": 2 if not risk_off else 5,
            "mark_index_basis_bps": 12 if bullish else -2,
            "liquidation_imbalance": 0.28 if bullish else -0.10,
            "mtf_alignment_score": mtf,
            "mtf_bias": "BULLISH" if bullish else "BEARISH",
            "market_regime": "TREND" if bullish else "RANGE",
            "data_quality_status": "OK",
            "binance_derivatives_score": 0.58 if bullish else -0.20,
            "exchange_flow_score": exchange_flow,
            "etf_flow_score": etf_flow,
            "stablecoin_liquidity_score": stable,
            "btc_exchange_netflow": -1200.0 if exchange_flow > 0 else 1800.0,
            "exchange_netflow_zscore_30d": -1.4 if exchange_flow > 0 else 1.8,
            "total_flow_usd_m": 260.0 if etf_flow > 0 else -420.0,
            "etf_flow_5d_sum": 900.0 if etf_flow > 0 else -1100.0,
            "stablecoin_total_mcap_7d_change": 0.010 if stable > 0 else -0.012,
            "feature_matrix_mode": "backtest",
            "feature_matrix_version": "step259_weight_calibration_permission_distribution_matrix",
            "optional_extra_data_available": True,
        })
    return pd.DataFrame(data)


def _load_matrix(root: Path, matrix_path: str | None) -> tuple[pd.DataFrame, str]:
    candidates: list[Path] = []
    if matrix_path:
        p = Path(matrix_path)
        candidates.append(p if p.is_absolute() else root / p)
    candidates.extend([
        root / "storage" / "features" / "research_feature_matrix_backtest.csv",
        root / "storage" / "features" / "research_feature_matrix_live.csv",
        root / "storage" / "features" / "research_feature_matrix.csv",
    ])
    for path in candidates:
        if path.exists() and path.is_file():
            try:
                frame = pd.read_csv(path)
                if not frame.empty:
                    return frame, str(path.relative_to(root) if path.is_relative_to(root) else path)
            except Exception:
                continue
    return _synthetic_calibration_matrix(), "synthetic_step259_calibration_matrix"


def build_report(root: Path, matrix_path: str | None = None, max_rows: int | None = None) -> dict[str, Any]:
    cfg = load_config(root)
    matrix, source = _load_matrix(root, matrix_path)
    comparison = compare_weight_profiles(matrix, cfg, max_rows=max_rows)
    report = {
        "step": 259,
        "status": "completed",
        "scope": "researchsignal_v2_weight_calibration_permission_distribution_and_telegram_extra_data_summary",
        "version": STEP259_CALIBRATION_VERSION,
        "matrix_source": source,
        "matrix_rows_available": int(len(matrix)),
        "comparison": comparison,
        "telegram_extra_data_summary_connected": "Extra Data Summary" in (root / "notify" / "telegram_summary_builder.py").read_text(encoding="utf-8")
        and "Extra Data Summary" in (root / "src" / "crypto_ai_system" / "notifier" / "telegram.py").read_text(encoding="utf-8"),
        "safety_boundaries": {
            "live_trading_allowed": False,
            "order_routing_enabled": False,
            "external_order_submission_performed": False,
            "canonical_live_execution_port_performed": False,
            "canonical_testnet_execution_port_performed": False,
            "root_package_deletion_performed": False,
            "root_package_deletion_deferred": True,
            "missing_canonical_module_count": 2,
        },
        "next_step": {
            "name": "Step260",
            "goal": "Run calibration against real stored Feature Store backtest matrices and add acceptance thresholds before selecting a production score-weight profile.",
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step259 ResearchSignal weight calibration report.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--matrix", default=None, help="Optional Feature Store CSV matrix path")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional replay row cap")
    parser.add_argument("--output", default="data/reports/step259_researchsignal_weight_calibration_report.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    report = build_report(root, matrix_path=args.matrix, max_rows=args.max_rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(output),
        "profiles_compared": report["comparison"]["profiles_compared"],
        "rows_evaluated": report["comparison"]["rows_evaluated"],
        "telegram_extra_data_summary_connected": report["telegram_extra_data_summary_connected"],
        "external_order_submission_performed": report["safety_boundaries"]["external_order_submission_performed"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_python(args: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env['PYTHONPATH'] = 'src:.'
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def test_canonical_and_root_limited_live_readiness_imports_work() -> None:
    canonical = _run_python(['-c', 'from crypto_ai_system.reports.limited_live_readiness import build_limited_live_readiness_report; print(build_limited_live_readiness_report.__name__)'])
    assert canonical.returncode == 0, canonical.stderr
    assert 'build_limited_live_readiness_report' in canonical.stdout

    wrapper = _run_python(['-c', 'from reports.limited_live_readiness import build_limited_live_readiness_report; print(build_limited_live_readiness_report.__name__)'])
    assert wrapper.returncode == 0, wrapper.stderr
    assert 'build_limited_live_readiness_report' in wrapper.stdout


def test_run_full_cycle_smoke_preserves_safety_flags() -> None:
    completed = _run_python(['run_full_cycle.py'])
    assert completed.returncode == 0, completed.stderr
    assert 'Full cycle completed.' in completed.stdout

    order_path = ROOT / 'storage' / 'latest' / 'latest_order_result.json'
    limited_live_path = ROOT / 'storage' / 'latest' / 'limited_live_readiness_report.json'
    assert order_path.exists()
    assert limited_live_path.exists()

    order = json.loads(order_path.read_text())
    limited_live = json.loads(limited_live_path.read_text())

    assert order.get('external_order_submission_performed') is False
    assert limited_live.get('safety', {}).get('external_order_submission_performed') is False
    assert limited_live.get('safety', {}).get('live_trading_allowed') is False
    assert limited_live.get('safety', {}).get('testnet_order_submission_allowed') is False
    assert limited_live.get('safety', {}).get('real_telegram_send_allowed') is False


def test_run_operational_dry_run_smoke_passes() -> None:
    completed = _run_python(['run_operational_dry_run.py'])
    assert completed.returncode == 0, completed.stderr
    assert 'Operational dry run Step150: PASSED' in completed.stdout

    result_path = ROOT / 'storage' / 'latest' / 'operational_dry_run_result.json'
    result = json.loads(result_path.read_text())
    assert result.get('status') == 'PASSED'
    assert result.get('order_status') in {'NO_ORDER', 'SHADOW_ONLY', 'TESTNET_REQUIRED_BEFORE_LIVE'}

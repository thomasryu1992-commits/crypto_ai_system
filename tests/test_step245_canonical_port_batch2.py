from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _audit_row(risk_level: str, status: str) -> dict:
    return {
        "risk_level": risk_level,
        "paper_status": status,
        "position_opened": status == "POSITION_OPENED",
        "signal": "LONG",
    }


def test_step245_canonical_paper_report_builds_risk_buckets(tmp_path):
    from crypto_ai_system.trading.paper_report import (
        build_and_save_paper_risk_level_report,
        build_paper_risk_level_report_from_rows,
    )

    rows = [
        _audit_row("normal", "POSITION_OPENED"),
        _audit_row("reduced", "POSITION_OPENED"),
        _audit_row("blocked", "BLOCKED_BY_PERMISSION_GATE"),
    ]
    trades = [
        {"status": "CLOSED", "result": "WIN", "risk_level": "reduced", "pnl_r": 2.0},
        {"status": "CLOSED", "result": "LOSS", "risk_level": "normal", "pnl_r": -1.0},
    ]
    report = build_paper_risk_level_report_from_rows(rows, trades)
    assert report["total_audit_records"] == 3
    assert report["total_position_opened"] == 2
    assert report["total_blocked_by_permission_gate"] == 1
    assert report["by_risk_level"]["reduced"]["win_count"] == 1

    audit_path = tmp_path / "audit.jsonl"
    latest_path = tmp_path / "latest.json"
    trades_path = tmp_path / "trades.json"
    output_path = tmp_path / "risk_report.json"
    audit_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    latest_path.write_text(json.dumps(rows[-1]), encoding="utf-8")
    trades_path.write_text(json.dumps(trades), encoding="utf-8")
    saved = build_and_save_paper_risk_level_report(
        audit_path=audit_path,
        trades_path=trades_path,
        output_path=output_path,
        latest_audit_path=latest_path,
    )
    assert output_path.exists()
    assert saved["latest_permission_gate"]["risk_level"] == "blocked"


def test_step245_batch2_report_confirms_ported_module_removed_from_plan(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "step245_report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/report_step245_canonical_port_batch2.py",
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
    assert payload["status"] == "BATCH2_CANONICAL_PORT_APPLIED"
    assert payload["direct_root_import_finding_count"] <= 21
    assert payload["remaining_root_only_input_count"] <= 21
    assert payload["expected_ported_modules_removed_from_plan"] is True
    assert payload["ported_modules_still_in_port_plan"] == []
    assert payload["port_performed"] is True
    assert payload["import_rewrite_performed"] is True
    assert payload["wrapper_conversion_performed"] is False
    assert payload["live_trading_allowed"] is False

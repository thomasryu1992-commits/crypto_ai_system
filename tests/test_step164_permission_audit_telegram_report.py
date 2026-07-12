from __future__ import annotations

import json
from pathlib import Path

from notify.telegram_summary_builder import build_daily_telegram_message
from crypto_ai_system.trading.permission_audit import build_permission_gate_audit_record, log_permission_gate_audit
from crypto_ai_system.trading.paper_report import build_paper_risk_level_report_from_rows, build_and_save_paper_risk_level_report


def _signal(risk_level: str = 'reduced') -> dict:
    return {
        'signal': 'LONG',
        'confidence': 72,
        'permission_gate_applied': True,
        'allow_long': True,
        'allow_short': False,
        'allow_new_position': risk_level != 'blocked',
        'risk_level': risk_level,
        'position_size_multiplier': 0.5 if risk_level == 'reduced' else (0.0 if risk_level == 'blocked' else 1.0),
        'risk_warnings': ['FUNDING_ELEVATED_REDUCE_SIZE'] if risk_level == 'reduced' else [],
        'block_reasons': ['RESEARCH_SIGNAL_RISK_LEVEL_BLOCKED'] if risk_level == 'blocked' else [],
        'research_signal_id': f'sig_{risk_level}',
    }


def test_step164_permission_gate_audit_record_reduced() -> None:
    record = build_permission_gate_audit_record(
        _signal('reduced'),
        {'status': 'POSITION_OPENED', 'active_position': {'direction': 'LONG', 'entry_price': 100000}},
        {'symbol': 'BTCUSDT', 'last_close': 100000},
        created_at='2026-06-25T00:00:00+00:00',
    )
    assert record['risk_level'] == 'reduced'
    assert record['position_opened'] is True
    assert record['position_size_multiplier'] == 0.5
    assert 'FUNDING_ELEVATED_REDUCE_SIZE' in record['risk_warnings']


def test_step164_permission_gate_audit_writes_jsonl_and_latest(tmp_path: Path) -> None:
    audit_path = tmp_path / 'permission_gate_audit.jsonl'
    latest_path = tmp_path / 'permission_gate_audit_latest.json'
    record = log_permission_gate_audit(
        _signal('blocked'),
        {'status': 'BLOCKED_BY_PERMISSION_GATE', 'reasons': ['blocked']},
        {'symbol': 'BTCUSDT'},
        audit_path=audit_path,
        latest_path=latest_path,
    )
    assert audit_path.exists()
    assert latest_path.exists()
    assert json.loads(audit_path.read_text().strip())['risk_level'] == 'blocked'
    assert json.loads(latest_path.read_text())['paper_status'] == 'BLOCKED_BY_PERMISSION_GATE'
    assert record['position_opened'] is False


def test_step164_paper_risk_level_report_from_audit_rows() -> None:
    rows = [
        build_permission_gate_audit_record(_signal('normal'), {'status': 'POSITION_OPENED'}, {'symbol': 'BTCUSDT'}),
        build_permission_gate_audit_record(_signal('reduced'), {'status': 'POSITION_OPENED'}, {'symbol': 'BTCUSDT'}),
        build_permission_gate_audit_record(_signal('blocked'), {'status': 'BLOCKED_BY_PERMISSION_GATE'}, {'symbol': 'BTCUSDT'}),
    ]
    trades = [
        {'status': 'CLOSED', 'result': 'WIN', 'risk_level': 'reduced', 'pnl_r': 2.0},
        {'status': 'CLOSED', 'result': 'LOSS', 'risk_level': 'normal', 'pnl_r': -1.0},
    ]
    report = build_paper_risk_level_report_from_rows(rows, trades)
    assert report['total_audit_records'] == 3
    assert report['total_position_opened'] == 2
    assert report['total_blocked_by_permission_gate'] == 1
    assert report['by_risk_level']['reduced']['win_count'] == 1
    assert report['by_risk_level']['normal']['loss_count'] == 1


def test_step164_paper_risk_level_report_writes_file(tmp_path: Path) -> None:
    audit_path = tmp_path / 'audit.jsonl'
    latest_path = tmp_path / 'latest.json'
    trades_path = tmp_path / 'trades.json'
    output_path = tmp_path / 'paper_risk_level_report.json'
    log_permission_gate_audit(_signal('reduced'), {'status': 'POSITION_OPENED'}, {'symbol': 'BTCUSDT'}, audit_path=audit_path, latest_path=latest_path)
    trades_path.write_text('[]', encoding='utf-8')
    report = build_and_save_paper_risk_level_report(audit_path=audit_path, trades_path=trades_path, output_path=output_path, latest_audit_path=latest_path)
    assert output_path.exists()
    assert report['by_risk_level']['reduced']['position_opened_count'] == 1


def test_step164_telegram_message_includes_permission_and_report() -> None:
    audit = build_permission_gate_audit_record(_signal('reduced'), {'status': 'POSITION_OPENED'}, {'symbol': 'BTCUSDT'})
    report = build_paper_risk_level_report_from_rows([audit], [])
    message = build_daily_telegram_message(
        daily_report={'report_date': '2026-06-25', 'current_price': 100000, 'market_bias': 'neutral', 'research_score': 55},
        research_cycle_result={},
        paper_report={'mode': 'paper', 'position_opened': True, 'signal': {'side': 'LONG', 'confidence': 0.72}},
        scheduler_health={},
        markdown_report_result={},
        signal_quality_report={},
        signal_calibration_advice={},
        trading_cycle_result={'permission_gate': audit},
        permission_gate_audit=audit,
        paper_risk_level_report=report,
    )
    assert '[Trade Permission]' in message
    assert 'Risk Level: reduced' in message
    assert '[Paper Risk-Level Report]' in message
    assert 'Reduced Attempts: 1' in message

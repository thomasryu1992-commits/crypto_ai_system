from scripts.common import bootstrap
bootstrap()

from pathlib import Path
from tempfile import TemporaryDirectory

from crypto_ai_system.trading.permission_audit import log_permission_gate_audit
from crypto_ai_system.trading.paper_report import build_and_save_paper_risk_level_report
from notify.telegram_summary_builder import build_daily_telegram_message


if __name__ == "__main__":
    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        audit_path = tmp_path / "permission_gate_audit.jsonl"
        latest_path = tmp_path / "permission_gate_audit_latest.json"
        report_path = tmp_path / "paper_risk_level_report.json"
        signal = {
            "signal": "LONG",
            "confidence": 72,
            "permission_gate_applied": True,
            "allow_long": True,
            "allow_short": False,
            "allow_new_position": True,
            "risk_level": "reduced",
            "position_size_multiplier": 0.5,
            "risk_warnings": ["FUNDING_ELEVATED_REDUCE_SIZE"],
            "research_signal_id": "step164_validation_signal",
        }
        paper = {"status": "POSITION_OPENED", "active_position": {"direction": "LONG", "entry_price": 100000}}
        snapshot = {"symbol": "BTCUSDT", "last_close": 100000}
        record = log_permission_gate_audit(signal, paper, snapshot, audit_path=audit_path, latest_path=latest_path)
        report = build_and_save_paper_risk_level_report(audit_path=audit_path, output_path=report_path, latest_audit_path=latest_path)
        message = build_daily_telegram_message(
            daily_report={"report_date": "2026-06-25", "current_price": 100000, "market_bias": "neutral", "research_score": 50},
            research_cycle_result={},
            paper_report={"mode": "paper", "position_opened": True, "signal": {"side": "LONG", "confidence": 0.72}},
            scheduler_health={},
            markdown_report_result={},
            signal_quality_report={},
            signal_calibration_advice={},
            trading_cycle_result={"permission_gate": record},
            permission_gate_audit=record,
            paper_risk_level_report=report,
        )
        assert "[Trade Permission]" in message
        assert "Risk Level: reduced" in message
        assert report["by_risk_level"]["reduced"]["position_opened_count"] == 1
        print("STEP164_PERMISSION_TELEGRAM_VALIDATION_OK")
        print("risk_level:", record.get("risk_level"))
        print("paper_risk_report_status:", report.get("status"))

from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.paper_execution_engine_v2 import simulate_paper_execution
from crypto_ai_system.execution.paper_reconciliation_v2 import reconcile_paper_execution_record
from crypto_ai_system.feedback.outcome_analytics_v2 import analyze_and_persist_paper_outcome, analyze_paper_reconciliation_outcome
from crypto_ai_system.feedback.performance_report_generator import (
    PERFORMANCE_REPORT_REGISTRY_NAME,
    PERFORMANCE_REPORT_VERSION,
    RECOMMEND_CREATE_CANDIDATE_PROFILE_DRAFT,
    RECOMMEND_EXPAND_TEST_COVERAGE,
    RECOMMEND_REPEAT_IN_PAPER,
    STATUS_PERFORMANCE_REPORT_BLOCKED_NO_OUTCOMES,
    STATUS_PERFORMANCE_REPORT_BLOCKED_UNSAFE_SIDE_EFFECT,
    STATUS_PERFORMANCE_REPORT_RECORDED,
    STATUS_PERFORMANCE_REPORT_REVIEW_ONLY_INSUFFICIENT_SAMPLE,
    build_performance_report,
    build_performance_report_registry_record,
    generate_and_persist_performance_report,
    run_performance_report_latest,
)
from crypto_ai_system.registry.base_registry import registry_path


def _cfg(tmp_path: Path):
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["registry_dir"] = str(tmp_path / "storage" / "registries")
    cfg.settings.setdefault("storage", {})["latest_dir"] = str(tmp_path / "storage" / "latest")
    return cfg


def _intent(order_id: str = "order_intent_step297", **overrides):
    payload = {
        "status": "ORDER_INTENT_CREATED",
        "state": "CREATED",
        "decision_stage": "paper",
        "execution_stage": "paper",
        "order_intent_created": True,
        "order_intent_id": order_id,
        "decision_id": f"decision_{order_id}",
        "risk_gate_id": f"risk_gate_{order_id}",
        "research_signal_id": "signal_step297",
        "profile_id": "profile_step297",
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "side": "BUY",
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "take_profit": 115.0,
        "quantity": 0.1,
        "order_notional_usdt": 10.0,
        "permission_result": "allow_long",
        "adapter_called": False,
        "live_order_executed": False,
        "external_order_submission_performed": False,
    }
    payload.update(overrides)
    return payload


def _risk_gate(intent: dict):
    return {
        "approved": True,
        "status": "PASS_PAPER",
        "risk_gate_id": intent["risk_gate_id"],
        "decision_id": intent["decision_id"],
        "research_signal_id": intent["research_signal_id"],
        "profile_id": intent["profile_id"],
    }


def _outcome(order_id: str, result_r: float, *, regime: str = "trend", direction: str = "LONG", **overrides):
    intent = _intent(order_id, direction=direction, side="BUY" if direction == "LONG" else "SELL", **overrides)
    record = simulate_paper_execution(
        intent,
        risk_gate_report=_risk_gate(intent),
        execution_config={"fee_bps": 4.0, "slippage_bps": 2.0, "fill_latency_ms": 100.0},
    ).to_dict()
    rec = reconcile_paper_execution_record(record)
    return analyze_paper_reconciliation_outcome(rec, outcome_context={"result_R": result_r, "regime": regime, "api_error_rate": 0.0})


def test_step297_builds_report_from_multiple_outcomes_and_keeps_review_only() -> None:
    rows = [_outcome("order_a", 2.0), _outcome("order_b", -0.5), _outcome("order_c", 1.0, regime="range")]
    report = build_performance_report(rows, min_sample_size=3)

    assert report["performance_report_version"] == PERFORMANCE_REPORT_VERSION
    assert report["status"] == STATUS_PERFORMANCE_REPORT_RECORDED
    assert report["recommendation"] == RECOMMEND_CREATE_CANDIDATE_PROFILE_DRAFT
    assert report["source_outcome_count"] == 3
    assert report["sample_size"] == 3
    assert report["expectancy"] == 0.83333333
    assert report["average_R"] == 0.83333333
    assert report["max_drawdown"] == 0.5
    assert report["r_distribution"]["gte_2R"] == 1
    assert report["r_distribution"]["minus_1R_to_0R"] == 1
    assert set(report["summary_by_regime"]) == {"range", "trend"}
    assert report["candidate_profile_created"] is False
    assert report["approval_packet_created"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["auto_promotion_allowed"] is False
    assert report["live_trading_allowed_by_this_module"] is False
    assert report["performance_report_sha256"]


def test_step297_blocks_no_outcomes() -> None:
    report = build_performance_report([], min_sample_size=3)

    assert report["status"] == STATUS_PERFORMANCE_REPORT_BLOCKED_NO_OUTCOMES
    assert report["recommendation"] == RECOMMEND_EXPAND_TEST_COVERAGE
    assert "NO_OUTCOME_RECORDS" in report["failure_modes"]
    assert report["live_candidate_eligible"] is False


def test_step297_insufficient_sample_is_review_only_repeat_in_paper() -> None:
    report = build_performance_report([_outcome("order_a", 2.0)], min_sample_size=3)

    assert report["status"] == STATUS_PERFORMANCE_REPORT_REVIEW_ONLY_INSUFFICIENT_SAMPLE
    assert report["recommendation"] == RECOMMEND_REPEAT_IN_PAPER
    assert "INSUFFICIENT_CLOSED_OUTCOME_SAMPLE" in report["blockers"]
    assert report["live_candidate_eligible"] is False


def test_step297_blocks_unsafe_side_effect_flags() -> None:
    row = _outcome("order_a", 1.0)
    row["runtime_settings_mutated"] = True
    report = build_performance_report([row], min_sample_size=1)

    assert report["status"] == STATUS_PERFORMANCE_REPORT_BLOCKED_UNSAFE_SIDE_EFFECT
    assert report["recommendation"] == RECOMMEND_EXPAND_TEST_COVERAGE
    assert "UNSAFE_SIDE_EFFECT_FLAG_DETECTED" in report["failure_modes"]
    assert report["live_candidate_eligible"] is False


def test_step297_registry_record_preserves_source_outcome_hashes() -> None:
    report = build_performance_report([_outcome("order_a", 1.0)], min_sample_size=1)
    registry_record = build_performance_report_registry_record(report)

    assert registry_record["performance_report_registry_version"] == PERFORMANCE_REPORT_VERSION
    assert registry_record["performance_report_id"] == report["performance_report_id"]
    assert registry_record["source_outcome_ids"] == report["source_outcome_ids"]
    assert registry_record["source_outcome_hashes"] == report["source_outcome_hashes"]
    assert registry_record["performance_report_registry_record_sha256"]


def test_step297_persists_latest_report_and_append_only_registry(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    rows = [_outcome("order_a", 2.0), _outcome("order_b", 1.0), _outcome("order_c", 0.5)]
    report = generate_and_persist_performance_report(rows, cfg=cfg, min_sample_size=3)
    registry = registry_path(cfg, PERFORMANCE_REPORT_REGISTRY_NAME)
    registry_rows = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines()]

    assert (tmp_path / "storage" / "latest" / "performance_report.json").exists()
    assert (tmp_path / "storage" / "latest" / "performance_report_registry_record.json").exists()
    assert len(registry_rows) == 1
    assert registry_rows[0]["registry_name"] == PERFORMANCE_REPORT_REGISTRY_NAME
    assert report["performance_report_registry_record_id"] == registry_rows[0]["performance_report_registry_record_id"]


def test_step297_run_latest_reads_outcome_feedback_registry(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    analyze_and_persist_paper_outcome(reconcile_paper_execution_record(simulate_paper_execution(_intent("order_a"), risk_gate_report=_risk_gate(_intent("order_a"))).to_dict()), outcome_context={"result_R": 1.0}, cfg=cfg)
    analyze_and_persist_paper_outcome(reconcile_paper_execution_record(simulate_paper_execution(_intent("order_b"), risk_gate_report=_risk_gate(_intent("order_b"))).to_dict()), outcome_context={"result_R": 1.5}, cfg=cfg)
    analyze_and_persist_paper_outcome(reconcile_paper_execution_record(simulate_paper_execution(_intent("order_c"), risk_gate_report=_risk_gate(_intent("order_c"))).to_dict()), outcome_context={"result_R": 2.0}, cfg=cfg)

    report = run_performance_report_latest(cfg=cfg, min_sample_size=3)

    assert report["status"] == STATUS_PERFORMANCE_REPORT_RECORDED
    assert report["recommendation"] == RECOMMEND_CREATE_CANDIDATE_PROFILE_DRAFT
    assert (tmp_path / "storage" / "registries" / "performance_report_registry.jsonl").exists()


def _plain_row(signal_id: str, result_r: float, created_at: str, *, entry_price: float = 100.0) -> dict:
    return {
        "outcome_closed": True,
        "outcome_id": f"out_{signal_id}_{result_r}_{created_at}",
        "research_signal_id": signal_id,
        "profile_id": "paper_default_v1",
        "result_R": result_r,
        "expectancy": result_r,
        "created_at_utc": created_at,
        "direction": "LONG",
        "entry_price": entry_price,
    }


def test_step297_repeated_setup_is_insufficient_independent_events() -> None:
    # 4 closed rows, but all the same setup re-entered every 15 minutes:
    # closed_count passes min_sample_size, the independent-event gate must not.
    rows = [
        _plain_row("sig_a", 2.5, "2026-07-21T02:27:29Z"),
        _plain_row("sig_a", 2.5, "2026-07-21T02:42:29Z"),
        _plain_row("sig_a", 2.5, "2026-07-21T02:57:29Z"),
        _plain_row("sig_a", 2.5, "2026-07-21T03:12:29Z"),
    ]
    report = build_performance_report(rows, min_sample_size=3)
    assert report["independent_trade_event_count"] == 1
    assert report["status"] == STATUS_PERFORMANCE_REPORT_REVIEW_ONLY_INSUFFICIENT_SAMPLE
    assert "INSUFFICIENT_INDEPENDENT_TRADE_EVENTS" in report["blockers"]
    assert report["live_candidate_eligible"] is False


def test_step297_all_signals_low_sample_reports_insufficient_not_no_outcomes() -> None:
    # Two signals, each one repeated setup -> both excluded. The report must
    # say "insufficient sample", not "no outcome records".
    rows = [
        _plain_row("sig_a", 2.5, "2026-07-21T02:27:29Z"),
        _plain_row("sig_a", 2.5, "2026-07-21T02:42:29Z"),
        _plain_row("sig_b", 1.9, "2026-07-21T02:27:30Z", entry_price=200.0),
        _plain_row("sig_b", 1.9, "2026-07-21T02:42:30Z", entry_price=200.0),
    ]
    report = build_performance_report(rows, min_sample_size=3, min_signal_sample_size=3)
    assert report["blockers"] == ["ALL_SIGNALS_BELOW_MIN_INDEPENDENT_EVENTS"]
    assert report["status"] == STATUS_PERFORMANCE_REPORT_REVIEW_ONLY_INSUFFICIENT_SAMPLE
    assert report["live_candidate_eligible"] is False
    for signal_summary in report["summary_by_signal"].values():
        assert signal_summary["independent_event_count"] == 1
        assert signal_summary["sufficient_sample"] is False


def test_step297_distinct_events_stay_eligible() -> None:
    # Genuinely distinct setups (different R, different days) keep eligibility.
    rows = [
        _plain_row("sig_a", 2.0, "2026-07-18T02:00:00Z"),
        _plain_row("sig_a", 1.5, "2026-07-19T02:00:00Z", entry_price=110.0),
        _plain_row("sig_a", 0.5, "2026-07-20T02:00:00Z", entry_price=120.0),
    ]
    report = build_performance_report(rows, min_sample_size=3)
    assert report["independent_trade_event_count"] == 3
    assert report["status"] == "PERFORMANCE_REPORT_RECORDED"
    assert report["live_candidate_eligible"] is True

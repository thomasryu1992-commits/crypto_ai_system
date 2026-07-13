from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.research.research_signal_profile_final_apply_approval import (
    STEP266_PROFILE_FINAL_APPLY_APPROVAL_VERSION,
    apply_step266_final_manual_apply_approval_disabled_stub,
    build_step266_final_manual_apply_approval_record,
    resolve_step266_final_apply_approval_policy,
    validate_step266_final_manual_apply_approval_record,
)
from scripts.report_step259_researchsignal_weight_calibration import _synthetic_calibration_matrix
from scripts.report_step265_researchsignal_profile_disabled_apply_dry_run import build_report as build_step265_report
from scripts.report_step266_researchsignal_profile_final_apply_approval_validator import build_report as build_step266_report


def test_step266_policy_hard_locks_apply_even_with_overrides() -> None:
    cfg = load_config('.')
    policy = resolve_step266_final_apply_approval_policy(
        cfg,
        {
            'manual_final_apply_approval_required': False,
            'auto_apply_approved_profile': True,
            'runtime_score_weight_write_enabled': True,
            'settings_score_weight_write_enabled': True,
            'apply_approved_profile_enabled': True,
            'canonical_approve_decision': 'SOMETHING_ELSE',
        },
    )
    assert policy['manual_final_apply_approval_required'] is True
    assert policy['auto_apply_approved_profile'] is False
    assert policy['runtime_score_weight_write_enabled'] is False
    assert policy['settings_score_weight_write_enabled'] is False
    assert policy['apply_approved_profile_enabled'] is False
    assert policy['canonical_approve_decision'] == 'APPROVED_DISABLED_APPLY_DRY_RUN'


def test_step266_default_request_more_data_records_without_mutation() -> None:
    report = build_step266_report(
        Path('.').resolve(),
        max_rows=24,
        upstream_approval_decision='REQUEST_MORE_DATA',
        upstream_approver='thomas',
        upstream_approval_rationale='Real matrix required upstream.',
        upstream_approval_timestamp_utc='2026-06-30T00:00:00Z',
        upstream_review_decision='REQUEST_MORE_DATA',
        upstream_reviewer='thomas',
        upstream_review_rationale='Pre-apply review requires approved staging handoff.',
        upstream_review_timestamp_utc='2026-06-30T00:00:00Z',
        final_approval_decision='REQUEST_MORE_DATA',
        final_approver='thomas',
        final_rationale='Final approval requires a ready disabled dry-run packet.',
        final_timestamp_utc='2026-06-30T00:00:00Z',
    )
    record = report['final_apply_approval_record']
    approval = record['final_apply_approval_record']

    assert report['step'] == 266
    assert report['status'] == 'completed'
    assert record['version'] == STEP266_PROFILE_FINAL_APPLY_APPROVAL_VERSION
    assert approval['record_status'] == 'more_data_requested'
    assert approval['recorded'] is True
    assert report['runtime_score_weights_unchanged'] is True
    assert report['final_apply_approval_policy']['candidate_profile_applied'] is False
    assert report['application_stub_result']['status'] == 'DISABLED_STUB'
    assert report['safety_boundaries']['external_order_submission_performed'] is False


def test_step266_approve_dry_run_is_invalid_when_step265_source_blocked() -> None:
    report = build_step266_report(
        Path('.').resolve(),
        max_rows=24,
        upstream_approval_decision='REQUEST_MORE_DATA',
        upstream_approver='thomas',
        upstream_approval_rationale='Candidate is not ready.',
        upstream_approval_timestamp_utc='2026-06-30T00:00:00Z',
        upstream_review_decision='REQUEST_MORE_DATA',
        upstream_reviewer='thomas',
        upstream_review_rationale='Pre-apply review is not ready.',
        upstream_review_timestamp_utc='2026-06-30T00:00:00Z',
        final_approval_decision='APPROVE_DRY_RUN',
        final_approver='thomas',
        final_rationale='Should be rejected because dry-run is blocked.',
        final_timestamp_utc='2026-06-30T00:00:00Z',
    )
    record = report['final_apply_approval_record']
    approval = record['final_apply_approval_record']

    assert report['status'] == 'failed_validation'
    assert approval['record_status'] == 'invalid'
    assert approval['recorded'] is False
    assert 'SOURCE_DRY_RUN_NOT_READY_FOR_FINAL_APPROVAL' in approval['record_reasons']
    assert 'READY_FOR_DISABLED_APPLY_DRY_RUN_FLAG_FALSE' in approval['record_reasons']
    assert report['runtime_score_weights_unchanged'] is True
    assert report['application_stub_result']['runtime_score_weights_mutated'] is False


def test_step266_ready_step265_dry_run_accepts_approve_but_does_not_apply(tmp_path: Path) -> None:
    matrix_path = tmp_path / 'research_feature_matrix_backtest.csv'
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)

    report = build_step266_report(
        Path('.').resolve(),
        matrix_path=str(matrix_path),
        max_rows=72,
        upstream_approval_decision='APPROVE_FOR_REVIEW_ONLY_STAGING',
        upstream_approver='thomas',
        upstream_approval_rationale='Candidate approved only for review-only staging.',
        upstream_approval_timestamp_utc='2026-06-30T00:00:00Z',
        upstream_review_decision='READY',
        upstream_reviewer='thomas',
        upstream_review_rationale='Ready for disabled pre-apply review only.',
        upstream_review_timestamp_utc='2026-06-30T00:00:00Z',
        final_approval_decision='APPROVE_DRY_RUN',
        final_approver='thomas',
        final_rationale='Approve disabled dry-run packet only.',
        final_timestamp_utc='2026-06-30T00:00:00Z',
    )
    record = report['final_apply_approval_record']
    approval = record['final_apply_approval_record']
    validation = report['final_apply_approval_validation']

    assert report['status'] == 'completed'
    assert record['source_dry_run_status'] == 'ready_disabled_apply_dry_run'
    assert record['source_ready_for_disabled_apply_dry_run'] is True
    assert approval['record_status'] == 'approved_disabled_apply_dry_run'
    assert approval['recorded'] is True
    assert record['production_candidate_profile'] in {
        'baseline_step258',
        'price_structure_dominant',
        'flow_confirmed',
        'liquidity_risk_guarded',
    }
    assert record['candidate_weights_present'] is True
    assert record['mutation_plan_write_enabled'] is False
    assert record['mutation_plan_apply_enabled'] is False
    assert record['decision_effect']['disabled_dry_run_final_approval_recorded'] is True
    assert record['decision_effect']['candidate_profile_applied'] is False
    assert validation['valid'] is True
    assert report['runtime_score_weights_unchanged'] is True
    assert report['application_stub_result']['runtime_score_weights_mutated'] is False
    assert report['application_stub_result']['settings_score_weights_mutated'] is False
    assert report['application_stub_result']['order_routing_enabled'] is False


def test_step266_disabled_final_apply_stub_does_not_mutate_score_weights(tmp_path: Path) -> None:
    cfg = load_config('.')
    before = dict(cfg.get('research.score_weights'))
    matrix_path = tmp_path / 'matrix.csv'
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)
    step265_report = build_step265_report(
        Path('.').resolve(),
        matrix_path=str(matrix_path),
        max_rows=72,
        approval_decision='APPROVE_FOR_REVIEW_ONLY_STAGING',
        approver='thomas',
        approval_rationale='Review-only staging approved.',
        approval_timestamp_utc='2026-06-30T00:00:00Z',
        review_decision='READY',
        reviewer='thomas',
        review_rationale='Disabled pre-apply review ready.',
        review_timestamp_utc='2026-06-30T00:00:00Z',
    )
    record = build_step266_final_manual_apply_approval_record(
        step265_report,
        cfg,
        approval_decision='APPROVE_DRY_RUN',
        approver='thomas',
        rationale='Approve disabled dry-run only.',
        timestamp_utc='2026-06-30T00:00:00Z',
    )
    validation = validate_step266_final_manual_apply_approval_record(record)
    result = apply_step266_final_manual_apply_approval_disabled_stub(record, cfg)

    assert validation['valid'] is True
    assert result['status'] == 'DISABLED_STUB'
    assert result['record_status'] == 'approved_disabled_apply_dry_run'
    assert result['score_weights_before'] == before
    assert result['score_weights_after'] == before
    assert cfg.get('research.score_weights') == before
    assert result['runtime_score_weights_mutated'] is False
    assert result['settings_score_weights_mutated'] is False
    assert result['external_order_submission_performed'] is False

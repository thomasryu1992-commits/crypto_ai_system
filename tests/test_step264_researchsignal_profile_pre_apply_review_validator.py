from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.research.research_signal_profile_pre_apply_review import (
    STEP264_PROFILE_PRE_APPLY_REVIEW_VERSION,
    apply_step264_pre_apply_review_disabled_stub,
    build_step264_pre_apply_review_record,
    resolve_step264_pre_apply_review_policy,
    validate_step264_pre_apply_review_record,
)
from scripts.report_step259_researchsignal_weight_calibration import _synthetic_calibration_matrix
from scripts.report_step263_researchsignal_profile_review_only_staging_handoff import build_report as build_step263_report
from scripts.report_step264_researchsignal_profile_pre_apply_review_validator import build_report as build_step264_report


def test_step264_policy_hard_locks_mutation_even_with_overrides() -> None:
    cfg = load_config('.')
    policy = resolve_step264_pre_apply_review_policy(
        cfg,
        {
            'manual_pre_apply_review_required': False,
            'auto_apply_reviewed_profile': True,
            'runtime_score_weight_write_enabled': True,
            'settings_score_weight_write_enabled': True,
            'apply_reviewed_profile_enabled': True,
            'canonical_ready_decision': 'READY_AND_APPLY_NOW',
        },
    )
    assert policy['manual_pre_apply_review_required'] is True
    assert policy['auto_apply_reviewed_profile'] is False
    assert policy['runtime_score_weight_write_enabled'] is False
    assert policy['settings_score_weight_write_enabled'] is False
    assert policy['apply_reviewed_profile_enabled'] is False
    assert policy['canonical_ready_decision'] == 'READY_FOR_DISABLED_PRE_APPLY_REVIEW'


def test_step264_default_request_more_data_records_without_mutation() -> None:
    report = build_step264_report(
        Path('.').resolve(),
        max_rows=24,
        approval_decision='REQUEST_MORE_DATA',
        approver='thomas',
        approval_rationale='Real matrix required upstream.',
        approval_timestamp_utc='2026-06-30T00:00:00Z',
        review_decision='REQUEST_MORE_DATA',
        reviewer='thomas',
        rationale='Pre-apply review requires an approved staging handoff.',
        timestamp_utc='2026-06-30T00:00:00Z',
    )
    record = report['pre_apply_review_record']
    review = record['pre_apply_review_record']

    assert report['step'] == 264
    assert report['status'] == 'completed'
    assert record['version'] == STEP264_PROFILE_PRE_APPLY_REVIEW_VERSION
    assert record['source_handoff_status'] == 'blocked_by_approval_intake'
    assert review['review_decision'] == 'REQUEST_MORE_DATA'
    assert review['record_status'] == 'more_data_requested'
    assert report['runtime_score_weights_unchanged'] is True
    assert report['pre_apply_review_policy']['runtime_score_weight_mutation_allowed'] is False
    assert report['application_stub_result']['status'] == 'DISABLED_STUB'
    assert report['safety_boundaries']['external_order_submission_performed'] is False


def test_step264_ready_requires_ready_step263_handoff() -> None:
    step263_report = build_step263_report(
        Path('.').resolve(),
        max_rows=24,
        approval_decision='REQUEST_MORE_DATA',
        approver='thomas',
        rationale='Need more data before staging.',
        timestamp_utc='2026-06-30T00:00:00Z',
    )
    record = build_step264_pre_apply_review_record(
        step263_report,
        load_config('.'),
        review_decision='READY',
        reviewer='thomas',
        rationale='Trying to mark blocked handoff as ready should fail.',
        timestamp_utc='2026-06-30T00:00:00Z',
    )
    validation = validate_step264_pre_apply_review_record(record)

    assert record['pre_apply_review_record']['record_status'] == 'invalid'
    assert record['pre_apply_review_record']['recorded'] is False
    assert 'STAGING_HANDOFF_NOT_READY_FOR_PRE_APPLY_REVIEW' in record['pre_apply_review_record']['record_reasons']
    assert validation['valid'] is False
    assert 'validation_object_valid' in validation['failed_checks']


def test_step264_ready_records_only_disabled_pre_apply_review_when_step263_ready(tmp_path: Path) -> None:
    matrix_path = tmp_path / 'research_feature_matrix_backtest.csv'
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)

    report = build_step264_report(
        Path('.').resolve(),
        matrix_path=str(matrix_path),
        max_rows=72,
        approval_decision='APPROVE_FOR_REVIEW_ONLY_STAGING',
        approver='thomas',
        approval_rationale='Candidate approved only for review-only staging.',
        approval_timestamp_utc='2026-06-30T00:00:00Z',
        review_decision='READY',
        reviewer='thomas',
        rationale='Ready for disabled pre-apply review only.',
        timestamp_utc='2026-06-30T00:00:00Z',
    )
    record = report['pre_apply_review_record']
    review = record['pre_apply_review_record']
    validation = report['pre_apply_review_validation']

    assert report['status'] == 'completed'
    assert record['source_handoff_status'] == 'ready_for_pre_apply_review'
    assert record['source_ready_for_pre_apply_review'] is True
    assert record['candidate_available'] is True
    assert record['production_candidate_profile'] in {
        'baseline_step258',
        'price_structure_dominant',
        'flow_confirmed',
        'liquidity_risk_guarded',
    }
    assert review['review_decision'] == 'READY'
    assert review['canonical_review_decision'] == 'READY_FOR_DISABLED_PRE_APPLY_REVIEW'
    assert review['record_status'] == 'ready_for_disabled_pre_apply_review'
    assert validation['valid'] is True
    assert report['runtime_score_weights_unchanged'] is True
    assert report['application_stub_result']['runtime_score_weights_mutated'] is False
    assert report['application_stub_result']['order_routing_enabled'] is False


def test_step264_reject_records_on_ready_handoff_without_apply(tmp_path: Path) -> None:
    matrix_path = tmp_path / 'matrix.csv'
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)
    step263_report = build_step263_report(
        Path('.').resolve(),
        matrix_path=str(matrix_path),
        max_rows=72,
        approval_decision='APPROVE_FOR_REVIEW_ONLY_STAGING',
        approver='thomas',
        rationale='Candidate approved only for staging handoff.',
        timestamp_utc='2026-06-30T00:00:00Z',
    )
    record = build_step264_pre_apply_review_record(
        step263_report,
        load_config('.'),
        review_decision='REJECT',
        reviewer='thomas',
        rationale='Reject at pre-apply review.',
        timestamp_utc='2026-06-30T00:00:00Z',
    )
    validation = validate_step264_pre_apply_review_record(record)

    assert record['pre_apply_review_record']['record_status'] == 'rejected_pre_apply_review'
    assert record['pre_apply_review_record']['recorded'] is True
    assert validation['valid'] is True
    assert record['decision_effect']['pre_apply_review_rejection_recorded'] is True
    assert record['decision_effect']['runtime_profile_application_allowed'] is False


def test_step264_disabled_apply_stub_does_not_mutate_score_weights(tmp_path: Path) -> None:
    cfg = load_config('.')
    before = dict(cfg.get('research.score_weights'))
    matrix_path = tmp_path / 'matrix.csv'
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)
    report = build_step264_report(
        Path('.').resolve(),
        matrix_path=str(matrix_path),
        max_rows=72,
        approval_decision='APPROVE_FOR_REVIEW_ONLY_STAGING',
        approver='thomas',
        approval_rationale='Review-only staging approved.',
        approval_timestamp_utc='2026-06-30T00:00:00Z',
        review_decision='READY',
        reviewer='thomas',
        rationale='Disabled pre-apply review ready.',
        timestamp_utc='2026-06-30T00:00:00Z',
    )

    result = apply_step264_pre_apply_review_disabled_stub(report['pre_apply_review_record'], cfg)

    assert result['status'] == 'DISABLED_STUB'
    assert result['score_weights_before'] == before
    assert result['score_weights_after'] == before
    assert cfg.get('research.score_weights') == before
    assert result['runtime_score_weights_mutated'] is False
    assert result['settings_score_weights_mutated'] is False
    assert result['external_order_submission_performed'] is False

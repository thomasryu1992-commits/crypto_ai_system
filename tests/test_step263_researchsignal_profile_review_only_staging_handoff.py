from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.research.research_signal_profile_staging_handoff import (
    STEP263_PROFILE_STAGING_HANDOFF_VERSION,
    apply_step263_staging_handoff_disabled_stub,
    build_step263_review_only_staging_handoff_packet,
    resolve_step263_staging_handoff_policy,
    validate_step263_staging_handoff_packet,
)
from scripts.report_step259_researchsignal_weight_calibration import _synthetic_calibration_matrix
from scripts.report_step262_researchsignal_profile_approval_intake_validator import build_report as build_step262_report
from scripts.report_step263_researchsignal_profile_review_only_staging_handoff import build_report as build_step263_report


def test_step263_policy_hard_locks_mutation_even_with_overrides() -> None:
    cfg = load_config('.')
    policy = resolve_step263_staging_handoff_policy(
        cfg,
        {
            'manual_pre_apply_review_required': False,
            'pre_apply_checklist_required': False,
            'auto_apply_approved_profile': True,
            'runtime_score_weight_write_enabled': True,
            'settings_score_weight_write_enabled': True,
            'apply_approved_profile_enabled': True,
        },
    )
    assert policy['manual_pre_apply_review_required'] is True
    assert policy['pre_apply_checklist_required'] is True
    assert policy['auto_apply_approved_profile'] is False
    assert policy['runtime_score_weight_write_enabled'] is False
    assert policy['settings_score_weight_write_enabled'] is False
    assert policy['apply_approved_profile_enabled'] is False


def test_step263_default_request_more_data_builds_blocked_handoff() -> None:
    report = build_step263_report(
        Path('.').resolve(),
        max_rows=24,
        approval_decision='REQUEST_MORE_DATA',
        approver='thomas',
        rationale='Real matrix is required before staging handoff.',
        timestamp_utc='2026-06-30T00:00:00Z',
    )
    packet = report['staging_handoff_packet']

    assert report['step'] == 263
    assert report['status'] == 'completed'
    assert packet['version'] == STEP263_PROFILE_STAGING_HANDOFF_VERSION
    assert packet['handoff']['handoff_status'] == 'blocked_by_approval_intake'
    assert packet['handoff']['ready_for_pre_apply_review'] is False
    assert 'APPROVE_FOR_REVIEW_ONLY_STAGING_REQUIRED' in packet['handoff']['blocked_reasons']
    assert report['runtime_score_weights_unchanged'] is True
    assert report['staging_handoff_policy']['runtime_score_weight_mutation_allowed'] is False
    assert report['application_stub_result']['status'] == 'DISABLED_STUB'
    assert report['safety_boundaries']['external_order_submission_performed'] is False


def test_step263_approve_intake_record_creates_ready_pre_apply_handoff(tmp_path: Path) -> None:
    matrix_path = tmp_path / 'research_feature_matrix_backtest.csv'
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)

    report = build_step263_report(
        Path('.').resolve(),
        matrix_path=str(matrix_path),
        max_rows=72,
        approval_decision='APPROVE_FOR_REVIEW_ONLY_STAGING',
        approver='thomas',
        rationale='Candidate profile is approved only for review-only staging handoff.',
        timestamp_utc='2026-06-30T00:00:00Z',
        notes='Ready for pre-apply checklist review only.',
    )
    packet = report['staging_handoff_packet']
    validation = report['staging_handoff_validation']

    assert report['status'] == 'completed'
    assert packet['handoff']['handoff_status'] == 'ready_for_pre_apply_review'
    assert packet['handoff']['ready_for_pre_apply_review'] is True
    assert packet['source']['approval_decision'] == 'APPROVE_FOR_REVIEW_ONLY_STAGING'
    assert packet['source']['approval_record_status'] == 'accepted_review_only_staging'
    assert packet['candidate']['candidate_available'] is True
    assert packet['candidate']['production_candidate_profile'] in {
        'baseline_step258',
        'price_structure_dominant',
        'flow_confirmed',
        'liquidity_risk_guarded',
    }
    assert packet['handoff']['pre_apply_checklist_summary']['all_passed'] is True
    assert validation['valid'] is True
    assert report['runtime_score_weights_unchanged'] is True
    assert report['application_stub_result']['runtime_score_weights_mutated'] is False


def test_step263_reject_intake_record_blocks_staging_handoff(tmp_path: Path) -> None:
    matrix_path = tmp_path / 'matrix.csv'
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)
    step262_report = build_step262_report(
        Path('.').resolve(),
        matrix_path=str(matrix_path),
        max_rows=72,
        approval_decision='REJECT',
        approver='thomas',
        rationale='Reject candidate for now.',
        timestamp_utc='2026-06-30T00:00:00Z',
    )
    packet = build_step263_review_only_staging_handoff_packet(step262_report, load_config('.'))
    validation = validate_step263_staging_handoff_packet(packet)

    assert packet['handoff']['handoff_status'] == 'blocked_by_approval_intake'
    assert packet['handoff']['ready_for_pre_apply_review'] is False
    assert 'SOURCE_DECISION_NOT_APPROVED_FOR_STAGING' in packet['handoff']['blocked_reasons']
    assert validation['valid'] is True
    assert validation['checks']['ready_requires_source_approval'] is True


def test_step263_validation_fails_when_ready_handoff_missing_candidate() -> None:
    report = build_step263_report(
        Path('.').resolve(),
        max_rows=24,
        approval_decision='REQUEST_MORE_DATA',
        approver='thomas',
        rationale='Need more data.',
        timestamp_utc='2026-06-30T00:00:00Z',
    )
    packet = report['staging_handoff_packet']
    packet['handoff']['handoff_status'] = 'ready_for_pre_apply_review'
    packet['handoff']['ready_for_pre_apply_review'] = True
    validation = validate_step263_staging_handoff_packet(packet)

    assert validation['valid'] is False
    assert 'ready_requires_candidate_available' in validation['failed_checks']
    assert 'ready_requires_source_approval' in validation['failed_checks']


def test_step263_disabled_apply_stub_does_not_mutate_score_weights(tmp_path: Path) -> None:
    cfg = load_config('.')
    before = dict(cfg.get('research.score_weights'))
    matrix_path = tmp_path / 'matrix.csv'
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)
    report = build_step263_report(
        Path('.').resolve(),
        matrix_path=str(matrix_path),
        max_rows=72,
        approval_decision='APPROVE_FOR_REVIEW_ONLY_STAGING',
        approver='thomas',
        rationale='Review-only staging handoff.',
        timestamp_utc='2026-06-30T00:00:00Z',
    )

    result = apply_step263_staging_handoff_disabled_stub(report['staging_handoff_packet'], cfg)

    assert result['status'] == 'DISABLED_STUB'
    assert result['score_weights_before'] == before
    assert result['score_weights_after'] == before
    assert cfg.get('research.score_weights') == before
    assert result['runtime_score_weights_mutated'] is False
    assert result['settings_score_weights_mutated'] is False
    assert result['order_routing_enabled'] is False

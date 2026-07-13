from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.research.research_signal_profile_apply_dry_run import (
    STEP265_PROFILE_APPLY_DRY_RUN_VERSION,
    apply_step265_disabled_apply_candidate_dry_run_stub,
    build_score_weight_diff,
    build_step265_disabled_apply_candidate_dry_run_packet,
    resolve_step265_apply_dry_run_policy,
    validate_step265_disabled_apply_candidate_dry_run_packet,
)
from scripts.report_step259_researchsignal_weight_calibration import _synthetic_calibration_matrix
from scripts.report_step264_researchsignal_profile_pre_apply_review_validator import build_report as build_step264_report
from scripts.report_step265_researchsignal_profile_disabled_apply_dry_run import build_report as build_step265_report


def test_step265_policy_hard_locks_mutation_even_with_overrides() -> None:
    cfg = load_config('.')
    policy = resolve_step265_apply_dry_run_policy(
        cfg,
        {
            'manual_apply_approval_required': False,
            'auto_apply_candidate_profile': True,
            'runtime_score_weight_write_enabled': True,
            'settings_score_weight_write_enabled': True,
            'apply_candidate_profile_enabled': True,
            'mutation_plan_write_enabled': False,
            'diff_required': False,
        },
    )
    assert policy['manual_apply_approval_required'] is True
    assert policy['auto_apply_candidate_profile'] is False
    assert policy['runtime_score_weight_write_enabled'] is False
    assert policy['settings_score_weight_write_enabled'] is False
    assert policy['apply_candidate_profile_enabled'] is False
    assert policy['mutation_plan_write_enabled'] is True
    assert policy['diff_required'] is True


def test_step265_score_weight_diff_marks_changed_added_removed_and_unchanged() -> None:
    diff = build_score_weight_diff(
        {'structure': 0.2, 'momentum': 0.1, 'old': 0.3},
        {'structure': 0.25, 'momentum': 0.1, 'new': 0.4},
    )
    assert diff['has_diff'] is True
    assert diff['changed'] == ['structure']
    assert diff['unchanged'] == ['momentum']
    assert diff['removed'] == ['old']
    assert diff['added'] == ['new']
    assert diff['details']['structure']['delta'] == 0.04999999999999999


def test_step265_default_request_more_data_builds_blocked_dry_run_without_mutation() -> None:
    report = build_step265_report(
        Path('.').resolve(),
        max_rows=24,
        approval_decision='REQUEST_MORE_DATA',
        approver='thomas',
        approval_rationale='Real matrix required upstream.',
        approval_timestamp_utc='2026-06-30T00:00:00Z',
        review_decision='REQUEST_MORE_DATA',
        reviewer='thomas',
        review_rationale='Pre-apply review requires approved staging handoff.',
        review_timestamp_utc='2026-06-30T00:00:00Z',
    )
    packet = report['apply_dry_run_packet']

    assert report['step'] == 265
    assert report['status'] == 'completed'
    assert packet['version'] == STEP265_PROFILE_APPLY_DRY_RUN_VERSION
    assert packet['dry_run']['dry_run_status'] == 'blocked_by_pre_apply_review'
    assert packet['dry_run']['ready_for_disabled_apply_dry_run'] is False
    assert 'READY_PRE_APPLY_REVIEW_RECORD_REQUIRED' in packet['dry_run']['blocked_reasons']
    assert packet['mutation_plan']['write_enabled'] is False
    assert packet['mutation_plan']['apply_enabled'] is False
    assert report['runtime_score_weights_unchanged'] is True
    assert report['apply_dry_run_policy']['runtime_score_weight_mutation_allowed'] is False
    assert report['application_stub_result']['status'] == 'DISABLED_STUB'
    assert report['safety_boundaries']['external_order_submission_performed'] is False


def test_step265_ready_step264_record_creates_disabled_apply_dry_run_packet(tmp_path: Path) -> None:
    matrix_path = tmp_path / 'research_feature_matrix_backtest.csv'
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)

    report = build_step265_report(
        Path('.').resolve(),
        matrix_path=str(matrix_path),
        max_rows=72,
        approval_decision='APPROVE_FOR_REVIEW_ONLY_STAGING',
        approver='thomas',
        approval_rationale='Candidate approved only for review-only staging.',
        approval_timestamp_utc='2026-06-30T00:00:00Z',
        review_decision='READY',
        reviewer='thomas',
        review_rationale='Ready for disabled pre-apply review only.',
        review_timestamp_utc='2026-06-30T00:00:00Z',
    )
    packet = report['apply_dry_run_packet']
    validation = report['apply_dry_run_validation']

    assert report['status'] == 'completed'
    assert packet['source']['record_status'] == 'ready_for_disabled_pre_apply_review'
    assert packet['dry_run']['dry_run_status'] == 'ready_disabled_apply_dry_run'
    assert packet['dry_run']['ready_for_disabled_apply_dry_run'] is True
    assert packet['candidate']['candidate_available'] is True
    assert packet['candidate']['production_candidate_profile'] in {
        'baseline_step258',
        'price_structure_dominant',
        'flow_confirmed',
        'liquidity_risk_guarded',
    }
    assert packet['candidate']['candidate_weights_present'] is True
    assert packet['candidate']['candidate_weights_source'] == 'config.research.score_weight_profiles'
    assert set(packet['candidate']['candidate_weights']) == set(report['runtime_score_weights_before'])
    assert packet['mutation_plan']['write_enabled'] is False
    assert packet['mutation_plan']['apply_enabled'] is False
    assert all(op['enabled'] is False for op in packet['mutation_plan']['operations'])
    assert validation['valid'] is True
    assert report['runtime_score_weights_unchanged'] is True
    assert report['application_stub_result']['runtime_score_weights_mutated'] is False
    assert report['application_stub_result']['order_routing_enabled'] is False


def test_step265_disabled_apply_stub_does_not_mutate_score_weights(tmp_path: Path) -> None:
    cfg = load_config('.')
    before = dict(cfg.get('research.score_weights'))
    matrix_path = tmp_path / 'matrix.csv'
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)
    step264_report = build_step264_report(
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
    packet = build_step265_disabled_apply_candidate_dry_run_packet(step264_report, cfg)
    validation = validate_step265_disabled_apply_candidate_dry_run_packet(packet)
    result = apply_step265_disabled_apply_candidate_dry_run_stub(packet, cfg)

    assert validation['valid'] is True
    assert result['status'] == 'DISABLED_STUB'
    assert result['score_weights_before'] == before
    assert result['score_weights_after'] == before
    assert cfg.get('research.score_weights') == before
    assert result['runtime_score_weights_mutated'] is False
    assert result['settings_score_weights_mutated'] is False
    assert result['external_order_submission_performed'] is False

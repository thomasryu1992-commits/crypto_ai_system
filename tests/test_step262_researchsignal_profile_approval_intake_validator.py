from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.research.research_signal_profile_approval_intake import (
    STEP262_PROFILE_APPROVAL_INTAKE_VERSION,
    apply_step262_approval_intake_disabled_stub,
    build_step262_approval_intake_record,
    resolve_step262_approval_intake_policy,
    validate_step262_approval_intake_record,
)
from scripts.report_step259_researchsignal_weight_calibration import _synthetic_calibration_matrix
from scripts.report_step261_researchsignal_profile_manual_approval_packet import build_report as build_step261_report
from scripts.report_step262_researchsignal_profile_approval_intake_validator import build_report as build_step262_report


def test_step262_policy_hard_locks_mutation_even_with_overrides() -> None:
    cfg = load_config('.')
    policy = resolve_step262_approval_intake_policy(
        cfg,
        {
            'auto_apply_approved_profile': True,
            'runtime_score_weight_write_enabled': True,
            'settings_score_weight_write_enabled': True,
            'apply_approved_profile_enabled': True,
        },
    )
    assert policy['manual_approval_required'] is True
    assert policy['auto_apply_approved_profile'] is False
    assert policy['runtime_score_weight_write_enabled'] is False
    assert policy['settings_score_weight_write_enabled'] is False
    assert policy['apply_approved_profile_enabled'] is False


def test_step262_request_more_data_records_for_no_candidate_packet() -> None:
    report = build_step262_report(
        Path('.').resolve(),
        max_rows=24,
        approval_decision='REQUEST_MORE_DATA',
        approver='thomas',
        rationale='Real Feature Store matrix is required before profile approval.',
        timestamp_utc='2026-06-30T00:00:00Z',
    )
    record = report['approval_intake_record']

    assert report['step'] == 262
    assert report['status'] == 'completed'
    assert record['version'] == STEP262_PROFILE_APPROVAL_INTAKE_VERSION
    assert record['candidate_available'] is False
    assert record['approval_record']['approval_decision'] == 'REQUEST_MORE_DATA'
    assert record['approval_record']['record_status'] == 'more_data_requested'
    assert record['approval_record']['recorded'] is True
    assert report['runtime_score_weights_unchanged'] is True
    assert report['approval_intake_policy']['runtime_score_weight_mutation_allowed'] is False
    assert report['application_stub_result']['status'] == 'DISABLED_STUB'
    assert report['safety_boundaries']['external_order_submission_performed'] is False


def test_step262_approve_records_review_only_staging_for_candidate_packet(tmp_path: Path) -> None:
    matrix_path = tmp_path / 'research_feature_matrix_backtest.csv'
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)

    report = build_step262_report(
        Path('.').resolve(),
        matrix_path=str(matrix_path),
        max_rows=72,
        approval_decision='APPROVE_FOR_REVIEW_ONLY_STAGING',
        approver='thomas',
        rationale='Candidate profile is approved only for review-only staging handoff.',
        timestamp_utc='2026-06-30T00:00:00Z',
    )
    record = report['approval_intake_record']

    assert report['status'] == 'completed'
    assert record['candidate_available'] is True
    assert record['production_candidate_profile'] in {
        'baseline_step258',
        'price_structure_dominant',
        'flow_confirmed',
        'liquidity_risk_guarded',
    }
    assert record['approval_record']['record_status'] == 'accepted_review_only_staging'
    assert record['decision_effect']['review_only_staging_intent_recorded'] is True
    assert record['decision_effect']['runtime_profile_application_allowed'] is False
    assert record['decision_effect']['settings_profile_write_allowed'] is False
    assert report['runtime_score_weights_unchanged'] is True
    assert report['application_stub_result']['runtime_score_weights_mutated'] is False


def test_step262_approve_rejected_when_candidate_is_not_available() -> None:
    step261_report = build_step261_report(Path('.').resolve(), max_rows=24)
    record = build_step262_approval_intake_record(
        step261_report,
        load_config('.'),
        approval_decision='APPROVE_FOR_REVIEW_ONLY_STAGING',
        approver='thomas',
        rationale='Trying to approve no-candidate packet should fail.',
        timestamp_utc='2026-06-30T00:00:00Z',
    )
    validation = validate_step262_approval_intake_record(record)

    assert record['candidate_available'] is False
    assert record['approval_record']['recorded'] is False
    assert record['approval_record']['record_status'] == 'invalid'
    assert 'CANDIDATE_PROFILE_NOT_AVAILABLE' in record['approval_record']['record_reasons']
    assert validation['valid'] is False
    assert 'validation_object_valid' in validation['failed_checks']


def test_step262_invalid_intake_fields_fail_validation(tmp_path: Path) -> None:
    matrix_path = tmp_path / 'matrix.csv'
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)
    step261_report = build_step261_report(Path('.').resolve(), matrix_path=str(matrix_path), max_rows=72)
    record = build_step262_approval_intake_record(
        step261_report,
        load_config('.'),
        approval_decision='INVALID_DECISION',
        approver='',
        rationale='',
        timestamp_utc='not-a-timestamp',
    )
    validation = validate_step262_approval_intake_record(record)

    assert record['approval_record']['recorded'] is False
    assert validation['valid'] is False
    assert 'validation_object_valid' in validation['failed_checks']
    assert record['validation']['checks']['approval_decision_allowed'] is False
    assert record['validation']['checks']['approver_present'] is False
    assert record['validation']['checks']['rationale_present'] is False
    assert record['validation']['checks']['timestamp_utc_parseable'] is False


def test_step262_disabled_apply_stub_does_not_mutate_score_weights(tmp_path: Path) -> None:
    cfg = load_config('.')
    before = dict(cfg.get('research.score_weights'))
    matrix_path = tmp_path / 'matrix.csv'
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)
    report = build_step262_report(
        Path('.').resolve(),
        matrix_path=str(matrix_path),
        max_rows=72,
        approval_decision='APPROVE_FOR_REVIEW_ONLY_STAGING',
        approver='thomas',
        rationale='Review-only staging approval.',
        timestamp_utc='2026-06-30T00:00:00Z',
    )

    result = apply_step262_approval_intake_disabled_stub(report['approval_intake_record'], cfg)

    assert result['status'] == 'DISABLED_STUB'
    assert result['score_weights_before'] == before
    assert result['score_weights_after'] == before
    assert cfg.get('research.score_weights') == before
    assert result['runtime_score_weights_mutated'] is False
    assert result['settings_score_weights_mutated'] is False
    assert result['order_routing_enabled'] is False

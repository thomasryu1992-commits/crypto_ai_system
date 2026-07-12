from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.research.research_signal_profile_settings_write_preview import (
    STEP267_PROFILE_SETTINGS_WRITE_PREVIEW_VERSION,
    apply_step267_disabled_settings_write_preview_stub,
    build_step267_disabled_settings_write_preview_packet,
    resolve_step267_settings_write_preview_policy,
    validate_step267_disabled_settings_write_preview_packet,
)
from scripts.report_step259_researchsignal_weight_calibration import _synthetic_calibration_matrix
from scripts.report_step266_researchsignal_profile_final_apply_approval_validator import build_report as build_step266_report
from scripts.report_step267_researchsignal_profile_disabled_settings_write_preview import build_report as build_step267_report


def test_step267_policy_hard_locks_settings_write_even_with_overrides() -> None:
    cfg = load_config('.')
    policy = resolve_step267_settings_write_preview_policy(
        cfg,
        {
            'settings_write_preview_export_enabled': False,
            'manual_settings_write_review_required': False,
            'auto_apply_approved_profile': True,
            'runtime_score_weight_write_enabled': True,
            'settings_score_weight_write_enabled': True,
            'config_write_enabled': True,
            'settings_file_write_enabled': True,
            'apply_preview_enabled': True,
            'target_yaml_path': 'something.else',
        },
    )
    assert policy['settings_write_preview_export_enabled'] is True
    assert policy['manual_settings_write_review_required'] is True
    assert policy['auto_apply_approved_profile'] is False
    assert policy['runtime_score_weight_write_enabled'] is False
    assert policy['settings_score_weight_write_enabled'] is False
    assert policy['config_write_enabled'] is False
    assert policy['settings_file_write_enabled'] is False
    assert policy['apply_preview_enabled'] is False
    assert policy['target_yaml_path'] == 'research.score_weights'


def test_step267_default_request_more_data_builds_blocked_preview_without_mutation() -> None:
    report = build_step267_report(
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
        final_rationale='Final approval requires ready disabled dry-run packet.',
        final_timestamp_utc='2026-06-30T00:00:00Z',
        preview_operator_label='thomas',
        preview_notes='Only export a preview.',
        preview_timestamp_utc='2026-06-30T00:00:00Z',
    )
    packet = report['settings_write_preview_packet']
    validation = report['settings_write_preview_validation']

    assert report['step'] == 267
    assert report['status'] == 'completed'
    assert packet['version'] == STEP267_PROFILE_SETTINGS_WRITE_PREVIEW_VERSION
    assert packet['preview']['preview_status'] == 'blocked_by_final_apply_approval_record'
    assert packet['preview']['ready_for_disabled_settings_write_preview'] is False
    assert 'SOURCE_RECORD_STATUS_NOT_APPROVED_DISABLED_DRY_RUN' in packet['preview']['blocked_reasons']
    assert report['settings_write_preview_policy']['settings_write_enabled'] is False
    assert report['settings_write_preview_policy']['config_write_enabled'] is False
    assert report['runtime_score_weights_unchanged'] is True
    assert validation['valid'] is True
    assert report['application_stub_result']['status'] == 'DISABLED_STUB'
    assert report['safety_boundaries']['external_order_submission_performed'] is False


def test_step267_approved_step266_record_exports_exact_disabled_settings_diff(tmp_path: Path) -> None:
    matrix_path = tmp_path / 'research_feature_matrix_backtest.csv'
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)

    report = build_step267_report(
        Path('.').resolve(),
        matrix_path=str(matrix_path),
        max_rows=72,
        upstream_approval_decision='APPROVE_FOR_REVIEW_ONLY_STAGING',
        upstream_approver='thomas',
        upstream_approval_rationale='Review-only staging approved.',
        upstream_approval_timestamp_utc='2026-06-30T00:00:00Z',
        upstream_review_decision='READY',
        upstream_reviewer='thomas',
        upstream_review_rationale='Disabled pre-apply review ready.',
        upstream_review_timestamp_utc='2026-06-30T00:00:00Z',
        final_approval_decision='APPROVE_DRY_RUN',
        final_approver='thomas',
        final_rationale='Approve disabled dry-run only.',
        final_timestamp_utc='2026-06-30T00:00:00Z',
        preview_operator_label='thomas',
        preview_notes='Render candidate settings diff only.',
        preview_timestamp_utc='2026-06-30T00:00:00Z',
    )
    packet = report['settings_write_preview_packet']
    artifact = packet['settings_yaml_diff_artifact']
    validation = report['settings_write_preview_validation']

    assert report['status'] == 'completed'
    assert packet['preview']['preview_status'] == 'ready_disabled_settings_write_preview'
    assert packet['preview']['ready_for_disabled_settings_write_preview'] is True
    assert packet['production_candidate_profile'] in {
        'baseline_step258',
        'price_structure_dominant',
        'flow_confirmed',
        'liquidity_risk_guarded',
    }
    assert packet['candidate']['candidate_weights_present'] is True
    assert packet['candidate']['candidate_weights_source'] == 'config.research.score_weight_profiles'
    assert artifact['target_yaml_path'] == 'research.score_weights'
    assert artifact['target_settings_file'] == 'config/settings.yaml'
    assert 'research:' in artifact['candidate_settings_yaml']
    assert 'score_weights:' in artifact['candidate_settings_yaml']
    assert isinstance(artifact['unified_diff'], str)
    assert artifact['candidate_settings_yaml_sha256']
    assert packet['settings_write_preview_export']['settings_write_enabled'] is False
    assert packet['settings_write_preview_export']['config_write_enabled'] is False
    assert validation['valid'] is True
    assert report['runtime_score_weights_unchanged'] is True


def test_step267_disabled_stub_does_not_write_or_mutate_score_weights(tmp_path: Path) -> None:
    cfg = load_config('.')
    before = dict(cfg.get('research.score_weights'))
    settings_path = Path('config/settings.yaml')
    settings_before = settings_path.read_text(encoding='utf-8')
    matrix_path = tmp_path / 'matrix.csv'
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)
    step266_report = build_step266_report(
        Path('.').resolve(),
        matrix_path=str(matrix_path),
        max_rows=72,
        upstream_approval_decision='APPROVE_FOR_REVIEW_ONLY_STAGING',
        upstream_approver='thomas',
        upstream_approval_rationale='Review-only staging approved.',
        upstream_approval_timestamp_utc='2026-06-30T00:00:00Z',
        upstream_review_decision='READY',
        upstream_reviewer='thomas',
        upstream_review_rationale='Disabled pre-apply review ready.',
        upstream_review_timestamp_utc='2026-06-30T00:00:00Z',
        final_approval_decision='APPROVE_DRY_RUN',
        final_approver='thomas',
        final_rationale='Approve disabled dry-run only.',
        final_timestamp_utc='2026-06-30T00:00:00Z',
    )
    packet = build_step267_disabled_settings_write_preview_packet(step266_report, cfg)
    validation = validate_step267_disabled_settings_write_preview_packet(packet)
    result = apply_step267_disabled_settings_write_preview_stub(packet, cfg)

    assert validation['valid'] is True
    assert result['status'] == 'DISABLED_STUB'
    assert result['score_weights_before'] == before
    assert result['score_weights_after'] == before
    assert cfg.get('research.score_weights') == before
    assert settings_path.read_text(encoding='utf-8') == settings_before
    assert result['settings_file_written'] is False
    assert result['runtime_score_weights_mutated'] is False
    assert result['settings_score_weights_mutated'] is False
    assert result['external_order_submission_performed'] is False


def test_step267_report_script_exports_diff_and_candidate_yaml(tmp_path: Path) -> None:
    from scripts.report_step267_researchsignal_profile_disabled_settings_write_preview import _write_outputs

    matrix_path = tmp_path / 'matrix.csv'
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)
    report = build_step267_report(
        Path('.').resolve(),
        matrix_path=str(matrix_path),
        max_rows=72,
        upstream_approval_decision='APPROVE_FOR_REVIEW_ONLY_STAGING',
        upstream_review_decision='READY',
        final_approval_decision='APPROVE_DRY_RUN',
    )
    output = tmp_path / 'report.json'
    latest = tmp_path / 'latest.json'
    diff = tmp_path / 'preview.diff'
    candidate_yaml = tmp_path / 'candidate_settings.yaml'
    _write_outputs(report, output, latest, diff, candidate_yaml)

    assert output.exists()
    assert latest.exists()
    assert diff.exists()
    assert candidate_yaml.exists()
    assert 'research:' in candidate_yaml.read_text(encoding='utf-8')
    assert 'score_weights:' in candidate_yaml.read_text(encoding='utf-8')

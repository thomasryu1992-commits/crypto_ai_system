from __future__ import annotations

from pathlib import Path
import shutil
import json


from crypto_ai_system.config import load_config
from crypto_ai_system.research.research_signal_profile_approval import (
    STEP261_PROFILE_APPROVAL_PACKET_VERSION,
    apply_step261_approved_profile_disabled_stub,
    build_step261_manual_approval_packet,
    resolve_step261_approval_policy,
    validate_step261_approval_packet,
)
from scripts.report_step259_researchsignal_weight_calibration import _synthetic_calibration_matrix
from scripts.report_step260_researchsignal_profile_review_only_calibration import build_report as build_step260_report
from scripts.report_step261_researchsignal_profile_manual_approval_packet import build_report as build_step261_report


def _clean_config_root(tmp_path: Path) -> Path:
    root = tmp_path / 'clean_root'
    (root / 'config').mkdir(parents=True)
    shutil.copy(Path('config/settings.yaml'), root / 'config/settings.yaml')
    fallback = Path('config/fallback_data_profiles.yaml')
    if fallback.exists():
        shutil.copy(fallback, root / 'config/fallback_data_profiles.yaml')
    return root


def test_step261_policy_hard_locks_auto_apply_even_with_overrides() -> None:
    cfg = load_config('.')
    policy = resolve_step261_approval_policy(
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


def test_step261_synthetic_step260_report_creates_no_candidate_packet(tmp_path: Path) -> None:
    clean_root = _clean_config_root(tmp_path)
    cfg = load_config(clean_root)
    step260 = build_step260_report(clean_root, max_rows=24)
    source_path = clean_root / "data/reports/step260_researchsignal_profile_review_only_calibration_report.json"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(json.dumps(step260, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    packet = build_step261_manual_approval_packet(step260, cfg, source_step_report_path=source_path)
    validation = validate_step261_approval_packet(packet)

    assert packet['version'] == STEP261_PROFILE_APPROVAL_PACKET_VERSION
    assert packet['candidate']['candidate_available'] is False
    assert packet['candidate']['production_candidate_profile'] is None
    assert packet['approval']['approval_status'] == 'no_candidate_available'
    assert 'REAL_FEATURE_STORE_MATRIX_REQUIRED' in packet['candidate']['blocked_reasons']
    assert packet['approval']['manual_approval_required'] is True
    assert packet['approval']['approval_recorded'] is False
    assert packet['safety_boundaries']['runtime_score_weights_mutated'] is False
    assert packet['safety_boundaries']['missing_canonical_module_count'] == 2
    assert validation['valid'] is True


def test_step261_explicit_matrix_candidate_packet_is_pending_manual_approval(tmp_path: Path) -> None:
    matrix_path = tmp_path / 'research_feature_matrix_backtest.csv'
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)

    report = build_step261_report(Path('.').resolve(), matrix_path=str(matrix_path), max_rows=72)
    packet = report['approval_packet']

    assert report['step'] == 261
    assert report['status'] == 'completed'
    assert packet['candidate']['candidate_available'] is True
    assert packet['candidate']['production_candidate_profile'] in {
        'baseline_step258',
        'price_structure_dominant',
        'flow_confirmed',
        'liquidity_risk_guarded',
    }
    assert packet['approval']['approval_status'] == 'pending_manual_approval'
    assert packet['approval']['approval_recorded'] is False
    assert packet['candidate']['candidate_weights']
    assert abs(sum(packet['candidate']['candidate_weights'].values()) - 1.0) < 0.000001
    assert report['runtime_score_weights_unchanged'] is True
    assert report['approval_policy']['runtime_score_weight_mutation_allowed'] is False
    assert report['application_stub_result']['status'] == 'DISABLED_STUB'
    assert report['safety_boundaries']['external_order_submission_performed'] is False


def test_step261_disabled_apply_stub_does_not_mutate_score_weights(tmp_path: Path) -> None:
    cfg = load_config('.')
    before = dict(cfg.get('research.score_weights'))
    matrix_path = tmp_path / 'matrix.csv'
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)
    report = build_step261_report(Path('.').resolve(), matrix_path=str(matrix_path), max_rows=72)

    result = apply_step261_approved_profile_disabled_stub(report['approval_packet'], cfg)

    assert result['status'] == 'DISABLED_STUB'
    assert result['score_weights_before'] == before
    assert result['score_weights_after'] == before
    assert cfg.get('research.score_weights') == before
    assert result['runtime_score_weights_mutated'] is False
    assert result['settings_score_weights_mutated'] is False
    assert result['order_routing_enabled'] is False


def test_step261_packet_validation_fails_if_apply_flags_are_enabled(tmp_path: Path) -> None:
    matrix_path = tmp_path / 'matrix.csv'
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)
    packet = build_step261_report(Path('.').resolve(), matrix_path=str(matrix_path), max_rows=72)['approval_packet']
    packet['policy']['auto_apply_approved_profile'] = True
    packet['safety_boundaries']['runtime_score_weights_mutated'] = True

    validation = validate_step261_approval_packet(packet)
    assert validation['valid'] is False
    assert 'policy_blocks_auto_apply' in validation['failed_checks']
    assert 'safety_blocks_runtime_mutation' in validation['failed_checks']

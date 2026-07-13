from __future__ import annotations

from pathlib import Path
import shutil


from crypto_ai_system.config import load_config
from crypto_ai_system.research.research_signal_calibration import (
    STEP260_CALIBRATION_REVIEW_VERSION,
    build_step260_profile_review,
    evaluate_profile_acceptance,
    rank_profile_candidates,
    resolve_step260_acceptance_criteria,
)
from scripts.report_step259_researchsignal_weight_calibration import _synthetic_calibration_matrix
from scripts.report_step260_researchsignal_profile_review_only_calibration import build_report, load_step260_matrix


def _clean_config_root(tmp_path: Path) -> Path:
    root = tmp_path / 'clean_root'
    (root / 'config').mkdir(parents=True)
    shutil.copy(Path('config/settings.yaml'), root / 'config/settings.yaml')
    fallback = Path('config/fallback_data_profiles.yaml')
    if fallback.exists():
        shutil.copy(fallback, root / 'config/fallback_data_profiles.yaml')
    return root


def test_step260_acceptance_criteria_are_review_only_and_configurable() -> None:
    cfg = load_config('.')
    criteria = resolve_step260_acceptance_criteria(cfg, {'min_rows': 12, 'max_blocked_ratio': 0.5})
    assert criteria['min_rows'] == 12
    assert criteria['max_blocked_ratio'] == 0.5
    assert criteria['max_entry_allowed_ratio'] <= 0.80

    accepted = evaluate_profile_acceptance(
        {
            'profile_name': 'candidate',
            'rows': 48,
            'entry_allowed_ratio': 0.25,
            'blocked_ratio': 0.35,
            'reduced_ratio': 0.10,
        },
        criteria,
        matrix_source_type='stored_feature_store_matrix',
    )
    assert accepted['status'] == 'eligible_review_candidate'
    assert accepted['review_only'] is True
    assert accepted['failures'] == []


def test_step260_synthetic_fallback_never_selects_production_candidate(tmp_path: Path) -> None:
    clean_root = _clean_config_root(tmp_path)
    report = build_report(clean_root, max_rows=24)
    review = report['review']
    assert report['step'] == 260
    assert review['version'] == STEP260_CALIBRATION_REVIEW_VERSION
    assert review['matrix_source_type'] == 'synthetic_fallback_matrix'
    assert review['candidate_review']['production_candidate_profile'] is None
    assert review['candidate_review']['selection_reason'] == 'real_feature_store_matrix_required_before_candidate_selection'
    assert review['candidate_review']['auto_apply_selected_profile'] is False
    assert review['candidate_review']['selected_profile_written_to_settings'] is False
    assert review['production_profile_auto_applied'] is False
    assert report['production_candidate_policy']['synthetic_fallback_can_select_candidate'] is False
    assert report['safety_boundaries']['external_order_submission_performed'] is False


def test_step260_explicit_feature_store_matrix_can_rank_but_not_apply_candidate(tmp_path: Path) -> None:
    matrix_path = tmp_path / 'research_feature_matrix_backtest.csv'
    _synthetic_calibration_matrix(rows=72).to_csv(matrix_path, index=False)

    report = build_report(Path('.').resolve(), matrix_path=str(matrix_path), max_rows=72)
    review = report['review']
    assert review['matrix_source_type'] == 'explicit_feature_store_matrix'
    assert review['rows_evaluated'] == 72
    assert review['candidate_review']['production_candidate_profile'] in {
        'baseline_step258',
        'price_structure_dominant',
        'flow_confirmed',
        'liquidity_risk_guarded',
    }
    assert review['candidate_review']['auto_apply_selected_profile'] is False
    assert review['candidate_review']['runtime_score_weights_mutated'] is False
    assert review['config_mutated'] is False
    assert review['safety_boundaries']['live_trading_allowed'] is False
    assert review['safety_boundaries']['missing_canonical_module_count'] == 2


def test_step260_profile_ranking_requires_real_matrix_even_when_distribution_fits() -> None:
    comparison = {
        'results': [
            {'profile_name': 'good_shape', 'rows': 100, 'entry_allowed_ratio': 0.25, 'blocked_ratio': 0.35, 'reduced_ratio': 0.10},
        ]
    }
    synthetic_rank = rank_profile_candidates(comparison, matrix_source_type='synthetic_fallback_matrix')
    assert synthetic_rank['production_candidate_profile'] is None
    assert synthetic_rank['auto_apply_selected_profile'] is False

    stored_rank = rank_profile_candidates(comparison, matrix_source_type='stored_feature_store_matrix')
    assert stored_rank['production_candidate_profile'] == 'good_shape'
    assert stored_rank['selected_profile_written_to_settings'] is False


def test_step260_load_matrix_prefers_explicit_then_stored_then_synthetic(tmp_path: Path) -> None:
    explicit = tmp_path / 'explicit_matrix.csv'
    _synthetic_calibration_matrix(rows=30).to_csv(explicit, index=False)
    frame, source, source_type = load_step260_matrix(Path('.').resolve(), str(explicit))
    assert len(frame) == 30
    assert source_type == 'explicit_feature_store_matrix'
    assert source.endswith('explicit_matrix.csv')

    clean_root = tmp_path / 'empty_matrix_root'
    clean_root.mkdir()
    frame2, source2, source_type2 = load_step260_matrix(clean_root, None)
    assert not frame2.empty
    assert source2 == 'synthetic_step260_review_only_calibration_matrix'
    assert source_type2 == 'synthetic_fallback_matrix'


def test_step260_profile_review_has_full_safety_boundaries_for_explicit_matrix(tmp_path: Path) -> None:
    cfg = load_config('.')
    matrix = _synthetic_calibration_matrix(rows=36)
    review = build_step260_profile_review(
        matrix,
        cfg,
        matrix_source=str(tmp_path / 'matrix.csv'),
        matrix_source_type='explicit_feature_store_matrix',
        max_rows=36,
    )
    assert review['mode'] == 'review_only'
    assert review['comparison']['profiles_compared'] >= 4
    assert review['candidate_review']['auto_apply_selected_profile'] is False
    assert review['safety_boundaries']['order_routing_enabled'] is False
    assert review['safety_boundaries']['canonical_live_execution_port_performed'] is False

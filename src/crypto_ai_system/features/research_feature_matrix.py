from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Literal

import numpy as np
import pandas as pd

from crypto_ai_system.config import AppConfig
from crypto_ai_system.storage.paths import ensure_storage_dirs
from crypto_ai_system.utils.audit import sha256_file, sha256_json, stable_id, utc_now_canonical


CORE_EXTRA_SCORE_COLUMNS = [
    'binance_derivatives_score',
    'exchange_flow_score',
    'etf_flow_score',
    'stablecoin_liquidity_score',
]

CORE_EXTRA_SIGNAL_COLUMNS = [
    'derivatives_signal',
    'netflow_signal',
    'etf_signal',
]

FEATURE_GROUP_OUTPUTS = {
    'binance_derivatives_features': 'extra_derivatives_features',
    'exchange_flow_features': 'exchange_flow_features',
    'etf_flow_features': 'etf_flow_features',
    'stablecoin_liquidity_features': 'stablecoin_liquidity_features',
}

_EXTRA_AVAILABILITY_PREFIX = '__extra_available__'
RESEARCH_FEATURE_MATRIX_VERSION = 'step259_weight_calibration_permission_distribution_matrix'
FEATURE_STORE_MANIFEST_VERSION = 'step270_feature_store_manifest_with_data_snapshot_v1'


def _to_utc_timestamp(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors='coerce')


def _safe_numeric(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors='coerce')
    return out


def _dedup_sort(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if 'timestamp' not in out.columns:
        return out.reset_index(drop=True)
    out['_ts'] = _to_utc_timestamp(out['timestamp'])
    out = out.dropna(subset=['_ts']).sort_values('_ts')
    out = out.drop_duplicates('_ts', keep='last')
    return out.reset_index(drop=True)


def _combine_first_ordered(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    if not columns:
        return pd.Series([np.nan] * len(df), index=df.index)
    combined = df[columns[0]]
    for col in columns[1:]:
        combined = combined.combine_first(df[col])
    return combined


_TIMEDELTA_SPEC = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([A-Za-z]+)\s*$")


def _timedelta_from_spec(spec: str) -> pd.Timedelta:
    """Parse a "3D"/"12h"-style config spec with an explicit unit.

    The string form ``pd.Timedelta("3D")`` goes through NumPy's deprecated
    'generic' timedelta unit and will raise on a future NumPy; the
    (value, unit=...) form does not.
    """
    match = _TIMEDELTA_SPEC.match(str(spec))
    if not match:
        raise ValueError(f"unsupported timedelta spec: {spec!r}")
    return pd.Timedelta(float(match.group(1)), unit=match.group(2))


def _cleanup_merge_suffixes(df: pd.DataFrame) -> pd.DataFrame:
    """Remove pandas merge suffix leakage such as *_x/*_y."""
    out = df.copy()
    suffix_bases = sorted({c[:-2] for c in out.columns if c.endswith('_x') or c.endswith('_y')})
    for base in suffix_bases:
        candidates: list[str] = []
        for col in [f'{base}_y', f'{base}_x', base]:
            if col in out.columns:
                candidates.append(col)
        if not candidates:
            continue
        if base in CORE_EXTRA_SCORE_COLUMNS or base in CORE_EXTRA_SIGNAL_COLUMNS or base not in out.columns:
            out[base] = _combine_first_ordered(out, candidates)
        else:
            out[base] = out[base].combine_first(_combine_first_ordered(out, candidates))
    drop_cols = [c for c in out.columns if c.endswith('_x') or c.endswith('_y')]
    if drop_cols:
        out = out.drop(columns=drop_cols)
    return out


def _feature_group_name(frame_name: str) -> str:
    return FEATURE_GROUP_OUTPUTS.get(frame_name, frame_name)


def _all_extra_feature_columns(additional_feature_frames: Dict[str, pd.DataFrame] | None) -> set[str]:
    cols: set[str] = set(CORE_EXTRA_SCORE_COLUMNS + CORE_EXTRA_SIGNAL_COLUMNS)
    for frame_name, frame in (additional_feature_frames or {}).items():
        if frame is None or frame.empty:
            continue
        group = _feature_group_name(frame_name)
        for col in frame.columns:
            if col in {'timestamp', '_ts'}:
                continue
            cols.add(col)
            cols.add(f'{group}_{col}')
        cols.add(f'{group}_timestamp')
    return cols


def _strip_broadcast_extra_columns(
    base: pd.DataFrame,
    additional_feature_frames: Dict[str, pd.DataFrame] | None,
) -> pd.DataFrame:
    """Remove latest-snapshot columns that build_feature_frame may broadcast.

    Step162.2: live collector snapshots are useful for the latest ResearchSignal, but
    broadcasting them across all historical price rows creates future-data leakage.
    The matrix builder now strips those broadcast columns first, then re-attaches
    feature data with timestamp-safe joins. In live mode, only the latest row may
    receive the latest available snapshot.
    """
    out = base.copy()
    extra_cols = _all_extra_feature_columns(additional_feature_frames)
    drop_cols = [c for c in out.columns if c in extra_cols or c.endswith('_features_timestamp')]
    if drop_cols:
        out = out.drop(columns=drop_cols)
    return out


def _asof_merge_feature_group(
    base: pd.DataFrame,
    feature: pd.DataFrame,
    *,
    group_name: str,
    tolerance: str | None = None,
) -> pd.DataFrame:
    if base is None or base.empty or feature is None or feature.empty or 'timestamp' not in feature.columns:
        return base

    left = base.copy()
    if '_ts' not in left.columns:
        left['_ts'] = _to_utc_timestamp(left['timestamp'])
    left = left.sort_values('_ts').reset_index(drop=True)

    right = _dedup_sort(feature)
    if right.empty:
        return left

    marker_col = f'{_EXTRA_AVAILABILITY_PREFIX}{group_name}'
    right[marker_col] = True
    right[f'{group_name}_timestamp'] = right['_ts']

    protected = {'open', 'high', 'low', 'close', 'volume', 'ma20', 'ma50', 'ema20', 'ema50', 'atr', 'rsi', 'adx'}
    keep_cols = ['_ts'] + [c for c in right.columns if c not in {'timestamp', '_ts'} and c not in protected]
    right = right[keep_cols]

    canonical_overlap = [
        col for col in right.columns
        if col in left.columns and col in set(CORE_EXTRA_SCORE_COLUMNS + CORE_EXTRA_SIGNAL_COLUMNS)
    ]
    if canonical_overlap:
        left = left.drop(columns=canonical_overlap)

    rename_map: dict[str, str] = {}
    for col in right.columns:
        if col == '_ts':
            continue
        if col in left.columns and col not in set(CORE_EXTRA_SCORE_COLUMNS + CORE_EXTRA_SIGNAL_COLUMNS):
            rename_map[col] = f'{group_name}_{col}'
    right = right.rename(columns=rename_map)

    tol = _timedelta_from_spec(tolerance) if tolerance else None
    merged = pd.merge_asof(left, right.sort_values('_ts'), on='_ts', direction='backward', tolerance=tol)
    return _cleanup_merge_suffixes(merged)


def _apply_latest_feature_to_latest_row(
    matrix: pd.DataFrame,
    additional_feature_frames: Dict[str, pd.DataFrame] | None,
) -> pd.DataFrame:
    """Attach latest optional features only to the latest matrix row.

    This keeps live ResearchSignal useful even when optional API data is newer than
    the latest local price candle, while avoiding the old behavior where the latest
    optional snapshot leaked into every historical row.
    """
    if matrix is None or matrix.empty:
        return matrix
    out = matrix.copy()
    latest_idx = out.index[-1]
    for frame_name, frame in (additional_feature_frames or {}).items():
        if frame is None or frame.empty or 'timestamp' not in frame.columns:
            continue
        group = _feature_group_name(frame_name)
        right = _dedup_sort(frame)
        if right.empty:
            continue
        row = right.iloc[-1]
        out.loc[latest_idx, f'{_EXTRA_AVAILABILITY_PREFIX}{group}'] = True
        out.loc[latest_idx, f'{group}_timestamp'] = row['_ts']
        for col, value in row.items():
            if col in {'timestamp', '_ts'}:
                continue
            if col in {'open', 'high', 'low', 'close', 'volume', 'ma20', 'ma50', 'ema20', 'ema50', 'atr', 'rsi', 'adx'}:
                continue
            # Canonical score/signal columns should remain canonical. Other
            # overlapping fields are also safe here because the latest row is the
            # live signal row, not a historical backtest row.
            out.loc[latest_idx, col] = value
    return _cleanup_merge_suffixes(out)


def _resolve_matrix_mode(mode: str | None, cfg: AppConfig | None) -> Literal['live', 'backtest']:
    requested = mode
    if requested is None and cfg is not None:
        requested = cfg.get('feature_store.research_matrix_mode')
    requested = str(requested or 'live').strip().lower()
    if requested in {'historical', 'history', 'safe', 'backtest'}:
        return 'backtest'
    return 'live'


def _finalize_matrix(out: pd.DataFrame, *, mode: Literal['live', 'backtest']) -> pd.DataFrame:
    out = _cleanup_merge_suffixes(out)

    for col in CORE_EXTRA_SCORE_COLUMNS:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors='coerce').fillna(0.0).clip(-1, 1)

    if 'binance_derivatives_score' in out.columns:
        out['extra_derivatives_score'] = pd.to_numeric(out['binance_derivatives_score'], errors='coerce').fillna(0.0)
    for col in ['exchange_netflow_zscore_30d', 'etf_flow_5d_sum', 'stablecoin_total_mcap_7d_change']:
        if col not in out.columns:
            out[col] = np.nan

    availability_cols = [c for c in out.columns if c.startswith(_EXTRA_AVAILABILITY_PREFIX)]
    if availability_cols:
        out['optional_extra_data_available'] = out[availability_cols].where(out[availability_cols].notna(), False).astype(bool).any(axis=1)
    else:
        score_available = out[CORE_EXTRA_SCORE_COLUMNS].abs().sum(axis=1).fillna(0) > 0
        signal_available = pd.Series(False, index=out.index)
        for col in CORE_EXTRA_SIGNAL_COLUMNS:
            if col in out.columns:
                signal_available = signal_available | out[col].notna()
        out['optional_extra_data_available'] = score_available | signal_available

    out['feature_matrix_mode'] = mode
    out['feature_matrix_version'] = RESEARCH_FEATURE_MATRIX_VERSION

    # Step270: distinguish true neutral data from missing/stale optional-data-neutral
    # and carry collector health metadata into the matrix.
    health_block_cols: list[str] = []
    for group in FEATURE_GROUP_OUTPUTS.values():
        availability_col = f'{_EXTRA_AVAILABILITY_PREFIX}{group}'
        neutral_col = f'{group}_neutral_due_to_missing'
        stale_col = f'{group}_stale'
        status_col = f'{group}_collector_status'
        error_col = f'{group}_collector_error'
        age_col = f'{group}_source_age_sec'
        last_success_col = f'{group}_last_success_utc'
        eligible_col = f'{group}_live_candidate_eligible'
        if availability_col in out.columns:
            available = out[availability_col].where(out[availability_col].notna(), False).astype(bool)
        else:
            available = pd.Series(False, index=out.index)
        if neutral_col not in out.columns:
            out[neutral_col] = ~available
        else:
            out[neutral_col] = out[neutral_col].fillna(~available).astype(bool)
        if stale_col not in out.columns:
            out[stale_col] = False
        else:
            out[stale_col] = out[stale_col].fillna(False).astype(bool)
        if status_col not in out.columns:
            out[status_col] = np.where(available, 'ok', 'missing_optional_neutral')
        else:
            default_status = pd.Series(np.where(available, 'ok', 'missing_optional_neutral'), index=out.index)
            out[status_col] = out[status_col].where(out[status_col].notna(), default_status)
        if error_col not in out.columns:
            out[error_col] = None
        if age_col not in out.columns:
            out[age_col] = np.nan
        if last_success_col not in out.columns:
            out[last_success_col] = None
        if eligible_col not in out.columns:
            out[eligible_col] = available & ~out[neutral_col].astype(bool) & ~out[stale_col].astype(bool)
        else:
            out[eligible_col] = out[eligible_col].fillna(False).astype(bool)
        health_block_cols.extend([neutral_col, stale_col])

    out['missing_optional_data_neutral'] = out[[f'{group}_neutral_due_to_missing' for group in FEATURE_GROUP_OUTPUTS.values() if f'{group}_neutral_due_to_missing' in out.columns]].any(axis=1)
    stale_optional_cols = [f'{group}_stale' for group in FEATURE_GROUP_OUTPUTS.values() if f'{group}_stale' in out.columns]
    out['stale_optional_data'] = out[stale_optional_cols].any(axis=1) if stale_optional_cols else False
    live_eligible_cols = [f'{group}_live_candidate_eligible' for group in FEATURE_GROUP_OUTPUTS.values() if f'{group}_live_candidate_eligible' in out.columns]
    if live_eligible_cols:
        out['live_candidate_eligible'] = out[live_eligible_cols].all(axis=1) & ~out['missing_optional_data_neutral'].astype(bool) & ~out['stale_optional_data'].astype(bool)
    else:
        out['live_candidate_eligible'] = ~(out.get('missing_optional_data_neutral', False).astype(bool))

    # Step268 canonical UTC timestamp: YYYY-MM-DDTHH:MM:SSZ only.
    out['timestamp'] = out['_ts'].dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    drop_cols = ['_ts'] + availability_cols
    return out.drop(columns=[c for c in drop_cols if c in out.columns]).reset_index(drop=True)


def build_research_feature_matrix(
    base_features: pd.DataFrame,
    additional_feature_frames: Dict[str, pd.DataFrame] | None,
    cfg: AppConfig | None = None,
    *,
    mode: str | None = None,
) -> pd.DataFrame:
    """Create the unified Research Engine feature matrix.

    Step258 keeps timestamp-safe matrix modes while feeding ResearchSignal v2:

    - ``mode='backtest'``: optional features are attached only when
      ``feature_timestamp <= price_timestamp`` through backward as-of joins.
    - ``mode='live'``: historical rows still use backward as-of joins, but the
      latest row can receive the latest optional API snapshot so the live
      ResearchSignal can use fresh Binance/DefiLlama data.
    """
    if base_features is None or base_features.empty:
        return pd.DataFrame()

    matrix_mode = _resolve_matrix_mode(mode, cfg)
    out = base_features.copy().reset_index(drop=True)
    if 'timestamp' not in out.columns:
        return out

    out = _strip_broadcast_extra_columns(out, additional_feature_frames)
    out['_ts'] = _to_utc_timestamp(out['timestamp'])
    out = out.dropna(subset=['_ts']).sort_values('_ts').reset_index(drop=True)

    tolerance = None
    if cfg is not None:
        tolerance = cfg.get('feature_store.extra_data_asof_tolerance') or cfg.get('additional_data.feature_asof_tolerance')

    for frame_name, frame in (additional_feature_frames or {}).items():
        group = _feature_group_name(frame_name)
        out = _asof_merge_feature_group(out, frame, group_name=group, tolerance=tolerance)

    if matrix_mode == 'live':
        out = _apply_latest_feature_to_latest_row(out, additional_feature_frames)

    return _finalize_matrix(out, mode=matrix_mode)


def build_research_feature_matrices(
    base_features: pd.DataFrame,
    additional_feature_frames: Dict[str, pd.DataFrame] | None,
    cfg: AppConfig | None = None,
) -> Dict[str, pd.DataFrame]:
    """Build both live and backtest-safe matrices from the same inputs."""
    return {
        'live': build_research_feature_matrix(base_features, additional_feature_frames, cfg, mode='live'),
        'backtest': build_research_feature_matrix(base_features, additional_feature_frames, cfg, mode='backtest'),
    }


def latest_research_feature_snapshot(matrix: pd.DataFrame) -> dict[str, Any]:
    if matrix is None or matrix.empty:
        return {}
    return matrix.iloc[-1].replace({np.nan: None}).to_dict()


def _json_default(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return str(pd.Timestamp(value).tz_convert('UTC') if pd.Timestamp(value).tzinfo else pd.Timestamp(value).tz_localize('UTC'))
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return str(value)


def feature_matrix_sha256(matrix: pd.DataFrame) -> str:
    """Deterministic SHA256 over a canonicalized feature matrix payload."""
    if matrix is None or matrix.empty:
        return sha256_json([])
    canonical = matrix.copy()
    canonical = _cleanup_merge_suffixes(canonical)
    canonical = canonical.reindex(sorted(canonical.columns), axis=1)
    rows = canonical.replace({np.nan: None}).to_dict(orient='records')
    return sha256_json(rows)


def _row_count_for_path(path: Path) -> int | None:
    try:
        if path.suffix.lower() == '.csv':
            return int(len(pd.read_csv(path)))
    except Exception:
        return None
    return None


def _timestamp_range_for_path(path: Path) -> tuple[str | None, str | None]:
    try:
        if path.suffix.lower() == '.csv':
            df = pd.read_csv(path, usecols=lambda c: c == 'timestamp')
            if 'timestamp' not in df.columns or df.empty:
                return None, None
            ts = pd.to_datetime(df['timestamp'], utc=True, errors='coerce').dropna()
            if ts.empty:
                return None, None
            return ts.min().strftime('%Y-%m-%dT%H:%M:%SZ'), ts.max().strftime('%Y-%m-%dT%H:%M:%SZ')
    except Exception:
        return None, None
    return None, None


def build_feature_store_manifest(
    matrix: pd.DataFrame,
    *,
    matrix_path: str | Path | None = None,
    data_snapshot_id: str | None = None,
    source_files: list[str | Path] | None = None,
    feature_snapshot_id: str | None = None,
    data_snapshot_manifest: dict[str, Any] | None = None,
    data_snapshot_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build a Step268 audit manifest for a stored Research Feature Matrix."""
    matrix_hash = feature_matrix_sha256(matrix)
    files: list[dict[str, Any]] = []
    for src in source_files or []:
        path = Path(src)
        exists = path.exists()
        row_count = _row_count_for_path(path) if exists else None
        min_ts, max_ts = _timestamp_range_for_path(path) if exists else (None, None)
        files.append({
            'path': str(path),
            'sha256': sha256_file(path) if exists else None,
            'exists': exists,
            'row_count': row_count,
            'min_timestamp_utc': min_ts,
            'max_timestamp_utc': max_ts,
        })
    data_snapshot_manifest = data_snapshot_manifest or {}
    if data_snapshot_manifest_path is not None:
        path = Path(data_snapshot_manifest_path)
        files.append({
            'path': str(path),
            'sha256': sha256_file(path) if path.exists() else None,
            'exists': path.exists(),
            'row_count': None,
            'min_timestamp_utc': None,
            'max_timestamp_utc': None,
            'artifact_role': 'data_snapshot_manifest',
        })
    source_bundle_payload = [{'path': f['path'], 'sha256': f['sha256']} for f in files]
    source_bundle_hash = data_snapshot_manifest.get('source_bundle_sha256') or sha256_json(source_bundle_payload)
    fallback_used = bool(matrix.get('fallback_used', pd.Series(False, index=matrix.index)).fillna(False).astype(bool).any()) if matrix is not None and not matrix.empty else False
    synthetic_used = bool(matrix.get('synthetic_used', pd.Series(False, index=matrix.index)).fillna(False).astype(bool).any()) if matrix is not None and not matrix.empty else False
    sample_used = bool(matrix.get('sample_used', pd.Series(False, index=matrix.index)).fillna(False).astype(bool).any()) if matrix is not None and not matrix.empty else False
    stale_cols = [c for c in (matrix.columns if matrix is not None else []) if c.endswith('_stale') or c == 'stale']
    stale_source_count = int(matrix[stale_cols].fillna(False).astype(bool).any(axis=0).sum()) if stale_cols and matrix is not None and not matrix.empty else 0
    # Step286: feature_snapshot_id must be stable before and after persistence.
    # The matrix path is storage-location metadata, not lineage identity.
    # Keeping it out of the stable ID payload lets ResearchSignal carry the same
    # feature_snapshot_id during in-memory analysis and after the manifest is written.
    payload = {
        'data_snapshot_id': data_snapshot_id or data_snapshot_manifest.get('data_snapshot_id') or stable_id('data_snapshot', {'feature_matrix_sha256': matrix_hash, 'source_bundle_sha256': source_bundle_hash}, 20),
        'feature_matrix_sha256': matrix_hash,
        'source_bundle_sha256': source_bundle_hash,
    }
    return {
        'feature_snapshot_id': feature_snapshot_id or stable_id('feature_snapshot', payload, 20),
        'data_snapshot_id': payload['data_snapshot_id'],
        'feature_matrix_sha256': matrix_hash,
        'source_bundle_sha256': source_bundle_hash,
        'source_files': files,
        'data_snapshot_manifest_sha256': data_snapshot_manifest.get('data_snapshot_sha256'),
        'data_snapshot_manifest_path': str(data_snapshot_manifest_path) if data_snapshot_manifest_path is not None else data_snapshot_manifest.get('path'),
        'optional_data_health': data_snapshot_manifest.get('optional_data_health', {}),
        'missing_optional_source_count': data_snapshot_manifest.get('missing_optional_source_count'),
        'stale_optional_source_count': data_snapshot_manifest.get('stale_optional_source_count'),
        'live_candidate_eligible': bool(data_snapshot_manifest.get('live_candidate_eligible', not bool(matrix.get('missing_optional_data_neutral', pd.Series(False, index=matrix.index)).fillna(False).astype(bool).any()) if matrix is not None and not matrix.empty else False)),
        'fallback_used': fallback_used,
        'synthetic_used': synthetic_used,
        'sample_used': sample_used,
        'stale_source_count': stale_source_count,
        'created_at_utc': utc_now_canonical(),
        'version': FEATURE_STORE_MANIFEST_VERSION,
        'feature_matrix_version': RESEARCH_FEATURE_MATRIX_VERSION,
        'matrix_path': str(matrix_path) if matrix_path is not None else None,
    }


def write_feature_store_manifest(manifest_path: str | Path, manifest: dict[str, Any]) -> str:
    path = Path(manifest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    return str(path)


def _write_csv(path: Path, df: pd.DataFrame, dedup_subset: list[str] | None = None) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    incoming = _cleanup_merge_suffixes(df.copy())
    if path.exists():
        try:
            existing = _cleanup_merge_suffixes(pd.read_csv(path))
            combined = pd.concat([existing, incoming], ignore_index=True)
        except Exception:
            combined = incoming
    else:
        combined = incoming
    subset = dedup_subset or [c for c in ['timestamp', 'symbol', 'exchange_market', 'timeframe', 'feature_matrix_mode'] if c in combined.columns]
    if subset:
        combined = combined.drop_duplicates(subset=subset, keep='last')
    if 'timestamp' in combined.columns:
        combined = combined.sort_values('timestamp')
    combined.to_csv(path, index=False)
    return str(path)



def _overwrite_csv(path: Path, df: pd.DataFrame) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = _cleanup_merge_suffixes(df.copy())
    if 'timestamp' in out.columns:
        out = out.sort_values('timestamp')
    out.to_csv(path, index=False)
    return str(path)

def _try_write_parquet(path: Path, df: pd.DataFrame) -> str | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _cleanup_merge_suffixes(df).to_parquet(path, index=False)
        return str(path)
    except Exception:
        return None


def persist_feature_store_outputs(
    cfg: AppConfig,
    *,
    feature_frames: Dict[str, pd.DataFrame] | None = None,
    research_feature_matrix: pd.DataFrame | None = None,
    research_feature_matrix_live: pd.DataFrame | None = None,
    research_feature_matrix_backtest: pd.DataFrame | None = None,
    data_snapshot_manifest: dict[str, Any] | None = None,
    data_snapshot_manifest_path: str | Path | None = None,
) -> Dict[str, str]:
    """Persist Step162/162.2 Feature Store outputs.

    ``research_feature_matrix.csv`` is kept as the live alias for backward
    compatibility. Step162.2 also writes explicit live/backtest files to prevent
    accidental use of a live matrix for historical regression tests.
    """
    paths = ensure_storage_dirs(cfg)
    root = paths['features']
    written: Dict[str, str] = {}
    feature_source_files: list[str] = []

    for name, frame in (feature_frames or {}).items():
        if frame is None or frame.empty:
            continue
        output_name = FEATURE_GROUP_OUTPUTS.get(name, name)
        csv_path = root / f'{output_name}.csv'
        written[f'{output_name}_csv'] = _write_csv(csv_path, frame)
        feature_source_files.append(str(csv_path))
        parquet = _try_write_parquet(root / f'{output_name}.parquet', frame)
        if parquet:
            written[f'{output_name}_parquet'] = parquet

    live_matrix = research_feature_matrix_live
    if live_matrix is None:
        live_matrix = research_feature_matrix
    if live_matrix is not None and not live_matrix.empty:
        live_csv = root / 'research_feature_matrix_live.csv'
        written['research_feature_matrix_live_csv'] = _overwrite_csv(live_csv, live_matrix)
        alias_csv = root / 'research_feature_matrix.csv'
        written['research_feature_matrix_csv'] = _overwrite_csv(alias_csv, live_matrix)
        live_manifest = build_feature_store_manifest(live_matrix, matrix_path=live_csv, source_files=feature_source_files, data_snapshot_manifest=data_snapshot_manifest, data_snapshot_manifest_path=data_snapshot_manifest_path)
        written['research_feature_matrix_live_manifest_json'] = write_feature_store_manifest(root / 'research_feature_matrix_manifest_live.json', live_manifest)
        alias_manifest = dict(live_manifest)
        alias_manifest['matrix_path'] = str(alias_csv)
        written['research_feature_matrix_manifest_json'] = write_feature_store_manifest(root / 'research_feature_matrix_manifest.json', alias_manifest)
        parquet = _try_write_parquet(root / 'research_feature_matrix_live.parquet', live_matrix)
        if parquet:
            written['research_feature_matrix_live_parquet'] = parquet

    if research_feature_matrix_backtest is not None and not research_feature_matrix_backtest.empty:
        backtest_csv = root / 'research_feature_matrix_backtest.csv'
        written['research_feature_matrix_backtest_csv'] = _overwrite_csv(backtest_csv, research_feature_matrix_backtest)
        backtest_manifest = build_feature_store_manifest(research_feature_matrix_backtest, matrix_path=backtest_csv, source_files=feature_source_files, data_snapshot_manifest=data_snapshot_manifest, data_snapshot_manifest_path=data_snapshot_manifest_path)
        written['research_feature_matrix_backtest_manifest_json'] = write_feature_store_manifest(root / 'research_feature_matrix_manifest_backtest.json', backtest_manifest)
        parquet = _try_write_parquet(root / 'research_feature_matrix_backtest.parquet', research_feature_matrix_backtest)
        if parquet:
            written['research_feature_matrix_backtest_parquet'] = parquet

    return written

from __future__ import annotations

from typing import Any, Dict
import json
from pathlib import Path

import pandas as pd

from crypto_ai_system.config import AppConfig
from crypto_ai_system.data.collectors import collect_extended_market_bundle
from crypto_ai_system.data.additional_data_collector import collect_additional_data_package
from crypto_ai_system.data.data_source_policy import classify_data_source
from crypto_ai_system.research.research_bot import ResearchBot
from crypto_ai_system.storage.csv_backup import append_df_csv
from crypto_ai_system.storage.latest import write_latest
from crypto_ai_system.storage.paths import ensure_storage_dirs
from crypto_ai_system.storage.raw_store import store_raw_bundle
from crypto_ai_system.storage.normalized_store import store_normalized_frames
from crypto_ai_system.storage.jsonl import append_jsonl
from crypto_ai_system.features.research_feature_matrix import persist_feature_store_outputs
from crypto_ai_system.data.data_snapshot_manifest import build_data_snapshot_manifest, persist_data_snapshot_registries, write_data_snapshot_manifest
from crypto_ai_system.registry.market_thesis_registry import persist_market_thesis_registry_record
from crypto_ai_system.registry.research_signal_registry import persist_research_signal_registry_record
from crypto_ai_system.quality.signal_qa import persist_signal_qa_report, validate_research_signal_quality
from crypto_ai_system.quality.legacy_signal_fallback_blocker import build_legacy_signal_fallback_block_report


def run_raw_to_score_pipeline(cfg: AppConfig) -> Dict[str, Any]:
    paths = ensure_storage_dirs(cfg)
    ohlcv, derivatives, mark, index, orderbook, source = collect_extended_market_bundle(cfg)
    source_policy = classify_data_source(source)
    additional_package = collect_additional_data_package(cfg, persist=False)

    # Persist both raw and normalized views before analysis for reproducibility.
    raw_payload = {
        'ohlcv_raw': ohlcv,
        'derivatives_raw': derivatives,
        'mark_price_raw': mark,
        'index_price_raw': index,
    }
    raw_payload.update(additional_package.raw_frames)
    raw_files = store_raw_bundle(cfg, raw_payload)
    data_snapshot_manifest = build_data_snapshot_manifest(
        raw_payload,
        additional_package.source_status,
        cfg,
        source_files=raw_files,
        optional_data_health=additional_package.optional_data_health,
    )
    data_snapshot_manifest_path = write_data_snapshot_manifest(paths['raw'] / 'data_snapshot_manifest_latest.json', data_snapshot_manifest)
    data_snapshot_registry_outputs = persist_data_snapshot_registries(cfg, data_snapshot_manifest)
    normalized_payload = {
        'candles': ohlcv,
        'derivatives': derivatives,
        'mark_price': mark,
        'index_price': index,
    }
    normalized_payload.update(additional_package.feature_frames)
    normalized_files = store_normalized_frames(cfg, normalized_payload)

    bot = ResearchBot(cfg)
    orderbook = dict(orderbook or {})
    orderbook['additional_data'] = additional_package.to_summary()
    orderbook['additional_feature_snapshot'] = additional_package.feature_snapshot
    orderbook['additional_feature_frames'] = additional_package.feature_frames
    orderbook['data_snapshot_manifest'] = data_snapshot_manifest
    orderbook['optional_data_health'] = additional_package.optional_data_health or {}
    result = bot.analyze(ohlcv, derivatives, mark=mark, index=index, orderbook=orderbook, source=source)
    research_feature_matrix = getattr(bot, 'latest_feature_matrix', pd.DataFrame())
    research_feature_matrix_live = getattr(bot, 'latest_feature_matrix_live', research_feature_matrix)
    research_feature_matrix_backtest = getattr(bot, 'latest_feature_matrix_backtest', pd.DataFrame())
    feature_store_files = persist_feature_store_outputs(
        cfg,
        feature_frames=additional_package.feature_frames,
        research_feature_matrix=research_feature_matrix,
        research_feature_matrix_live=research_feature_matrix_live,
        research_feature_matrix_backtest=research_feature_matrix_backtest,
        data_snapshot_manifest=data_snapshot_manifest,
        data_snapshot_manifest_path=data_snapshot_manifest_path,
    )
    live_feature_manifest = {}
    live_manifest_path = feature_store_files.get('research_feature_matrix_live_manifest_json')
    if live_manifest_path and Path(live_manifest_path).exists():
        live_feature_manifest = json.loads(Path(live_manifest_path).read_text(encoding='utf-8'))

    payload = result.to_dict()
    if live_feature_manifest:
        payload.setdefault('snapshot', {})['feature_snapshot_manifest'] = live_feature_manifest
        for key in [
            'feature_snapshot_id',
            'feature_matrix_sha256',
            'source_bundle_sha256',
            'data_snapshot_id',
            'data_snapshot_manifest_sha256',
            'optional_data_health',
            'missing_optional_source_count',
            'stale_optional_source_count',
            'live_candidate_eligible',
        ]:
            if key in live_feature_manifest:
                payload['snapshot'][key] = live_feature_manifest.get(key)
    payload['source'] = source
    payload['source_policy'] = source_policy.to_dict()
    payload['raw_files'] = raw_files
    payload['normalized_files'] = normalized_files
    payload['feature_store_files'] = feature_store_files
    payload['data_snapshot_manifest'] = data_snapshot_manifest
    payload['data_snapshot_manifest_path'] = data_snapshot_manifest_path
    payload['data_snapshot_registry'] = data_snapshot_registry_outputs
    payload['research_feature_matrix'] = {
        'rows': int(len(research_feature_matrix)) if isinstance(research_feature_matrix, pd.DataFrame) else 0,
        'columns': list(research_feature_matrix.columns) if isinstance(research_feature_matrix, pd.DataFrame) else [],
        'mode': 'live',
        'backtest_rows': int(len(research_feature_matrix_backtest)) if isinstance(research_feature_matrix_backtest, pd.DataFrame) else 0,
        'backtest_columns': list(research_feature_matrix_backtest.columns) if isinstance(research_feature_matrix_backtest, pd.DataFrame) else [],
    }
    payload['additional_data'] = additional_package.to_summary()
    payload.setdefault('snapshot', {})['source'] = source
    payload['snapshot']['data_source'] = source
    payload['snapshot']['data_source_role'] = source_policy.role
    payload['snapshot']['trading_allowed_by_data_source'] = source_policy.trading_allowed
    payload['snapshot']['data_block_reasons'] = source_policy.block_reasons or payload['snapshot'].get('data_block_reasons', [])
    payload['snapshot']['data_snapshot_id'] = data_snapshot_manifest.get('data_snapshot_id')
    payload['snapshot']['data_snapshot_manifest_sha256'] = data_snapshot_manifest.get('data_snapshot_sha256')
    payload['snapshot']['source_bundle_sha256'] = data_snapshot_manifest.get('source_bundle_sha256')
    payload['snapshot']['optional_data_health'] = additional_package.optional_data_health or {}
    payload['snapshot']['missing_optional_source_count'] = data_snapshot_manifest.get('missing_optional_source_count')
    payload['snapshot']['stale_optional_source_count'] = data_snapshot_manifest.get('stale_optional_source_count')
    payload['snapshot']['live_candidate_eligible'] = data_snapshot_manifest.get('live_candidate_eligible')

    signal = payload.get('research_signal') or {}
    if live_feature_manifest:
        signal['feature_snapshot_manifest'] = live_feature_manifest
        for key in [
            'feature_snapshot_id',
            'feature_matrix_sha256',
            'source_bundle_sha256',
            'data_snapshot_id',
            'data_snapshot_manifest_sha256',
            'optional_data_health',
            'missing_optional_source_count',
            'stale_optional_source_count',
            'live_candidate_eligible',
        ]:
            if key in live_feature_manifest:
                signal[key] = live_feature_manifest.get(key)
    signal['data_source'] = source
    signal['data_source_role'] = source_policy.role
    signal['trading_allowed_by_data_source'] = source_policy.trading_allowed
    signal['data_snapshot_id'] = data_snapshot_manifest.get('data_snapshot_id')
    signal['data_snapshot_manifest_sha256'] = data_snapshot_manifest.get('data_snapshot_sha256')
    signal['source_bundle_sha256'] = data_snapshot_manifest.get('source_bundle_sha256')
    signal['optional_data_health'] = additional_package.optional_data_health or {}
    signal['missing_optional_source_count'] = data_snapshot_manifest.get('missing_optional_source_count')
    signal['stale_optional_source_count'] = data_snapshot_manifest.get('stale_optional_source_count')
    signal['live_candidate_eligible'] = data_snapshot_manifest.get('live_candidate_eligible')
    if source_policy.block_reasons:
        signal['block_reasons'] = sorted(set((signal.get('block_reasons') or []) + source_policy.block_reasons))
        signal['entry_allowed'] = False
    payload['research_signal'] = signal
    market_thesis_note = payload.get('market_thesis_note') or {}
    market_thesis_registry_record = {}
    if market_thesis_note:
        market_thesis_registry_record = persist_market_thesis_registry_record(cfg, market_thesis_note)
        payload['market_thesis_registry'] = market_thesis_registry_record

    research_signal_registry_record = persist_research_signal_registry_record(cfg, signal)
    payload['research_signal_registry'] = research_signal_registry_record
    signal_qa_report = validate_research_signal_quality(
        signal,
        registry_record=research_signal_registry_record,
        cfg=cfg,
    )
    signal_qa_registry_record = persist_signal_qa_report(cfg, signal_qa_report)
    legacy_signal_fallback_blocker_report = build_legacy_signal_fallback_block_report(
        research_signal=signal,
        signal_qa_report=signal_qa_report,
        use_research_signal_gate=bool(cfg.get('trading.use_research_signal_gate', True)),
        consumer='raw_score_pipeline',
    )
    payload['signal_qa_report'] = signal_qa_report
    payload['signal_qa_registry'] = signal_qa_registry_record
    payload['legacy_signal_fallback_blocker_report'] = legacy_signal_fallback_blocker_report

    write_latest(paths['latest'] / 'additional_data_snapshot.json', additional_package.to_summary())
    write_latest(paths['latest'] / 'additional_feature_snapshot.json', additional_package.feature_snapshot)
    write_latest(paths['latest'] / 'optional_data_health.json', additional_package.optional_data_health or {})
    write_latest(paths['latest'] / 'data_snapshot_manifest.json', data_snapshot_manifest)
    write_latest(paths['latest'] / 'research_snapshot.json', payload['snapshot'])
    write_latest(paths['latest'] / 'research_signal.json', signal)
    write_latest(paths['latest'] / 'research_signal_registry_record.json', research_signal_registry_record)
    write_latest(paths['latest'] / 'signal_qa_report.json', signal_qa_report)
    write_latest(paths['latest'] / 'signal_qa_registry_record.json', signal_qa_registry_record)
    write_latest(paths['latest'] / 'legacy_signal_fallback_blocker_report.json', legacy_signal_fallback_blocker_report)
    if market_thesis_note:
        write_latest(paths['latest'] / 'market_thesis_note.json', market_thesis_note)
        write_latest(paths['latest'] / 'market_thesis_registry_record.json', market_thesis_registry_record)
    write_latest(paths['latest'] / 'market_condition_snapshot.json', payload['condition'])
    report_path = cfg.root / 'storage' / 'reports' / 'daily' / 'latest_research_report.md'
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(payload['report_markdown'], encoding='utf-8')
    append_df_csv(paths['spreadsheet_backup'] / 'research_scored_history.csv', pd.DataFrame([payload['snapshot']]), dedup_subset=['timestamp'])
    append_df_csv(paths['spreadsheet_backup'] / 'research_signal_history.csv', pd.DataFrame([signal]), dedup_subset=['signal_id'])
    append_jsonl(paths['signals'] / 'research_signal.jsonl', signal)
    return payload

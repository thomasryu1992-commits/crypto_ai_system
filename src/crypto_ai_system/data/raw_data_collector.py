from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from crypto_ai_system.config import AppConfig
from crypto_ai_system.data.collectors import collect_extended_market_bundle
from crypto_ai_system.data.data_contract import validate_derivatives, validate_ohlcv
from crypto_ai_system.data.data_source_policy import classify_data_source
from crypto_ai_system.data.market_snapshot_builder import build_market_snapshot
from crypto_ai_system.data.additional_data_collector import collect_additional_data_package
from crypto_ai_system.data.price_data_loader import load_price_history_bundle, build_multi_timeframe_context
from crypto_ai_system.storage.csv_backup import append_df_csv
from crypto_ai_system.storage.latest import write_latest
from crypto_ai_system.storage.normalized_store import store_normalized_frames
from crypto_ai_system.storage.paths import ensure_storage_dirs
from crypto_ai_system.storage.raw_store import store_raw_bundle
from crypto_ai_system.data.data_snapshot_manifest import build_data_snapshot_manifest, persist_data_snapshot_registries, write_data_snapshot_manifest


def collect_raw_market_package(cfg: AppConfig) -> Dict[str, Any]:
    paths = ensure_storage_dirs(cfg)
    ohlcv, derivatives, mark, index, orderbook, source = collect_extended_market_bundle(cfg)
    source_policy = classify_data_source(source)

    ohlcv, ohlcv_contract = validate_ohlcv(ohlcv, name='collector_ohlcv')
    derivatives, derivatives_contract = validate_derivatives(derivatives, name='collector_derivatives')

    snapshot_obj = build_market_snapshot(ohlcv, derivatives, source=source, mark=mark, index=index, orderbook=orderbook)
    snapshot = snapshot_obj.to_dict() if hasattr(snapshot_obj, 'to_dict') else dict(snapshot_obj)
    snapshot.update({
        'data_source_role': source_policy.role,
        'trading_allowed_by_data_source': source_policy.trading_allowed,
        'data_block_reasons': source_policy.block_reasons,
        'data_contract': {
            'ohlcv': ohlcv_contract.to_dict(),
            'derivatives': derivatives_contract.to_dict(),
            'collector_extra': orderbook.get('data_contract_reports', []) if isinstance(orderbook, dict) else [],
        },
    })

    price_bundle = load_price_history_bundle(cfg)
    price_context = build_multi_timeframe_context(cfg, price_bundle)
    snapshot['price_context'] = price_context

    additional_package = collect_additional_data_package(cfg, persist=False)
    snapshot['additional_data'] = additional_package.to_summary()
    snapshot['additional_features'] = additional_package.feature_snapshot

    bundle: Dict[str, pd.DataFrame] = {
        'ohlcv_raw': ohlcv,
        'derivatives_raw': derivatives,
        'mark_price_raw': mark,
        'index_price_raw': index,
    }
    for tf, price_df in price_bundle.items():
        bundle[f'price_data_{tf}_raw'] = price_df
    bundle.update(additional_package.raw_frames)
    raw_files = store_raw_bundle(cfg, bundle)
    data_snapshot_manifest = build_data_snapshot_manifest(
        bundle,
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

    # Keep spreadsheet-first backup seam alive while raw/normalized stores are canonical.
    append_df_csv(paths['backup'] / 'extended_ohlcv_history.csv', ohlcv)
    append_df_csv(paths['backup'] / 'extended_derivatives_history.csv', derivatives)
    append_df_csv(paths['backup'] / 'extended_mark_price_history.csv', mark)
    append_df_csv(paths['backup'] / 'extended_index_price_history.csv', index)
    for tf, price_df in price_bundle.items():
        append_df_csv(paths['backup'] / f'price_data_{tf}_history.csv', price_df)
    for name, feature_df in additional_package.feature_frames.items():
        append_df_csv(paths['backup'] / f'{name}_history.csv', feature_df)

    data_health = {
        'source': source,
        'source_role': source_policy.role,
        'allow_trading': source_policy.trading_allowed,
        'block_reasons': source_policy.block_reasons,
        'ohlcv_rows': len(ohlcv),
        'derivatives_rows': len(derivatives),
        'price_timeframes_loaded': sorted(price_bundle.keys()),
        'coinalyze_rows': orderbook.get('coinalyze_rows', 0) if isinstance(orderbook, dict) else 0,
        'contracts': snapshot['data_contract'],
        'additional_data': additional_package.to_summary(),
        'additional_feature_rows': {k: len(v) for k, v in additional_package.feature_frames.items()},
        'data_snapshot_registry': data_snapshot_registry_outputs,
        'data_snapshot': {
            'data_snapshot_id': data_snapshot_manifest.get('data_snapshot_id'),
            'data_snapshot_sha256': data_snapshot_manifest.get('data_snapshot_sha256'),
            'source_bundle_sha256': data_snapshot_manifest.get('source_bundle_sha256'),
            'path': data_snapshot_manifest_path,
        },
    }

    write_latest(paths['latest'] / 'price_context_snapshot.json', price_context)
    write_latest(paths['latest'] / 'extended_market_snapshot.json', snapshot)
    write_latest(paths['latest'] / 'market_snapshot.json', snapshot)
    write_latest(paths['latest'] / 'additional_data_snapshot.json', additional_package.to_summary())
    write_latest(paths['latest'] / 'additional_feature_snapshot.json', additional_package.feature_snapshot)
    write_latest(paths['latest'] / 'optional_data_health.json', additional_package.optional_data_health or {})
    write_latest(paths['latest'] / 'data_snapshot_manifest.json', data_snapshot_manifest)
    write_latest(paths['latest'] / 'data_health_snapshot.json', data_health)
    return {
        'snapshot': snapshot,
        'raw_files': raw_files,
        'normalized_files': normalized_files,
        'source': source,
        'rows': len(ohlcv),
        'data_health': data_health,
        'data_snapshot_manifest': data_snapshot_manifest,
        'data_snapshot_manifest_path': data_snapshot_manifest_path,
        'data_snapshot_registry': data_snapshot_registry_outputs,
    }

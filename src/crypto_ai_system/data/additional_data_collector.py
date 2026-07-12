from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict

import pandas as pd

from crypto_ai_system.config import AppConfig
from crypto_ai_system.data.binance_futures_collector import collect_binance_futures_public
from crypto_ai_system.data.coinmetrics_exchange_flow_collector import collect_coinmetrics_exchange_flow
from crypto_ai_system.data.defillama_stablecoin_collector import collect_defillama_stablecoins
from crypto_ai_system.data.farside_etf_flow_collector import collect_farside_etf_flow
from crypto_ai_system.features.additional_data_features import build_additional_feature_frames, build_additional_feature_snapshot
from crypto_ai_system.storage.csv_backup import append_df_csv
from crypto_ai_system.storage.latest import write_latest
from crypto_ai_system.storage.paths import ensure_storage_dirs
from crypto_ai_system.storage.raw_store import store_raw_bundle
from crypto_ai_system.storage.normalized_store import store_normalized_frames
from crypto_ai_system.storage.jsonl import append_jsonl
from crypto_ai_system.features.research_feature_matrix import persist_feature_store_outputs
from crypto_ai_system.data.data_snapshot_manifest import (
    annotate_feature_frames_with_optional_health,
    build_data_snapshot_manifest,
    build_optional_data_health,
    write_data_snapshot_manifest,
)


@dataclass(frozen=True)
class AdditionalDataPackage:
    raw_frames: Dict[str, pd.DataFrame]
    feature_frames: Dict[str, pd.DataFrame]
    feature_snapshot: Dict[str, Any]
    source_status: Dict[str, Any]
    optional_data_health: Dict[str, Any] | None = None
    data_snapshot_manifest: Dict[str, Any] | None = None

    def to_summary(self) -> Dict[str, Any]:
        return {
            'raw_frames': {k: len(v) for k, v in self.raw_frames.items()},
            'feature_frames': {k: len(v) for k, v in self.feature_frames.items()},
            'feature_snapshot_keys': sorted(self.feature_snapshot.keys()),
            'source_status': self.source_status,
            'optional_data_health': self.optional_data_health or {},
            'data_snapshot': {
                'data_snapshot_id': (self.data_snapshot_manifest or {}).get('data_snapshot_id'),
                'data_snapshot_sha256': (self.data_snapshot_manifest or {}).get('data_snapshot_sha256'),
                'source_bundle_sha256': (self.data_snapshot_manifest or {}).get('source_bundle_sha256'),
                'missing_optional_source_count': (self.data_snapshot_manifest or {}).get('missing_optional_source_count'),
                'stale_optional_source_count': (self.data_snapshot_manifest or {}).get('stale_optional_source_count'),
                'live_candidate_eligible': (self.data_snapshot_manifest or {}).get('live_candidate_eligible'),
            },
        }


def collect_additional_data_package(cfg: AppConfig, *, persist: bool = False) -> AdditionalDataPackage:
    enabled = bool(cfg.get('additional_data.enabled', True))
    if not enabled:
        
        status = {'enabled': False}
        health = build_optional_data_health(status, {}, cfg)
        manifest = build_data_snapshot_manifest({}, status, cfg, optional_data_health=health)
        return AdditionalDataPackage(raw_frames={}, feature_frames={}, feature_snapshot={}, source_status=status, optional_data_health=health, data_snapshot_manifest=manifest)

    paths = ensure_storage_dirs(cfg)
    raw_frames: Dict[str, pd.DataFrame] = {}
    network_enabled = bool(cfg.get('additional_data.network_enabled', False))
    status: Dict[str, Any] = {'enabled': True, 'network_enabled': network_enabled}

    collectors = []
    if network_enabled:
        collectors.extend([
            ('binance_futures', collect_binance_futures_public),
            ('coinmetrics_exchange_flow', collect_coinmetrics_exchange_flow),
            ('defillama_stablecoins', collect_defillama_stablecoins),
        ])
    else:
        status['binance_futures'] = {'enabled': False, 'ok': True, 'source': 'binance_futures_public', 'reason': 'network_disabled'}
        status['coinmetrics_exchange_flow'] = {'enabled': False, 'ok': True, 'source': 'coinmetrics_community', 'reason': 'network_disabled'}
        status['defillama_stablecoins'] = {'enabled': False, 'ok': True, 'source': 'defillama_stablecoins', 'reason': 'network_disabled'}

    # Farside ETF flow v1 is CSV/manual input, so it can run in offline mode.
    collectors.append(('farside_etf_flow', collect_farside_etf_flow))

    for name, fn in collectors:
        try:
            result = fn(cfg)
            raw_frames.update(result.frames)
            status[name] = result.status
        except Exception as exc:
            status[name] = {'ok': False, 'error': str(exc)}

    optional_data_health = build_optional_data_health(status, raw_frames, cfg)
    feature_frames = build_additional_feature_frames(raw_frames, cfg)
    feature_frames = annotate_feature_frames_with_optional_health(feature_frames, optional_data_health)
    feature_snapshot = build_additional_feature_snapshot(feature_frames)
    feature_snapshot['optional_data_health'] = optional_data_health
    data_snapshot_manifest = build_data_snapshot_manifest(raw_frames, status, cfg, optional_data_health=optional_data_health)
    package = AdditionalDataPackage(
        raw_frames=raw_frames,
        feature_frames=feature_frames,
        feature_snapshot=feature_snapshot,
        source_status=status,
        optional_data_health=optional_data_health,
        data_snapshot_manifest=data_snapshot_manifest,
    )

    if persist:
        raw_files = store_raw_bundle(cfg, raw_frames)
        data_snapshot_manifest = build_data_snapshot_manifest(raw_frames, status, cfg, source_files=raw_files, optional_data_health=optional_data_health)
        package = AdditionalDataPackage(
            raw_frames=raw_frames,
            feature_frames=feature_frames,
            feature_snapshot=feature_snapshot,
            source_status=status,
            optional_data_health=optional_data_health,
            data_snapshot_manifest=data_snapshot_manifest,
        )
        data_manifest_path = write_data_snapshot_manifest(paths['raw'] / 'data_snapshot_manifest_latest.json', data_snapshot_manifest)
        data_snapshot_registry_outputs = persist_data_snapshot_registries(cfg, data_snapshot_manifest)
        store_normalized_frames(cfg, feature_frames)
        for name, frame in feature_frames.items():
            append_df_csv(paths['features'] / f'{name}.csv', frame)
        feature_store_files = persist_feature_store_outputs(cfg, feature_frames=feature_frames, data_snapshot_manifest=data_snapshot_manifest, data_snapshot_manifest_path=data_manifest_path)
        summary_with_files = package.to_summary()
        summary_with_files['feature_store_files'] = feature_store_files
        summary_with_files['data_snapshot_registry'] = data_snapshot_registry_outputs
        write_latest(paths['latest'] / 'additional_data_snapshot.json', summary_with_files)
        write_latest(paths['latest'] / 'additional_feature_snapshot.json', feature_snapshot)
        write_latest(paths['latest'] / 'optional_data_health.json', optional_data_health)
        write_latest(paths['latest'] / 'data_snapshot_manifest.json', data_snapshot_manifest)
        append_jsonl(paths['logs'] / 'event_log.jsonl', {'type': 'additional_data_collect', **summary_with_files})

    return package


def collect_and_persist_additional_data(cfg: AppConfig) -> Dict[str, Any]:
    package = collect_additional_data_package(cfg, persist=True)
    summary = package.to_summary()
    summary['feature_store_files'] = persist_feature_store_outputs(cfg, feature_frames=package.feature_frames, data_snapshot_manifest=package.data_snapshot_manifest)
    return summary

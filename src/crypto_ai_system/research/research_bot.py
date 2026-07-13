from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict

import pandas as pd

from crypto_ai_system.analysis.market_condition import classify_market_condition
from crypto_ai_system.analysis.market_report import render_market_report
from crypto_ai_system.analysis.score_engine import ScoreEngine
from crypto_ai_system.features.feature_store import build_feature_frame, latest_feature_snapshot
from crypto_ai_system.features.research_feature_matrix import build_feature_store_manifest, build_research_feature_matrices
from crypto_ai_system.data.price_data_loader import build_multi_timeframe_context
from crypto_ai_system.research.research_signal_builder import build_research_signal
from crypto_ai_system.research.market_thesis_note import build_market_thesis_note


def _data_freshness_sec(timestamp: Any) -> float | None:
    try:
        ts = pd.to_datetime(timestamp, utc=True, errors='coerce')
        if pd.isna(ts):
            return None
        now = pd.Timestamp.utcnow()
        if now.tzinfo is None:
            now = now.tz_localize('UTC')
        return float((now - ts).total_seconds())
    except Exception:
        return None


@dataclass
class ResearchResult:
    snapshot: Dict[str, Any]
    condition: Dict[str, Any]
    research_signal: Dict[str, Any]
    market_thesis_note: Dict[str, Any]
    report_markdown: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ResearchBot:
    """Research layer: raw market data -> feature data -> weighted score -> ResearchSignal."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.score_engine = ScoreEngine(weights=cfg.get('research.score_weights'))
        self.latest_feature_matrix = pd.DataFrame()
        self.latest_feature_matrix_live = pd.DataFrame()
        self.latest_feature_matrix_backtest = pd.DataFrame()

    def analyze(self, ohlcv: pd.DataFrame, derivatives: pd.DataFrame, mark=None, index=None, orderbook=None, source: str | None = None) -> ResearchResult:
        base_features = build_feature_frame(ohlcv, derivatives, self.cfg, mark=mark, index=index, orderbook=orderbook)
        additional_feature_frames = {}
        data_snapshot_manifest = {}
        optional_data_health = {}
        if isinstance(orderbook, dict):
            additional_feature_frames = orderbook.get('additional_feature_frames') or {}
            data_snapshot_manifest = orderbook.get('data_snapshot_manifest') or {}
            optional_data_health = orderbook.get('optional_data_health') or data_snapshot_manifest.get('optional_data_health', {})
        matrices = build_research_feature_matrices(base_features, additional_feature_frames, self.cfg)
        features = matrices.get('live', pd.DataFrame())
        backtest_features = matrices.get('backtest', pd.DataFrame())
        scored = self.score_engine.score_frame(features)
        self.latest_feature_matrix = scored
        self.latest_feature_matrix_live = scored
        self.latest_feature_matrix_backtest = self.score_engine.score_frame(backtest_features) if not backtest_features.empty else pd.DataFrame()
        feature_snapshot_manifest = build_feature_store_manifest(
            scored,
            data_snapshot_manifest=data_snapshot_manifest,
        ) if not scored.empty else {}
        snapshot = latest_feature_snapshot(scored)
        if feature_snapshot_manifest:
            snapshot['feature_snapshot_manifest'] = feature_snapshot_manifest
            snapshot['feature_snapshot_id'] = feature_snapshot_manifest.get('feature_snapshot_id')
            snapshot['feature_matrix_sha256'] = feature_snapshot_manifest.get('feature_matrix_sha256')
            snapshot['source_bundle_sha256'] = feature_snapshot_manifest.get('source_bundle_sha256')
            snapshot['data_snapshot_id'] = feature_snapshot_manifest.get('data_snapshot_id')
            snapshot['data_snapshot_manifest_sha256'] = feature_snapshot_manifest.get('data_snapshot_manifest_sha256')
            snapshot['optional_data_health'] = feature_snapshot_manifest.get('optional_data_health', {})
            snapshot['missing_optional_source_count'] = feature_snapshot_manifest.get('missing_optional_source_count')
            snapshot['stale_optional_source_count'] = feature_snapshot_manifest.get('stale_optional_source_count')
            snapshot['live_candidate_eligible'] = feature_snapshot_manifest.get('live_candidate_eligible')
        if source:
            snapshot['data_source'] = source
            snapshot['source'] = source
        else:
            snapshot['data_source'] = snapshot.get('data_source') or snapshot.get('source') or 'UNKNOWN'

        price_context = build_multi_timeframe_context(self.cfg)
        snapshot['price_context'] = price_context
        snapshot['mtf_alignment_score'] = price_context.get('alignment_score', snapshot.get('mtf_alignment_score', 0.0))
        snapshot['mtf_bias'] = price_context.get('bias', snapshot.get('mtf_bias', 'UNKNOWN'))
        snapshot['mtf_available'] = price_context.get('available', snapshot.get('mtf_available', False))
        snapshot['data_freshness_sec'] = _data_freshness_sec(snapshot.get('timestamp'))
        if data_snapshot_manifest:
            snapshot['data_snapshot_id'] = data_snapshot_manifest.get('data_snapshot_id')
            snapshot['data_snapshot_manifest_sha256'] = data_snapshot_manifest.get('data_snapshot_sha256')
            snapshot['source_bundle_sha256'] = data_snapshot_manifest.get('source_bundle_sha256')
            snapshot['optional_data_health'] = optional_data_health
            snapshot['missing_optional_source_count'] = data_snapshot_manifest.get('missing_optional_source_count')
            snapshot['stale_optional_source_count'] = data_snapshot_manifest.get('stale_optional_source_count')
            snapshot['live_candidate_eligible'] = data_snapshot_manifest.get('live_candidate_eligible')

        condition = classify_market_condition(snapshot).to_dict()
        snapshot.update({
            'market_condition': condition['final_condition'],
            'volatility_state': condition['volatility_state'],
            'derivatives_state': condition['derivatives_state'],
            'liquidity_state': condition['liquidity_state'],
        })
        market_thesis_note = build_market_thesis_note(
            snapshot,
            condition,
            self.cfg,
            feature_snapshot_manifest=feature_snapshot_manifest,
        )
        snapshot.update({
            'market_thesis_note_id': market_thesis_note['market_thesis_note_id'],
            'market_thesis_note_sha256': market_thesis_note['market_thesis_note_sha256'],
        })
        research_signal = build_research_signal(snapshot, condition, self.cfg, source=source or snapshot.get('data_source'))
        research_signal['market_thesis_note_id'] = market_thesis_note['market_thesis_note_id']
        research_signal['market_thesis_note_sha256'] = market_thesis_note['market_thesis_note_sha256']
        snapshot.update({
            'research_signal_id': research_signal['signal_id'],
            'entry_side': research_signal['entry_side'],
            'entry_allowed': research_signal['entry_allowed'],
            'entry_confidence': research_signal['entry_confidence'],
            'block_reasons': research_signal['block_reasons'],
            'trading_allowed_by_data_source': research_signal['trading_allowed_by_data_source'],
            'data_source_role': research_signal['data_source_role'],
            'data_block_reasons': research_signal['block_reasons'],
        })
        research_signal['snapshot'] = snapshot
        report = render_market_report(snapshot, research_signal=research_signal)
        return ResearchResult(snapshot=snapshot, condition=condition, research_signal=research_signal, market_thesis_note=market_thesis_note, report_markdown=report)

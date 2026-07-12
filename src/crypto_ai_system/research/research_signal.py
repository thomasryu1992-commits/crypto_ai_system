from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


RESEARCH_SIGNAL_V2_VERSION = 'research_signal_v2_step259_weight_calibration_permission_distribution'
RESEARCH_SIGNAL_LINEAGE_VERSION = 'research_signal_lineage_step268_auditable_chain'


@dataclass
class ResearchSignal:
    signal_id: str
    timestamp: str
    symbol: str
    timeframe: str
    exchange_market: str

    data_source: str
    data_source_role: str
    data_quality_status: str
    data_freshness_sec: float | None
    trading_allowed_by_data_source: bool

    close: float | None
    score_total: float
    score_bias: str
    market_regime: str
    market_condition: str
    mtf_bias: str
    mtf_alignment_score: float

    entry_side: str
    entry_allowed: bool
    entry_confidence: float
    block_reasons: list[str] = field(default_factory=list)

    score_components: dict[str, Any] = field(default_factory=dict)
    features: dict[str, Any] = field(default_factory=dict)
    trade_permission: dict[str, Any] = field(default_factory=dict)
    price_context: dict[str, Any] = field(default_factory=dict)
    scenarios: dict[str, Any] = field(default_factory=dict)
    snapshot: dict[str, Any] = field(default_factory=dict)
    research_signal_id: str | None = None
    signal_version: str = RESEARCH_SIGNAL_LINEAGE_VERSION
    profile_id: str | None = None
    profile_version: str | None = None
    config_version: str | None = None
    data_snapshot_id: str | None = None
    feature_snapshot_id: str | None = None
    feature_matrix_sha256: str | None = None
    source_bundle_sha256: str | None = None
    created_at_utc: str | None = None
    version: str = RESEARCH_SIGNAL_V2_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

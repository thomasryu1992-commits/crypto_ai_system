from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


LIVE_EXECUTION_SOURCES = {'extended'}
RESEARCH_ONLY_PREFIXES = (
    'price_data',
    'sample',
    'synthetic',
    'mock',
    'fallback',
)


@dataclass(frozen=True)
class DataSourceDecision:
    source: str
    role: str
    trading_allowed: bool
    block_reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_data_source(source: str | None, extra_block_reasons: Iterable[str] | None = None) -> DataSourceDecision:
    src = str(source or 'UNKNOWN').strip()
    low = src.lower()
    block_reasons = list(extra_block_reasons or [])

    if low in LIVE_EXECUTION_SOURCES:
        role = 'LIVE_EXECUTION_ELIGIBLE'
        allowed = True
    elif low.startswith(RESEARCH_ONLY_PREFIXES):
        role = 'RESEARCH_BACKTEST_ONLY'
        allowed = False
        block_reasons.append(f'NON_LIVE_EXECUTION_DATA_SOURCE:{src}')
    elif low == 'unknown' or not low:
        role = 'UNKNOWN_SOURCE'
        allowed = False
        block_reasons.append('UNKNOWN_DATA_SOURCE')
    else:
        # Conservative default: a new source must be explicitly approved before order routing.
        role = 'RESEARCH_ONLY_UNAPPROVED_SOURCE'
        allowed = False
        block_reasons.append(f'UNAPPROVED_EXECUTION_DATA_SOURCE:{src}')

    return DataSourceDecision(source=src, role=role, trading_allowed=allowed, block_reasons=sorted(set(block_reasons)))


def attach_source_policy(payload: dict[str, Any], source: str | None = None) -> dict[str, Any]:
    target = dict(payload)
    decision = classify_data_source(source or target.get('data_source') or target.get('source'))
    target['data_source'] = decision.source
    target['data_source_role'] = decision.role
    target['trading_allowed_by_data_source'] = decision.trading_allowed
    target['data_block_reasons'] = decision.block_reasons
    return target

from __future__ import annotations

from crypto_ai_system.config import AppConfig
from crypto_ai_system.data.schemas import MarketIdentity


DEFAULT_SYMBOL_MAP = {
    'BTC-PERP': {
        'extended': {
            'exchange_market': 'BTC-USD',
            'base_asset': 'BTC',
            'quote_asset': 'USD',
            'settlement_asset': 'USDC',
            'contract_type': 'PERPETUAL',
        },
        'coinalyze': {
            'symbol': 'BTCUSDT_PERP.A',
        },
    },
    'ETH-PERP': {
        'extended': {
            'exchange_market': 'ETH-USD',
            'base_asset': 'ETH',
            'quote_asset': 'USD',
            'settlement_asset': 'USDC',
            'contract_type': 'PERPETUAL',
        },
        'coinalyze': {
            'symbol': 'ETHUSDT_PERP.A',
        },
    },
}


def get_market_identity(cfg: AppConfig) -> MarketIdentity:
    canonical = str(cfg.get('data.canonical_symbol', 'BTC-PERP')).upper()
    exchange = str(cfg.get('data.exchange', 'extended')).lower()
    mapping = DEFAULT_SYMBOL_MAP.get(canonical, {}).get(exchange, {})
    return MarketIdentity(
        canonical_symbol=canonical,
        exchange=exchange,
        exchange_market=str(cfg.get('data.exchange_market', mapping.get('exchange_market', 'BTC-USD'))),
        base_asset=str(cfg.get('data.base_asset', mapping.get('base_asset', canonical.split('-')[0]))),
        quote_asset=str(cfg.get('data.quote_asset', mapping.get('quote_asset', 'USD'))),
        settlement_asset=str(cfg.get('data.settlement_asset', mapping.get('settlement_asset', 'USDC'))),
        contract_type=str(cfg.get('data.contract_type', mapping.get('contract_type', 'PERPETUAL'))),
        timeframe=str(cfg.get('data.timeframe', 'PT1H')),
    )


def get_coinalyze_symbol(cfg: AppConfig) -> str:
    explicit = cfg.get('coinalyze.symbol')
    if explicit:
        return str(explicit)
    canonical = str(cfg.get('data.canonical_symbol', 'BTC-PERP')).upper()
    return DEFAULT_SYMBOL_MAP.get(canonical, {}).get('coinalyze', {}).get('symbol', 'BTCUSDT_PERP.A')

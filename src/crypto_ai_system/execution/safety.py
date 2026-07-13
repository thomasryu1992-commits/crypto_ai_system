from __future__ import annotations

import os
from crypto_ai_system.config import AppConfig


def assert_no_live_trading(cfg: AppConfig) -> None:
    cfg_live = bool(cfg.get('safety.live_trading_enabled', False))
    env_live = os.getenv('LIVE_TRADING_ENABLED', 'false').lower() == 'true'
    if cfg_live or env_live:
        raise RuntimeError('Live trading is blocked in Step157E package.')


def assert_no_testnet_signed_orders(cfg: AppConfig) -> None:
    cfg_flag = bool(cfg.get('safety.testnet_signed_order_enabled', False))
    env_flag = os.getenv('TESTNET_SIGNED_ORDER_ENABLED', 'false').lower() == 'true'
    if cfg_flag or env_flag:
        raise RuntimeError('Testnet signed orders are blocked in Step157E package.')

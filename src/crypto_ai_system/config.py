from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    root: Path
    settings: Dict[str, Any]

    def get(self, path: str, default: Any = None) -> Any:
        node: Any = self.settings
        for part in path.split('.'):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    # Same vocabulary as config.settings.env_bool — the same env string must
    # never parse True in one config half and False in the other.
    return str(value).strip().lower() in {'1', 'true', 'yes', 'y', 'on', 'enabled'}


def _to_int(value: Any, default: int) -> int:
    """Same forgiving semantics as config.settings.env_int: accepts "500.0",
    silently falls back on garbage — a malformed operator env var must not
    crash every load_config caller while the flat half quietly defaults."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default



def _load_fallback_profiles(root: Path) -> Dict[str, Any]:
    """Load optional fallback data profile definitions.

    Fallback profiles are intentionally separated from the main runtime settings so
    synthetic/local fallback data cannot be confused with live execution data.
    Missing profile files keep backward-compatible defaults.
    """
    profile_path = root / 'config' / 'fallback_data_profiles.yaml'
    if not profile_path.exists():
        return {
            'profiles': {},
            'default_profile': 'price_data_research',
            'loaded': False,
            'path': str(profile_path),
        }
    data = yaml.safe_load(profile_path.read_text(encoding='utf-8')) or {}
    if not isinstance(data, dict):
        data = {}
    profiles = data.get('profiles') or {}
    if not isinstance(profiles, dict):
        profiles = {}
    default_profile = str(data.get('default_profile') or 'price_data_research')
    return {
        'profiles': profiles,
        'default_profile': default_profile,
        'loaded': True,
        'path': str(profile_path),
    }


# src/crypto_ai_system/config.py -> repo root, mirroring the flat config's
# __file__ anchor. load_config(".") used to resolve against the process cwd,
# so a Task Scheduler entry without "Start in" (cwd=System32) crashed or —
# worse — was swallowed by best-effort callers.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def load_config(project_root: str | Path | None = None) -> AppConfig:
    if project_root in (None, '.'):
        root = _REPO_ROOT
    else:
        root = Path(project_root).resolve()
    env_path = root / '.env'
    if env_path.exists():
        load_dotenv(env_path, override=True)
    settings_path = root / 'config' / 'settings.yaml'
    if not settings_path.exists():
        raise FileNotFoundError(f'Missing settings file: {settings_path}')
    settings = yaml.safe_load(settings_path.read_text(encoding='utf-8')) or {}

    fallback_profiles = _load_fallback_profiles(root)
    settings['fallback_data_profiles'] = fallback_profiles

    data = settings.setdefault('data', {})
    data['fallback_profile'] = os.getenv('FALLBACK_DATA_PROFILE', data.get('fallback_profile', fallback_profiles.get('default_profile', 'price_data_research')))
    data['fallback_profiles_path'] = fallback_profiles.get('path')
    data['exchange'] = os.getenv('DEFAULT_EXCHANGE', data.get('exchange', 'extended'))
    data['canonical_symbol'] = os.getenv('DEFAULT_CANONICAL_SYMBOL', data.get('canonical_symbol', 'BTC-PERP'))
    data['exchange_market'] = os.getenv('DEFAULT_EXCHANGE_MARKET', data.get('exchange_market', 'BTC-USD'))
    data['timeframe'] = os.getenv('DEFAULT_TIMEFRAME', data.get('timeframe', 'PT1H'))
    data['limit'] = _to_int(os.getenv('DEFAULT_LIMIT', data.get('limit', 500)), 500)
    data['allow_sample_fallback'] = _to_bool(os.getenv('ALLOW_SAMPLE_FALLBACK', data.get('allow_sample_fallback', True)))

    extended = settings.setdefault('extended', {})
    extended['environment'] = os.getenv('EXTENDED_ENVIRONMENT', extended.get('environment', 'mainnet'))
    if os.getenv('EXTENDED_API_BASE_URL'):
        extended['base_url'] = os.getenv('EXTENDED_API_BASE_URL')
    extended['api_key'] = os.getenv('EXTENDED_API_KEY', extended.get('api_key'))
    extended['user_agent'] = os.getenv('EXTENDED_USER_AGENT', extended.get('user_agent', 'crypto_ai_system_step157e/0.1'))

    coinalyze = settings.setdefault('coinalyze', {})
    coinalyze['api_key'] = os.getenv('COINALYZE_API_KEY', coinalyze.get('api_key'))
    coinalyze['symbol'] = os.getenv('COINALYZE_SYMBOL', coinalyze.get('symbol', 'BTCUSDT_PERP.A'))
    coinalyze['interval'] = os.getenv('COINALYZE_INTERVAL', coinalyze.get('interval', '1hour'))

    additional = settings.setdefault('additional_data', {})
    additional['enabled'] = _to_bool(os.getenv('ADDITIONAL_DATA_ENABLED', additional.get('enabled', True)))
    additional['timeout_seconds'] = _to_float(os.getenv('ADDITIONAL_DATA_TIMEOUT_SECONDS', additional.get('timeout_seconds', 5)), 5.0)
    additional['network_enabled'] = _to_bool(os.getenv('ADDITIONAL_DATA_NETWORK_ENABLED', additional.get('network_enabled', False)))

    binance_futures = additional.setdefault('binance_futures', {})
    binance_futures['enabled'] = _to_bool(os.getenv('BINANCE_FUTURES_PUBLIC_ENABLED', binance_futures.get('enabled', True)))
    binance_futures['base_url'] = os.getenv('BINANCE_FUTURES_PUBLIC_BASE_URL', binance_futures.get('base_url', 'https://fapi.binance.com'))
    binance_futures['symbol'] = os.getenv('BINANCE_FUTURES_SYMBOL', binance_futures.get('symbol', 'BTCUSDT'))
    binance_futures['pair'] = os.getenv('BINANCE_FUTURES_PAIR', binance_futures.get('pair', binance_futures.get('symbol', 'BTCUSDT')))
    binance_futures['period'] = os.getenv('BINANCE_FUTURES_PERIOD', binance_futures.get('period', '1h'))
    binance_futures['limit'] = _to_int(os.getenv('BINANCE_FUTURES_LIMIT', binance_futures.get('limit', 100)), 100)

    coinmetrics_extra = additional.setdefault('coinmetrics', {})
    coinmetrics_extra['enabled'] = _to_bool(os.getenv('COINMETRICS_ENABLED', coinmetrics_extra.get('enabled', True)))
    coinmetrics_extra['base_url'] = os.getenv('COINMETRICS_BASE_URL', coinmetrics_extra.get('base_url', 'https://community-api.coinmetrics.io/v4'))
    coinmetrics_extra['asset'] = os.getenv('COINMETRICS_ASSET', coinmetrics_extra.get('asset', 'btc'))
    coinmetrics_extra['frequency'] = os.getenv('COINMETRICS_FREQUENCY', coinmetrics_extra.get('frequency', '1d'))
    coinmetrics_extra['page_size'] = _to_int(os.getenv('COINMETRICS_PAGE_SIZE', coinmetrics_extra.get('page_size', 200)), 200)

    farside = additional.setdefault('farside', {})
    farside['enabled'] = _to_bool(os.getenv('FARSIDE_ETF_FLOW_ENABLED', farside.get('enabled', True)))
    farside['csv_path'] = os.getenv('FARSIDE_BTC_ETF_FLOW_CSV', farside.get('csv_path', 'data/raw/etf/farside_btc_etf_flow.csv'))

    defillama = additional.setdefault('defillama', {})
    defillama['enabled'] = _to_bool(os.getenv('DEFILLAMA_STABLECOINS_ENABLED', defillama.get('enabled', True)))
    defillama['base_url'] = os.getenv('DEFILLAMA_STABLECOINS_BASE_URL', defillama.get('base_url', 'https://stablecoins.llama.fi'))

    feature_store = settings.setdefault('feature_store', {})
    feature_store['extra_data_asof_tolerance'] = os.getenv('FEATURE_STORE_EXTRA_DATA_ASOF_TOLERANCE', feature_store.get('extra_data_asof_tolerance', '3D'))
    feature_store['research_matrix_mode'] = os.getenv('RESEARCH_FEATURE_MATRIX_MODE', feature_store.get('research_matrix_mode', 'live'))

    # Single source of truth: the flat config.settings module already resolves
    # these gate values from env (with the canonical defaults) and is consumed
    # directly by decision_engine / signal_engine. Seed the AppConfig side from
    # those resolved constants so a settings.yaml value cannot silently diverge
    # from the flat half and split the pipeline's gate semantics.
    from config import settings as _flat_settings

    trading_cfg = settings.setdefault('trading', {})
    trading_cfg['use_research_signal_gate'] = bool(_flat_settings.USE_RESEARCH_SIGNAL_GATE)
    trading_cfg['risk_level_reduced_position_multiplier'] = float(_flat_settings.RISK_LEVEL_REDUCED_POSITION_MULTIPLIER)
    trading_cfg['risk_level_blocked_position_multiplier'] = float(_flat_settings.RISK_LEVEL_BLOCKED_POSITION_MULTIPLIER)

    backtest = settings.setdefault('backtest', {})
    backtest['maker_fee_bps'] = _to_float(os.getenv('MAKER_FEE_BPS', backtest.get('maker_fee_bps', 0)), 0.0)
    backtest['taker_fee_bps'] = _to_float(os.getenv('TAKER_FEE_BPS', backtest.get('taker_fee_bps', 2.5)), 2.5)
    backtest['slippage_bps'] = _to_float(os.getenv('SLIPPAGE_BPS', backtest.get('slippage_bps', 3)), 3.0)

    # Same single-source rule as the trading gate above: the flat config.settings
    # flags are the ones scripts/check_safety_defaults.py guards in CI, so mirror
    # them here rather than re-resolving env against a possibly-drifting yaml.
    safety = settings.setdefault('safety', {})
    safety['live_trading_enabled'] = bool(_flat_settings.LIVE_TRADING_ENABLED)
    safety['testnet_signed_order_enabled'] = bool(_flat_settings.TESTNET_SIGNED_ORDER_ENABLED)

    return AppConfig(root=root, settings=settings)

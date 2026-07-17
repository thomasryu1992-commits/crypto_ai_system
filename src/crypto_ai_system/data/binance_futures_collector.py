from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict

import pandas as pd
import requests

from crypto_ai_system.config import AppConfig

# Venue cap on rows per /fapi/v1/klines call; deeper history must be paged.
PUBLIC_KLINE_PAGE_LIMIT = 1500
# Venue cap on rows per /fapi/v1/fundingRate call.
PUBLIC_FUNDING_PAGE_LIMIT = 1000


def _utc_now_iso() -> str:
    return pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M:%S+00:00')


def _to_timestamp(value: Any) -> str:
    try:
        if value is None or value == '':
            return _utc_now_iso()
        v = float(value)
        unit = 'ms' if v > 10_000_000_000 else 's'
        return pd.to_datetime(v, unit=unit, utc=True).strftime('%Y-%m-%d %H:%M:%S+00:00')
    except Exception:
        ts = pd.to_datetime(value, utc=True, errors='coerce')
        if pd.isna(ts):
            return _utc_now_iso()
        return ts.strftime('%Y-%m-%d %H:%M:%S+00:00')


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == '':
            return default
        return float(value)
    except Exception:
        return default


@dataclass(frozen=True)
class BinanceFuturesCollectorResult:
    frames: Dict[str, pd.DataFrame]
    status: Dict[str, Any]


class BinanceFuturesPublicClient:
    """Read-only Binance USD-M Futures public market data collector.

    The class intentionally uses public endpoints only. It never signs requests and
    cannot place orders. The collected tables are designed to enrich research and
    execution filters with faster derivatives positioning data.
    """

    def __init__(self, base_url: str = 'https://fapi.binance.com', timeout_seconds: float = 5.0) -> None:
        self.base_url = base_url.rstrip('/')
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'crypto-ai-system-binance-futures-public/1.0'})

    @classmethod
    def from_config(cls, cfg: AppConfig) -> 'BinanceFuturesPublicClient':
        base = str(cfg.get('additional_data.binance_futures.base_url', 'https://fapi.binance.com'))
        timeout = float(cfg.get('additional_data.binance_futures.timeout_seconds', cfg.get('additional_data.timeout_seconds', 5)))
        return cls(base_url=base, timeout_seconds=timeout)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f'{self.base_url}{path}'
        response = self.session.get(url, params=params or {}, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()

    def open_interest_now(self, symbol: str) -> pd.DataFrame:
        payload = self._get('/fapi/v1/openInterest', {'symbol': symbol})
        return pd.DataFrame([{
            'timestamp': _to_timestamp(payload.get('time')),
            'symbol': symbol,
            'open_interest': _number(payload.get('openInterest'), 0.0),
            'source': 'binance_futures_public',
        }])

    def open_interest_hist(self, symbol: str, period: str, limit: int) -> pd.DataFrame:
        payload = self._get('/futures/data/openInterestHist', {'symbol': symbol, 'period': period, 'limit': limit})
        rows = []
        for item in payload or []:
            oi = _number(item.get('sumOpenInterest'), 0.0)
            oi_value = _number(item.get('sumOpenInterestValue'), 0.0)
            rows.append({
                'timestamp': _to_timestamp(item.get('timestamp')),
                'symbol': symbol,
                'open_interest': oi,
                'open_interest_value': oi_value,
                'source': 'binance_futures_public',
            })
        return pd.DataFrame(rows)

    def _funding_rows(self, payload: Any, symbol: str) -> list[dict[str, Any]]:
        rows = []
        for item in payload or []:
            rows.append({
                'timestamp': _to_timestamp(item.get('fundingTime')),
                'funding_time_ms': int(item.get('fundingTime')),
                'symbol': symbol,
                'funding_rate': _number(item.get('fundingRate'), 0.0),
                'mark_price': _number(item.get('markPrice')),
                'source': 'binance_futures_public',
            })
        return rows

    def funding_rate(self, symbol: str, limit: int) -> pd.DataFrame:
        payload = self._get('/fapi/v1/fundingRate', {'symbol': symbol, 'limit': limit})
        frame = pd.DataFrame(self._funding_rows(payload, symbol))
        return frame.drop(columns=['funding_time_ms'], errors='ignore')

    def funding_rate_history(
        self, symbol: str, records: int, *, page_limit: int = PUBLIC_FUNDING_PAGE_LIMIT
    ) -> pd.DataFrame:
        """Fetch up to ``records`` funding events, paging backward past the cap.

        Funding is charged every 8h, so one 1000-row page is ~11 months and a few
        pages cover the venue's whole history — years of real funding for the
        backtest. Same backward-paging discipline as ``klines_history``: walk
        ``endTime`` to just before the oldest event seen, stop when the venue
        runs out, refuse to spin without backward progress.
        """
        collected: list[dict[str, Any]] = []
        end_time: int | None = None
        oldest_seen: int | None = None

        while len(collected) < records:
            params: dict[str, Any] = {
                'symbol': symbol,
                'limit': min(page_limit, records - len(collected)),
            }
            if end_time is not None:
                params['endTime'] = end_time
            payload = self._get('/fapi/v1/fundingRate', params)
            rows = self._funding_rows(payload, symbol)
            if not rows:
                break

            collected.extend(rows)
            page_oldest = min(int(r['funding_time_ms']) for r in rows)
            if oldest_seen is not None and page_oldest >= oldest_seen:
                break
            oldest_seen = page_oldest
            end_time = page_oldest - 1
            # No short-page early exit: this endpoint returns fewer rows than
            # ``limit`` even mid-history (500 against a 1000 ask), so exhaustion
            # is detected only by an empty page or no backward progress.

        if not collected:
            return pd.DataFrame()
        frame = pd.DataFrame(collected)
        frame = frame.drop_duplicates(subset='funding_time_ms').sort_values('funding_time_ms')
        return frame.drop(columns=['funding_time_ms']).reset_index(drop=True)

    def premium_index(self, symbol: str) -> pd.DataFrame:
        payload = self._get('/fapi/v1/premiumIndex', {'symbol': symbol})
        return pd.DataFrame([{
            'timestamp': _to_timestamp(payload.get('time')),
            'symbol': symbol,
            'mark_price': _number(payload.get('markPrice')),
            'index_price': _number(payload.get('indexPrice')),
            'estimated_settle_price': _number(payload.get('estimatedSettlePrice')),
            'last_funding_rate': _number(payload.get('lastFundingRate')),
            'interest_rate': _number(payload.get('interestRate')),
            'next_funding_time': _to_timestamp(payload.get('nextFundingTime')) if payload.get('nextFundingTime') else None,
            'source': 'binance_futures_public',
        }])

    def taker_buy_sell(self, symbol: str, period: str, limit: int) -> pd.DataFrame:
        payload = self._get('/futures/data/takerlongshortRatio', {'symbol': symbol, 'period': period, 'limit': limit})
        rows = []
        for item in payload or []:
            rows.append({
                'timestamp': _to_timestamp(item.get('timestamp')),
                'symbol': symbol,
                'taker_buy_sell_ratio': _number(item.get('buySellRatio'), 1.0),
                'taker_buy_volume': _number(item.get('buyVol'), 0.0),
                'taker_sell_volume': _number(item.get('sellVol'), 0.0),
                'source': 'binance_futures_public',
            })
        return pd.DataFrame(rows)

    def long_short_ratio(self, endpoint: str, symbol: str, period: str, limit: int, output_col: str) -> pd.DataFrame:
        payload = self._get(endpoint, {'symbol': symbol, 'period': period, 'limit': limit})
        rows = []
        for item in payload or []:
            rows.append({
                'timestamp': _to_timestamp(item.get('timestamp')),
                'symbol': symbol,
                output_col: _number(item.get('longShortRatio'), 1.0),
                f'{output_col}_long_account': _number(item.get('longAccount')),
                f'{output_col}_short_account': _number(item.get('shortAccount')),
                'source': 'binance_futures_public',
            })
        return pd.DataFrame(rows)

    def basis(self, pair: str, contract_type: str, period: str, limit: int) -> pd.DataFrame:
        payload = self._get('/futures/data/basis', {'pair': pair, 'contractType': contract_type, 'period': period, 'limit': limit})
        rows = []
        for item in payload or []:
            rows.append({
                'timestamp': _to_timestamp(item.get('timestamp')),
                'symbol': pair,
                'basis': _number(item.get('basis'), 0.0),
                'basis_rate': _number(item.get('basisRate'), 0.0),
                'futures_price': _number(item.get('futuresPrice')),
                'index_price': _number(item.get('indexPrice')),
                'source': 'binance_futures_public',
            })
        return pd.DataFrame(rows)

    def orderbook_depth(self, symbol: str, limit: int = 100) -> pd.DataFrame:
        payload = self._get('/fapi/v1/depth', {'symbol': symbol, 'limit': limit})
        bids = payload.get('bids') or []
        asks = payload.get('asks') or []
        bid_depth = sum((_number(q, 0.0) or 0.0) for _p, q in bids)
        ask_depth = sum((_number(q, 0.0) or 0.0) for _p, q in asks)
        best_bid = _number(bids[0][0]) if bids else None
        best_ask = _number(asks[0][0]) if asks else None
        mid = ((best_bid or 0.0) + (best_ask or 0.0)) / 2 if best_bid and best_ask else None
        spread_bps = ((best_ask - best_bid) / mid * 10000) if mid else None
        imbalance = (bid_depth - ask_depth) / (bid_depth + ask_depth) if (bid_depth + ask_depth) else 0.0
        return pd.DataFrame([{
            'timestamp': _utc_now_iso(),
            'symbol': symbol,
            'orderbook_bid_depth': bid_depth,
            'orderbook_ask_depth': ask_depth,
            'orderbook_imbalance': imbalance,
            'bid_price': best_bid,
            'ask_price': best_ask,
            'spread_bps': spread_bps,
            'last_update_id': payload.get('lastUpdateId'),
            'source': 'binance_futures_public',
        }])

    def _kline_rows(self, payload: Any, symbol: str, interval: str) -> list[dict[str, Any]]:
        rows = []
        for item in payload or []:
            rows.append({
                'timestamp': _to_timestamp(item[0]),
                'open_time_ms': int(item[0]),
                'symbol': symbol,
                'exchange': 'binance_futures',
                'exchange_market': symbol,
                'timeframe': interval,
                'open': _number(item[1], 0.0),
                'high': _number(item[2], 0.0),
                'low': _number(item[3], 0.0),
                'close': _number(item[4], 0.0),
                'volume': _number(item[5], 0.0),
                'source': 'binance_futures_public',
            })
        return rows

    def klines(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        payload = self._get('/fapi/v1/klines', {'symbol': symbol, 'interval': interval, 'limit': limit})
        frame = pd.DataFrame(self._kline_rows(payload, symbol, interval))
        return frame.drop(columns=['open_time_ms'], errors='ignore')

    def klines_history(
        self, symbol: str, interval: str, bars: int, *, page_limit: int = PUBLIC_KLINE_PAGE_LIMIT
    ) -> pd.DataFrame:
        """Fetch up to ``bars`` klines, paging backward past the per-call cap.

        One /fapi/v1/klines call returns at most 1500 rows, which is only ~2
        months of 1h candles — far too few for a strategy to clear a meaningful
        trade-count gate. Each page walks ``endTime`` to just before the oldest
        row seen so far, so no interval arithmetic is needed and gaps in the
        venue's history cannot desynchronise the paging.

        Stops early when the venue runs out of history, and refuses to loop if a
        page fails to move backward. The returned frame is de-duplicated and
        oldest-first, matching ``klines``.
        """
        collected: list[dict[str, Any]] = []
        end_time: int | None = None
        oldest_seen: int | None = None

        while len(collected) < bars:
            params: dict[str, Any] = {
                'symbol': symbol,
                'interval': interval,
                'limit': min(page_limit, bars - len(collected)),
            }
            if end_time is not None:
                params['endTime'] = end_time
            payload = self._get('/fapi/v1/klines', params)
            rows = self._kline_rows(payload, symbol, interval)
            if not rows:
                break

            collected.extend(rows)
            page_oldest = min(int(r['open_time_ms']) for r in rows)
            if oldest_seen is not None and page_oldest >= oldest_seen:
                break  # no backward progress; stop rather than spin
            oldest_seen = page_oldest
            end_time = page_oldest - 1

            if len(rows) < params['limit']:
                break  # venue exhausted its history

        if not collected:
            return pd.DataFrame()
        frame = pd.DataFrame(collected)
        frame = frame.drop_duplicates(subset='open_time_ms').sort_values('open_time_ms')
        return frame.drop(columns=['open_time_ms']).reset_index(drop=True)


def collect_binance_futures_public(cfg: AppConfig) -> BinanceFuturesCollectorResult:
    enabled = bool(cfg.get('additional_data.binance_futures.enabled', True))
    if not enabled:
        return BinanceFuturesCollectorResult(frames={}, status={'enabled': False, 'ok': True, 'source': 'binance_futures_public'})

    client = BinanceFuturesPublicClient.from_config(cfg)
    symbol = str(cfg.get('additional_data.binance_futures.symbol', 'BTCUSDT'))
    pair = str(cfg.get('additional_data.binance_futures.pair', symbol))
    contract_type = str(cfg.get('additional_data.binance_futures.contract_type', 'PERPETUAL'))
    period = str(cfg.get('additional_data.binance_futures.period', '1h'))
    kline_interval = str(cfg.get('additional_data.binance_futures.kline_interval', '1h'))
    limit = int(cfg.get('additional_data.binance_futures.limit', 100))
    depth_limit = int(cfg.get('additional_data.binance_futures.depth_limit', 100))
    request_pause = float(cfg.get('additional_data.binance_futures.request_pause_seconds', 0.05))
    abort_after_errors = int(cfg.get('additional_data.binance_futures.abort_after_errors', 2))

    calls: list[tuple[str, Any]] = [
        ('binance_open_interest_now', lambda: client.open_interest_now(symbol)),
        ('binance_open_interest_hist', lambda: client.open_interest_hist(symbol, period, limit)),
        ('binance_funding_rate', lambda: client.funding_rate(symbol, min(limit, 1000))),
        ('binance_mark_price', lambda: client.premium_index(symbol)),
        ('binance_taker_buy_sell_volume', lambda: client.taker_buy_sell(symbol, period, limit)),
        ('binance_global_long_short_ratio', lambda: client.long_short_ratio('/futures/data/globalLongShortAccountRatio', symbol, period, limit, 'global_long_short_ratio')),
        ('binance_top_trader_account_ratio', lambda: client.long_short_ratio('/futures/data/topLongShortAccountRatio', symbol, period, limit, 'top_trader_account_long_short_ratio')),
        ('binance_top_trader_position_ratio', lambda: client.long_short_ratio('/futures/data/topLongShortPositionRatio', symbol, period, limit, 'top_trader_position_long_short_ratio')),
        ('binance_basis', lambda: client.basis(pair, contract_type, period, limit)),
        ('binance_orderbook_depth', lambda: client.orderbook_depth(symbol, depth_limit)),
        ('binance_klines', lambda: client.klines(symbol, kline_interval, min(limit, 1000))),
    ]

    frames: Dict[str, pd.DataFrame] = {}
    errors: Dict[str, str] = {}
    consecutive_errors = 0
    for name, fn in calls:
        try:
            frame = fn()
            consecutive_errors = 0
            if isinstance(frame, pd.DataFrame) and not frame.empty:
                frames[name] = frame.sort_values('timestamp').reset_index(drop=True) if 'timestamp' in frame.columns else frame
        except Exception as exc:
            consecutive_errors += 1
            errors[name] = str(exc)
            if abort_after_errors > 0 and consecutive_errors >= abort_after_errors and not frames:
                errors['aborted'] = f'aborted_after_{consecutive_errors}_consecutive_errors'
                break
        if request_pause > 0:
            time.sleep(request_pause)

    return BinanceFuturesCollectorResult(
        frames=frames,
        status={
            'enabled': True,
            'ok': bool(frames),
            'source': 'binance_futures_public',
            'frames': {k: len(v) for k, v in frames.items()},
            'errors': errors,
        },
    )

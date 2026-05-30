import asyncio
import logging
import time
from typing import Optional, List, Any
from datetime import datetime, timezone

from ..api.mexc_client import MEXCRestClient
from ..api.exceptions import MEXCAPIException
from ..models.market_data import MarketData
from .market_cap_cache import MarketCapCache

logger = logging.getLogger(__name__)


class DataAggregator:
    """Aggregates all market data from MEXC APIs into a single MarketData object.

    Usage:
        async with DataAggregator(mexc_client, mc_cache) as agg:
            data = await agg.aggregate('BTCUSDT')

        # Or standalone (creates its own client):
        async with DataAggregator() as agg:
            data = await agg.aggregate('BTCUSDT')
    """

    # Number of 1h klines to fetch: 48h of data
    KLINE_COUNT = 48
    # Recent trades to fetch for aggression calculation
    TRADES_LIMIT = 1000
    # ms window for aggression_5m
    AGGRESSION_5M_WINDOW_MS = 5 * 60 * 1000
    # ms window for aggression_2h
    AGGRESSION_2H_WINDOW_MS = 2 * 60 * 60 * 1000
    # ATR period
    ATR_PERIOD = 14

    def __init__(
        self,
        mexc_client: Optional[MEXCRestClient] = None,
        mc_cache: Optional[MarketCapCache] = None,
    ) -> None:
        self._client = mexc_client
        self._mc_cache = mc_cache
        self._own_client = mexc_client is None
        self._oi_last_known: dict[str, float] = {}

    async def __aenter__(self) -> 'DataAggregator':
        if self._own_client:
            self._client = MEXCRestClient()
            await self._client.__aenter__()
        return self

    async def __aexit__(self, *args) -> None:
        if self._own_client and self._client:
            await self._client.__aexit__(*args)
            self._client = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def aggregate(self, symbol: str) -> MarketData:
        """Fetch all data for a symbol and return a populated MarketData."""
        base_symbol = symbol.replace('_USDT', '').replace('USDT', '').upper()

        # run all primary API calls concurrently; individual failures return None
        ticker, oi_data, funding_data, ob_data, klines, trades = await asyncio.gather(
            self._safe(self._client.get_ticker_24h, symbol),
            self._safe(self._client.get_open_interest, symbol),
            self._safe(self._client.get_funding_rate, symbol),
            self._safe(self._client.get_order_book, symbol, 20),
            self._safe(self._client.get_klines, symbol, '1h', self.KLINE_COUNT),
            self._safe(self._client.get_recent_trades, symbol, self.TRADES_LIMIT),
        )
        # futures fallback — runs after gather so _contract_size_cache is already populated
        if not klines:
            klines = await self._safe(self._client.get_futures_klines, symbol, '1h', self.KLINE_COUNT) or []
        if not trades:
            trades = await self._safe(self._client.get_futures_deals, symbol, self.TRADES_LIMIT) or []

        price = self._parse_price(ticker)
        if (price is None or price <= 0) and oi_data:
            price = self._float(oi_data, 'lastPrice')
        if price is None or price <= 0:
            raise ValueError(f'Cannot get valid price for {symbol}')

        oi_usd = self._parse_oi(oi_data)
        if oi_usd and oi_usd > 0:
            self._oi_last_known[symbol] = oi_usd
        elif self._oi_last_known.get(symbol):
            logger.debug(f'OI=0 for {symbol}, using last known: ${self._oi_last_known[symbol]:,.0f}')
            oi_usd = self._oi_last_known[symbol]
        funding_rate = self._parse_funding(funding_data)
        kline_metrics = self._parse_klines(klines, price)
        aggression = self._parse_aggression(trades)
        ob_metrics = self._parse_order_book(ob_data, price)
        market_cap, fdv, circulating_supply = await self._fetch_market_cap(base_symbol, price)

        return MarketData(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            price=price,
            high_24h=self._float(ticker, 'highPrice') if ticker else None,
            low_24h=self._float(ticker, 'lowPrice') if ticker else None,
            volume_24h=(self._float(oi_data, 'amount24') if oi_data else None) or self._float(ticker, 'quoteVolume') or 0.0,
            price_change_24h=self._float(ticker, 'priceChangePercent') if ticker else None,
            open_interest_usd=oi_usd or 0.0,
            funding_rate=funding_rate or 0.0,
            market_cap_usd=market_cap,
            fdv=fdv,
            circulating_supply=circulating_supply,
            # kline-derived
            price_change_1h=kline_metrics.get('price_change_1h'),
            price_change_4h=kline_metrics.get('price_change_4h'),
            volume_1h=kline_metrics.get('volume_1h'),
            avg_volume_1h=kline_metrics.get('avg_volume_1h'),
            atr=kline_metrics.get('atr'),
            vci=kline_metrics.get('vci'),
            cfc=kline_metrics.get('cfc', 0),
            vwap=kline_metrics.get('vwap'),
            # aggression
            buy_volume_5m=aggression.get('buy_5m'),
            sell_volume_5m=aggression.get('sell_5m'),
            trade_count_5m=aggression.get('trade_count_5m'),
            trade_count_2h=aggression.get('trade_count_2h'),
            buy_volume_2h=aggression.get('buy_2h'),
            sell_volume_2h=aggression.get('sell_2h'),
            # order book
            ob_bid_total=ob_metrics.get('bid_total'),
            ob_ask_total=ob_metrics.get('ask_total'),
            ob_bid_wall=ob_metrics.get('bid_wall'),
            ob_ask_wall=ob_metrics.get('ask_wall'),
            ob_t1_bid_vol=ob_metrics.get('t1_bid'),
            ob_t1_ask_vol=ob_metrics.get('t1_ask'),
            ob_t2_bid_vol=ob_metrics.get('t2_bid'),
            ob_t2_ask_vol=ob_metrics.get('t2_ask'),
            ob_spread_pct=ob_metrics.get('spread_pct'),
        )

    # ------------------------------------------------------------------
    # Market cap
    # ------------------------------------------------------------------

    async def _fetch_market_cap(self, base_symbol: str, price: float):
        """Returns (market_cap, fdv, circulating_supply). Uses cache, then fallback."""
        if self._mc_cache:
            entry = self._mc_cache.get(base_symbol)
            if entry:
                return entry.get('market_cap'), entry.get('fdv'), entry.get('circulating_supply')
            # try fallback lookup for cache miss
            mc = await self._mc_cache.lookup_single(base_symbol)
            if mc:
                entry = self._mc_cache.get(base_symbol) or {}
                return mc, entry.get('fdv'), entry.get('circulating_supply')
        return None, None, None

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    def _parse_price(self, ticker) -> Optional[float]:
        if not ticker:
            return None
        for field in ('lastPrice', 'price', 'closePrice'):
            val = self._float(ticker, field)
            if val and val > 0:
                return val
        return None

    def _parse_oi(self, oi_data) -> Optional[float]:
        if not oi_data:
            return None
        try:
            return float(oi_data.get('openInterestValue', 0) or 0)
        except (TypeError, ValueError):
            return None

    def _parse_funding(self, funding_data) -> Optional[float]:
        if not funding_data:
            return 0.0
        data = funding_data.get('data', funding_data)
        if isinstance(data, dict):
            for field in ('fundingRate', 'rate'):
                val = self._float(data, field)
                if val is not None:
                    return val
        return 0.0

    def _parse_klines(self, klines, current_price: float) -> dict:
        """Parse 1h klines into price changes, volume metrics, and ATR."""
        result = {}
        if not klines or not isinstance(klines, list) or len(klines) < 5:
            return result

        try:
            closes = [float(k[4]) for k in klines]
            highs = [float(k[2]) for k in klines]
            lows = [float(k[3]) for k in klines]
            quote_vols = [float(k[7]) for k in klines]

            n = len(closes)

            # price changes relative to current price
            if n >= 2 and closes[-2] > 0:
                result['price_change_1h'] = (current_price - closes[-2]) / closes[-2] * 100
            if n >= 5 and closes[-5] > 0:
                result['price_change_4h'] = (current_price - closes[-5]) / closes[-5] * 100

            # volume: last completed candle and 24h average of completed candles
            if n >= 2:
                result['volume_1h'] = quote_vols[-2]  # last fully closed candle
            if n >= 25:
                avg_window = quote_vols[-25:-1]  # 24 completed candles before current
                result['avg_volume_1h'] = sum(avg_window) / len(avg_window) if avg_window else None

            # ATR (14-period EMA of True Range)
            result['atr'] = self._calculate_atr(highs, lows, closes, self.ATR_PERIOD)

            # VCI (Volatility Compression Index = ATR_5 / ATR_20)
            # Duplicate TR calculation here — _calculate_atr() doesn't expose tr_values.
            # range(1, n-1) excludes current open candle so its partial range doesn't
            # inflate ATR_5 (which weights it as 1/5 of the window).
            if n >= 22:
                tr_vals = [
                    max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
                    for i in range(1, n - 1)
                ]
                if len(tr_vals) >= 20:
                    atr_5 = sum(tr_vals[-5:]) / 5
                    atr_20 = sum(tr_vals[-20:]) / 20
                    if atr_20 > 0:
                        result['vci'] = atr_5 / atr_20

            # CFC (Consecutive Flat Candles — count candles with range < 1.5% from tail)
            # Exclude current open candle (index -1) — same as VCI — its partial range
            # would be artificially narrow early in the candle, giving a false flat count.
            cfc = 0
            for h, l, c in reversed(list(zip(highs[-11:-1], lows[-11:-1], closes[-11:-1]))):
                if c > 0 and (h - l) / c * 100 < 1.5:
                    cfc += 1
                else:
                    break
            result['cfc'] = cfc

            # VWAP (24h using typical price (H+L+C)/3 × quote volume, last 24 closed candles)
            if n >= 25:
                vwap_klines = klines[-25:-1]  # 24 closed candles (exclude current open candle)
                total_vol = sum(float(k[7]) for k in vwap_klines)
                if total_vol > 0:
                    typical_prices = [(float(k[2]) + float(k[3]) + float(k[4])) / 3 for k in vwap_klines]
                    vols = [float(k[7]) for k in vwap_klines]
                    result['vwap'] = sum(tp * v for tp, v in zip(typical_prices, vols)) / total_vol

        except (IndexError, TypeError, ValueError, ZeroDivisionError) as e:
            logger.debug(f'Kline parse error: {e}')

        return result

    def _calculate_atr(self, highs: List[float], lows: List[float], closes: List[float], period: int) -> Optional[float]:
        if len(highs) < period + 1:
            return None
        tr_values = []
        for i in range(1, len(highs)):
            prev_close = closes[i - 1]
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - prev_close),
                abs(lows[i] - prev_close),
            )
            tr_values.append(tr)
        if len(tr_values) < period:
            return None
        # seed with simple average of first `period` values
        atr = sum(tr_values[:period]) / period
        multiplier = 2.0 / (period + 1)
        for tr in tr_values[period:]:
            atr = tr * multiplier + atr * (1 - multiplier)
        return atr if atr > 0 else None

    def _parse_aggression(self, trades) -> dict:
        """Derive buy/sell volume from recent trades by timestamp windows.

        Returns buy_5m, sell_5m (last 5 min) and buy_2h, sell_2h (last 2h).
        Both windows filter by trade timestamp, so results reflect actual time
        coverage of the 1000-trade sample — not a fixed duration guarantee.
        """
        result = {}
        if not trades or not isinstance(trades, list):
            return result

        now_ms = int(time.time() * 1000)
        cutoff_5m = now_ms - self.AGGRESSION_5M_WINDOW_MS
        cutoff_2h = now_ms - self.AGGRESSION_2H_WINDOW_MS

        buy_5m = sell_5m = 0.0
        buy_2h = sell_2h = 0.0
        count_5m = count_2h = 0

        for t in trades:
            try:
                # isBuyerMaker=False → taker was buyer (aggressive buy)
                # isBuyerMaker=True  → taker was seller (aggressive sell)
                is_sell = bool(t.get('isBuyerMaker', False))
                qty = float(t.get('quoteQty', 0) or 0)
                ts = int(t.get('time', 0) or 0)

                if ts >= cutoff_2h:
                    count_2h += 1
                    if is_sell:
                        sell_2h += qty
                        if ts >= cutoff_5m:
                            sell_5m += qty
                            count_5m += 1
                    else:
                        buy_2h += qty
                        if ts >= cutoff_5m:
                            buy_5m += qty
                            count_5m += 1
            except (TypeError, ValueError):
                continue

        # only store if we have meaningful data
        if buy_5m + sell_5m > 0:
            result['buy_5m'] = buy_5m
            result['sell_5m'] = sell_5m
            result['trade_count_5m'] = count_5m
        if buy_2h + sell_2h > 0:
            result['buy_2h'] = buy_2h
            result['sell_2h'] = sell_2h
            result['trade_count_2h'] = count_2h

        return result

    def _parse_order_book(self, ob_data, price: float) -> dict:
        """Parse futures order book depth into tier volumes and spread."""
        result = {}
        if not ob_data:
            return result

        try:
            data = ob_data.get('data', ob_data)
            if not isinstance(data, dict):
                return result

            raw_bids: List = data.get('bids', [])
            raw_asks: List = data.get('asks', [])

            if not raw_bids and not raw_asks:
                return result

            # normalize: each entry can be [price_str, qty_str] or {"price": ..., "quantity": ...}
            bids = sorted(self._normalize_levels(raw_bids), key=lambda x: x[0], reverse=True)
            asks = sorted(self._normalize_levels(raw_asks), key=lambda x: x[0])

            if not bids and not asks:
                return result

            # tier thresholds (as fraction of price)
            t1_pct = 0.005  # 0.5%
            t2_pct = 0.020  # 2.0%

            bid_total = sum(q for _, q in bids)
            ask_total = sum(q for _, q in asks)
            bid_wall = max((q for p, q in bids if p >= price * (1 - t2_pct)), default=0.0)
            ask_wall = max((q for p, q in asks if p <= price * (1 + t2_pct)), default=0.0)

            t1_bid = sum(q for p, q in bids if p >= price * (1 - t1_pct))
            t1_ask = sum(q for p, q in asks if p <= price * (1 + t1_pct))
            t2_bid = sum(q for p, q in bids if price * (1 - t2_pct) <= p < price * (1 - t1_pct))
            t2_ask = sum(q for p, q in asks if price * (1 + t1_pct) < p <= price * (1 + t2_pct))

            result['bid_total'] = bid_total
            result['ask_total'] = ask_total
            result['bid_wall'] = bid_wall
            result['ask_wall'] = ask_wall
            result['t1_bid'] = t1_bid
            result['t1_ask'] = t1_ask
            result['t2_bid'] = t2_bid
            result['t2_ask'] = t2_ask

            # spread from best bid/ask
            best_bid = bids[0][0] if bids else None
            best_ask = asks[0][0] if asks else None
            if best_bid and best_ask and price > 0:
                result['spread_pct'] = max(0.0, (best_ask - best_bid) / price * 100)

        except (TypeError, ValueError, IndexError) as e:
            logger.debug(f'Order book parse error: {e}')

        return result

    @staticmethod
    def _normalize_levels(levels: list) -> List[tuple]:
        """Convert order book levels to list of (price, qty) floats, sorted by price desc for bids."""
        result = []
        for lvl in levels:
            try:
                if isinstance(lvl, (list, tuple)) and len(lvl) >= 2:
                    result.append((float(lvl[0]), float(lvl[1])))
                elif isinstance(lvl, dict):
                    p = float(lvl.get('price', 0) or lvl.get('p', 0))
                    q = float(lvl.get('quantity', 0) or lvl.get('vol', 0) or lvl.get('q', 0))
                    if p > 0:
                        result.append((p, q))
            except (TypeError, ValueError):
                continue
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _float(d: dict, key: str) -> Optional[float]:
        try:
            val = d.get(key)
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    async def _safe(coro_fn, *args, **kwargs) -> Any:
        """Call an async function, returning None on any exception."""
        try:
            return await coro_fn(*args, **kwargs)
        except MEXCAPIException as e:
            logger.debug(f'{coro_fn.__name__} API error: {e}')
            return None
        except Exception as e:
            logger.debug(f'{coro_fn.__name__} failed: {e}')
            return None

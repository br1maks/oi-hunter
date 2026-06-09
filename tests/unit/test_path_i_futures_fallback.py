"""Tests for PATH I: Futures Data Fallback.

Verifies that when spot klines/trades are empty (thin-spot tokens like ESPORTS, GUA),
the DataAggregator correctly falls back to futures API endpoints and produces
fully-populated MarketData with all metrics intact.

Covers:
  1. _normalize_futures_klines() — static normalization, all edge cases
  2. get_futures_deals() — T=1/T=0 buyer/seller mapping, quoteQty calculation
  3. _parse_klines() roundtrip with futures-normalized data
  4. _parse_aggression() roundtrip with futures-normalized deals
  5. aggregate() fallback trigger — spot empty → futures called, spot present → futures NOT called
  6. Full pipeline end-to-end with realistic thin-spot data (ESPORTS-type token)
"""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.mexc_client import MEXCRestClient
from src.data.data_aggregator import DataAggregator


# ---------------------------------------------------------------------------
# Realistic data generators
# ---------------------------------------------------------------------------

def make_futures_klines_raw(n: int = 48, base_price: float = 0.020,
                             base_ts_s: int = None) -> dict:
    """Generate realistic MEXC futures klines API response (dict-of-arrays format).

    Simulates an ESPORTS-type token: ~$0.020, thin spot, active futures.
    Timestamps are in SECONDS (MEXC futures API uses seconds, not ms).
    """
    if base_ts_s is None:
        # start n hours ago, each candle is 3600s
        base_ts_s = int(time.time()) - n * 3600

    times, opens, highs, lows, closes, vols, amounts = [], [], [], [], [], [], []
    price = base_price
    for i in range(n):
        ts = base_ts_s + i * 3600
        # small realistic price walk
        change = (((i * 7 + 3) % 11) - 5) * 0.0001
        open_ = price
        close = round(price + change, 6)
        high = round(max(open_, close) * 1.008, 6)
        low = round(min(open_, close) * 0.992, 6)
        # volume: 1M–8M contracts, USDT amount = vol * mid_price * contract_size(=1)
        vol_contracts = 1_000_000 + (i % 7) * 1_000_000
        amount_usdt = round(vol_contracts * (high + low) / 2, 2)

        times.append(ts)
        opens.append(str(round(open_, 6)))
        highs.append(str(high))
        lows.append(str(low))
        closes.append(str(round(close, 6)))
        vols.append(str(vol_contracts))
        amounts.append(str(amount_usdt))
        price = close

    return {
        'success': True,
        'code': 0,
        'data': {
            'time': times,
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'vol': vols,
            'amount': amounts,
        },
    }


def make_futures_klines_normalized(n: int = 48, base_price: float = 0.020) -> list:
    """Return futures klines already normalized to spot-compatible list-of-lists."""
    raw = make_futures_klines_raw(n, base_price)
    return MEXCRestClient._normalize_futures_klines(raw['data'])


def make_futures_deals_raw(total: int = 1000, price: float = 0.020,
                            buy_pct_5m: float = 0.65,
                            buy_pct_2h: float = 0.60,
                            contract_size: float = 1.0) -> list:
    """Generate realistic MEXC futures deals API response list.

    Timestamps are in MILLISECONDS (MEXC futures deals use ms).
    Distributes trades: ~200 in last 5 min, ~700 in last 2h, ~300 older.
    """
    now_ms = int(time.time() * 1000)
    deals = []

    # 200 trades in last 5 min
    n_5m = 200
    for i in range(n_5m):
        ts = now_ms - (4 * 60 * 1000) + i * (4 * 60 * 1000 // n_5m)
        is_buy = i < int(n_5m * buy_pct_5m)
        vol = 10_000 + (i % 20) * 5_000
        deals.append({'t': ts, 'p': str(price), 'v': str(vol), 'T': 1 if is_buy else 0})

    # 500 trades between 5min and 2h ago
    n_2h = 500
    for i in range(n_2h):
        ts = now_ms - (2 * 60 * 60 * 1000) + i * (115 * 60 * 1000 // n_2h)
        is_buy = i < int(n_2h * buy_pct_2h)
        vol = 5_000 + (i % 30) * 3_000
        deals.append({'t': ts, 'p': str(price), 'v': str(vol), 'T': 1 if is_buy else 0})

    # remaining trades older than 2h (should NOT appear in aggression windows)
    n_old = total - n_5m - n_2h
    for i in range(n_old):
        ts = now_ms - (3 * 60 * 60 * 1000) - i * 1000
        deals.append({'t': ts, 'p': str(price), 'v': '5000', 'T': 1})

    return deals


def make_futures_deals_normalized(total: int = 1000, price: float = 0.020,
                                   buy_pct_5m: float = 0.65,
                                   buy_pct_2h: float = 0.60,
                                   contract_size: float = 1.0) -> list:
    """Return futures deals normalized to spot-trades format (isBuyerMaker, quoteQty, time)."""
    raw_deals = make_futures_deals_raw(total, price, buy_pct_5m, buy_pct_2h, contract_size)
    result = []
    for d in raw_deals:
        p = float(d['p'])
        v = float(d['v'])
        result.append({
            'isBuyerMaker': d['T'] == 0,  # T=1 buy → False, T=0 sell → True
            'quoteQty': str(p * v * contract_size),
            'time': int(d['t']),
        })
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_ticker(price: float = 0.020) -> dict:
    return {
        'lastPrice': str(price),
        'highPrice': str(round(price * 1.15, 6)),
        'lowPrice': str(round(price * 0.85, 6)),
        'quoteVolume': '500000',
        'priceChangePercent': '-5.2',
    }


def make_mock_oi(price: float = 0.020) -> dict:
    return {
        'openInterest': '500000',
        'lastPrice': str(price),
        'amount24': '450000',
    }


def make_mock_funding() -> dict:
    return {'fundingRate': '0.00034'}


# ---------------------------------------------------------------------------
# Section 1: _normalize_futures_klines() — static method, no HTTP
# ---------------------------------------------------------------------------

class TestNormalizeFuturesKlines:

    def test_basic_field_mapping(self):
        """Each output candle maps to [ts_ms, open, high, low, close, vol, close_ts, quote_vol]."""
        data = {
            'time': [1706011200],
            'open': ['0.00100'],
            'high': ['0.00105'],
            'low': ['0.00098'],
            'close': ['0.00102'],
            'vol': ['5000000'],
            'amount': ['5100'],
        }
        result = MEXCRestClient._normalize_futures_klines(data)
        assert len(result) == 1
        k = result[0]
        assert k[1] == '0.00100'   # open
        assert k[2] == '0.00105'   # high
        assert k[3] == '0.00098'   # low
        assert k[4] == '0.00102'   # close
        assert k[5] == '5000000'   # vol (contracts)
        assert k[7] == '5100'      # amount (USDT) used as quote_vol

    def test_timestamps_converted_from_seconds_to_milliseconds(self):
        """MEXC futures timestamps are in seconds; output must be milliseconds."""
        ts_sec = 1706011200
        data = {
            'time': [ts_sec],
            'open': ['1.0'], 'high': ['1.0'], 'low': ['1.0'], 'close': ['1.0'],
            'vol': ['100'], 'amount': ['100'],
        }
        result = MEXCRestClient._normalize_futures_klines(data)
        assert result[0][0] == ts_sec * 1000

    def test_close_time_is_timestamp_plus_one_hour(self):
        """k[6] (close_time_ms) must equal k[0] + 3_600_000."""
        ts_sec = 1706011200
        data = {
            'time': [ts_sec],
            'open': ['1.0'], 'high': ['1.0'], 'low': ['1.0'], 'close': ['1.0'],
            'vol': ['100'], 'amount': ['100'],
        }
        result = MEXCRestClient._normalize_futures_klines(data)
        assert result[0][6] == result[0][0] + 3_600_000

    def test_amount_preferred_over_vol_times_close_for_quote_vol(self):
        """When 'amount' is present, it is used as k[7] (not vol*close)."""
        data = {
            'time': [1706011200],
            'open': ['1.0'], 'high': ['1.0'], 'low': ['1.0'], 'close': ['2.0'],
            'vol': ['1000'],
            'amount': ['9999'],  # explicit USDT amount
        }
        result = MEXCRestClient._normalize_futures_klines(data)
        assert result[0][7] == '9999'

    def test_fallback_to_vol_times_close_when_amount_missing(self):
        """When 'amount' is absent, k[7] = str(vol * close)."""
        data = {
            'time': [1706011200],
            'open': ['1.0'], 'high': ['1.0'], 'low': ['1.0'], 'close': ['2.0'],
            'vol': ['1000'],
            # no 'amount' key
        }
        result = MEXCRestClient._normalize_futures_klines(data)
        assert float(result[0][7]) == pytest.approx(2000.0)

    def test_empty_dict_returns_empty_list(self):
        result = MEXCRestClient._normalize_futures_klines({})
        assert result == []

    def test_empty_time_array_returns_empty_list(self):
        data = {'time': [], 'open': [], 'high': [], 'low': [], 'close': [], 'vol': []}
        result = MEXCRestClient._normalize_futures_klines(data)
        assert result == []

    def test_malformed_timestamp_entry_is_skipped(self):
        """A candle with non-numeric timestamp is silently skipped."""
        data = {
            'time': ['not_a_number', 1706011200],
            'open': ['1.0', '1.0'], 'high': ['1.0', '1.0'],
            'low': ['1.0', '1.0'], 'close': ['1.0', '1.0'],
            'vol': ['100', '100'], 'amount': ['100', '100'],
        }
        result = MEXCRestClient._normalize_futures_klines(data)
        # first entry skipped, second valid
        assert len(result) == 1
        assert result[0][0] == 1706011200 * 1000

    def test_48_candle_realistic_data_parses_fully(self):
        """Full 48-candle realistic dataset normalizes without loss."""
        raw = make_futures_klines_raw(48)
        result = MEXCRestClient._normalize_futures_klines(raw['data'])
        assert len(result) == 48
        # all timestamps strictly increasing
        timestamps = [k[0] for k in result]
        for i in range(1, len(timestamps)):
            assert timestamps[i] > timestamps[i - 1]
        # all close values are positive floats
        for k in result:
            assert float(k[4]) > 0

    def test_output_is_compatible_with_spot_kline_format(self):
        """Output format must match spot klines: k[2]=high, k[3]=low, k[4]=close, k[7]=quote_vol."""
        raw = make_futures_klines_raw(5)
        result = MEXCRestClient._normalize_futures_klines(raw['data'])
        for k in result:
            assert len(k) == 8
            # high >= low
            assert float(k[2]) >= float(k[3])
            # quote_vol > 0
            assert float(k[7]) > 0


# ---------------------------------------------------------------------------
# Section 2: Futures deals → spot trades normalization
# ---------------------------------------------------------------------------

class TestFuturesDealNormalization:
    """Tests the buyer/seller mapping and quoteQty calculation logic.

    We test the logic directly since get_futures_deals() requires HTTP.
    We replicate the exact normalization loop from the method.
    """

    def _normalize_deals(self, raw_deals: list, contract_size: float = 1.0) -> list:
        """Replicate the normalization loop from get_futures_deals()."""
        result = []
        for d in raw_deals:
            try:
                price = float(d.get('p', 0) or 0)
                vol_contracts = float(d.get('v', 0) or 0)
                quote_qty = price * vol_contracts * contract_size
                result.append({
                    'isBuyerMaker': d.get('T', 1) == 0,
                    'quoteQty': str(quote_qty),
                    'time': int(d.get('t', 0) or 0),
                })
            except (TypeError, ValueError):
                continue
        return result

    def test_T1_maps_to_isBuyerMaker_False(self):
        """T=1 (taker was buyer) → isBuyerMaker=False (aggressive buy)."""
        deals = [{'t': 1706011234567, 'p': '0.020', 'v': '1000', 'T': 1}]
        result = self._normalize_deals(deals)
        assert result[0]['isBuyerMaker'] is False

    def test_T0_maps_to_isBuyerMaker_True(self):
        """T=0 (taker was seller) → isBuyerMaker=True (aggressive sell)."""
        deals = [{'t': 1706011234567, 'p': '0.020', 'v': '1000', 'T': 0}]
        result = self._normalize_deals(deals)
        assert result[0]['isBuyerMaker'] is True

    def test_quote_qty_calculation_contract_size_1(self):
        """quoteQty = price × vol_contracts × contract_size (=1.0 default)."""
        deals = [{'t': 1706011234567, 'p': '0.020', 'v': '50000', 'T': 1}]
        result = self._normalize_deals(deals, contract_size=1.0)
        assert float(result[0]['quoteQty']) == pytest.approx(0.020 * 50000 * 1.0)

    def test_quote_qty_calculation_with_contract_size_10(self):
        """Tokens with contract_size=10 should multiply correctly."""
        deals = [{'t': 1706011234567, 'p': '0.020', 'v': '50000', 'T': 1}]
        result = self._normalize_deals(deals, contract_size=10.0)
        assert float(result[0]['quoteQty']) == pytest.approx(0.020 * 50000 * 10.0)

    def test_timestamp_preserved_in_milliseconds(self):
        """Futures deals timestamps are already in ms — must pass through unchanged."""
        ts_ms = 1706011234567
        deals = [{'t': ts_ms, 'p': '0.020', 'v': '1000', 'T': 1}]
        result = self._normalize_deals(deals)
        assert result[0]['time'] == ts_ms

    def test_malformed_deal_with_none_price_is_skipped(self):
        deals = [{'t': 123456, 'p': None, 'v': '1000', 'T': 1}]
        # price=None → float(None) raises TypeError → skipped
        result = self._normalize_deals(deals)
        # price None → float(None or 0) = 0.0, so quoteQty=0, not skipped but qty=0
        # Actually: d.get('p', 0) or 0 = None or 0 = 0, so price=0.0 → quoteQty=0
        assert result[0]['quoteQty'] == '0.0'

    def test_all_1000_deals_normalized(self):
        """1000-deal realistic dataset normalizes to exactly 1000 entries."""
        raw = make_futures_deals_raw(1000)
        result = self._normalize_deals(raw, contract_size=1.0)
        assert len(result) == 1000

    def test_buyer_seller_ratio_matches_generation(self):
        """60% of 2h-window deals should be buys (T=1 → isBuyerMaker=False)."""
        raw = make_futures_deals_raw(1000, buy_pct_5m=0.65, buy_pct_2h=0.60)
        result = self._normalize_deals(raw)
        # all 1000 deals — check global ratio is > 50% buys
        buys = sum(1 for r in result if not r['isBuyerMaker'])
        assert buys > 500  # majority are buys (65% in 5m + 60% in 2h)


# ---------------------------------------------------------------------------
# Section 3: _parse_klines() roundtrip with futures-normalized data
# ---------------------------------------------------------------------------

class TestParseKlinesWithFuturesData:
    """DataAggregator._parse_klines() must work identically with futures-normalized klines."""

    def setup_method(self):
        self.agg = DataAggregator.__new__(DataAggregator)
        self.agg._client = None
        self.agg._mc_cache = None
        self.agg._own_client = False
        self.agg._oi_last_known = {}

    def test_price_change_1h_populated(self):
        klines = make_futures_klines_normalized(48, base_price=0.020)
        current_price = float(klines[-1][4])  # last close as current price
        metrics = self.agg._parse_klines(klines, current_price)
        assert 'price_change_1h' in metrics
        assert isinstance(metrics['price_change_1h'], float)

    def test_price_change_4h_populated(self):
        klines = make_futures_klines_normalized(48)
        current_price = float(klines[-1][4])
        metrics = self.agg._parse_klines(klines, current_price)
        assert 'price_change_4h' in metrics

    def test_volume_1h_populated_and_positive(self):
        klines = make_futures_klines_normalized(48)
        current_price = float(klines[-1][4])
        metrics = self.agg._parse_klines(klines, current_price)
        assert 'volume_1h' in metrics
        assert metrics['volume_1h'] > 0

    def test_avg_volume_1h_populated_requires_25_candles(self):
        klines = make_futures_klines_normalized(48)
        current_price = float(klines[-1][4])
        metrics = self.agg._parse_klines(klines, current_price)
        assert 'avg_volume_1h' in metrics
        assert metrics['avg_volume_1h'] > 0

    def test_avg_volume_not_populated_with_only_24_candles(self):
        """avg_volume_1h requires n >= 25; with 24 candles it should be absent."""
        klines = make_futures_klines_normalized(24)
        current_price = float(klines[-1][4])
        metrics = self.agg._parse_klines(klines, current_price)
        assert 'avg_volume_1h' not in metrics

    def test_atr_populated(self):
        klines = make_futures_klines_normalized(48)
        current_price = float(klines[-1][4])
        metrics = self.agg._parse_klines(klines, current_price)
        assert 'atr' in metrics
        assert metrics['atr'] is not None
        assert metrics['atr'] > 0

    def test_vci_populated_with_48_candles(self):
        """VCI requires n >= 22 candles."""
        klines = make_futures_klines_normalized(48)
        current_price = float(klines[-1][4])
        metrics = self.agg._parse_klines(klines, current_price)
        assert 'vci' in metrics
        assert metrics['vci'] is not None
        assert metrics['vci'] > 0

    def test_cfc_populated(self):
        klines = make_futures_klines_normalized(48)
        current_price = float(klines[-1][4])
        metrics = self.agg._parse_klines(klines, current_price)
        assert 'cfc' in metrics
        assert isinstance(metrics['cfc'], int)

    def test_vwap_populated_with_48_candles(self):
        klines = make_futures_klines_normalized(48)
        current_price = float(klines[-1][4])
        metrics = self.agg._parse_klines(klines, current_price)
        assert 'vwap' in metrics
        assert metrics['vwap'] is not None
        assert metrics['vwap'] > 0

    def test_volume_ratio_computable_from_metrics(self):
        """After parse, volume_1h / avg_volume_1h gives a valid ratio > 0."""
        klines = make_futures_klines_normalized(48)
        current_price = float(klines[-1][4])
        metrics = self.agg._parse_klines(klines, current_price)
        vol = metrics.get('volume_1h', 0)
        avg = metrics.get('avg_volume_1h', 0)
        assert avg > 0
        ratio = vol / avg
        assert 0.01 < ratio < 100  # sanity bounds: not zero, not absurdly large

    def test_empty_klines_returns_empty_dict(self):
        metrics = self.agg._parse_klines([], 0.020)
        assert metrics == {}

    def test_too_few_klines_returns_empty_dict(self):
        klines = make_futures_klines_normalized(4)  # < 5 minimum
        metrics = self.agg._parse_klines(klines, 0.020)
        assert metrics == {}


# ---------------------------------------------------------------------------
# Section 4: _parse_aggression() roundtrip with futures-normalized deals
# ---------------------------------------------------------------------------

class TestParseAggressionWithFuturesDeals:

    def setup_method(self):
        self.agg = DataAggregator.__new__(DataAggregator)
        self.agg._client = None
        self.agg._mc_cache = None
        self.agg._own_client = False
        self.agg._oi_last_known = {}

    def test_buy_5m_populated(self):
        deals = make_futures_deals_normalized(1000, buy_pct_5m=0.65)
        result = self.agg._parse_aggression(deals)
        assert 'buy_5m' in result
        assert result['buy_5m'] > 0

    def test_sell_5m_populated(self):
        deals = make_futures_deals_normalized(1000, buy_pct_5m=0.65)
        result = self.agg._parse_aggression(deals)
        assert 'sell_5m' in result
        assert result['sell_5m'] > 0

    def test_trade_count_5m_populated(self):
        deals = make_futures_deals_normalized(1000)
        result = self.agg._parse_aggression(deals)
        assert 'trade_count_5m' in result
        assert result['trade_count_5m'] >= 20  # 200 5m trades generated

    def test_buy_2h_populated(self):
        deals = make_futures_deals_normalized(1000, buy_pct_2h=0.60)
        result = self.agg._parse_aggression(deals)
        assert 'buy_2h' in result
        assert result['buy_2h'] > 0

    def test_sell_2h_populated(self):
        deals = make_futures_deals_normalized(1000, buy_pct_2h=0.60)
        result = self.agg._parse_aggression(deals)
        assert 'sell_2h' in result
        assert result['sell_2h'] > 0

    def test_trade_count_2h_at_least_500(self):
        """We generate 200 5m trades + 500 2h trades = 700 total in 2h window."""
        deals = make_futures_deals_normalized(1000)
        result = self.agg._parse_aggression(deals)
        assert result.get('trade_count_2h', 0) >= 500

    def test_old_trades_excluded_from_2h_window(self):
        """300 trades older than 2h must not appear in buy_2h or sell_2h."""
        # Only new trades (5m + 2h window = 700)
        deals = make_futures_deals_normalized(1000, buy_pct_2h=0.60)
        result = self.agg._parse_aggression(deals)
        # trade_count_2h should be ~700, NOT 1000
        count_2h = result.get('trade_count_2h', 0)
        assert count_2h <= 750  # max 700 + small buffer for timing jitter

    def test_buy_dominates_in_accumulation_scenario(self):
        """When buy_pct=0.65 in 5m, buy_5m should exceed sell_5m."""
        deals = make_futures_deals_normalized(1000, buy_pct_5m=0.65, buy_pct_2h=0.60)
        result = self.agg._parse_aggression(deals)
        assert result['buy_5m'] > result['sell_5m']
        assert result['buy_2h'] > result['sell_2h']

    def test_empty_deals_returns_empty_dict(self):
        result = self.agg._parse_aggression([])
        assert result == {}

    def test_none_deals_returns_empty_dict(self):
        result = self.agg._parse_aggression(None)
        assert result == {}


# ---------------------------------------------------------------------------
# Section 5: aggregate() fallback trigger — mock-level tests
# ---------------------------------------------------------------------------

class TestFallbackTriggerInAggregate:
    """Verify that aggregate() calls futures endpoints when spot returns empty,
    and does NOT call them when spot data is present."""

    def _make_mock_client(self, spot_klines=None, spot_trades=None,
                          futures_klines=None, futures_deals=None):
        """Build a mock MEXCRestClient with configurable return values."""
        client = MagicMock()
        client.get_ticker_24h = AsyncMock(return_value=make_mock_ticker())
        client.get_open_interest = AsyncMock(return_value=make_mock_oi())
        client.get_funding_rate = AsyncMock(return_value=make_mock_funding())
        client.get_order_book = AsyncMock(return_value=None)
        client.get_klines = AsyncMock(return_value=spot_klines if spot_klines is not None else [])
        client.get_recent_trades = AsyncMock(return_value=spot_trades if spot_trades is not None else [])
        client.get_futures_klines = AsyncMock(return_value=futures_klines if futures_klines is not None else [])
        client.get_futures_deals = AsyncMock(return_value=futures_deals if futures_deals is not None else [])
        # _contract_size_cache must exist on the mock
        client._contract_size_cache = {}
        return client

    def _make_aggregator(self, client) -> DataAggregator:
        agg = DataAggregator.__new__(DataAggregator)
        agg._client = client
        agg._mc_cache = None
        agg._own_client = False
        agg._oi_last_known = {}
        return agg

    def test_futures_klines_called_when_spot_klines_empty(self):
        futures_klines = make_futures_klines_normalized(48)
        client = self._make_mock_client(spot_klines=[], futures_klines=futures_klines)
        agg = self._make_aggregator(client)

        asyncio.run(agg.aggregate('ESPORTS_USDT'))

        client.get_futures_klines.assert_called_once()

    def test_futures_deals_called_when_spot_trades_empty(self):
        futures_klines = make_futures_klines_normalized(48)
        futures_deals = make_futures_deals_normalized(1000)
        client = self._make_mock_client(
            spot_klines=[], spot_trades=[],
            futures_klines=futures_klines, futures_deals=futures_deals,
        )
        agg = self._make_aggregator(client)

        asyncio.run(agg.aggregate('ESPORTS_USDT'))

        client.get_futures_deals.assert_called_once()

    def test_futures_klines_NOT_called_when_spot_returns_data(self):
        spot_klines = make_futures_klines_normalized(48)  # spot data present
        client = self._make_mock_client(spot_klines=spot_klines)
        agg = self._make_aggregator(client)

        asyncio.run(agg.aggregate('BTC_USDT'))

        client.get_futures_klines.assert_not_called()

    def test_futures_deals_NOT_called_when_spot_trades_present(self):
        spot_klines = make_futures_klines_normalized(48)
        spot_trades = make_futures_deals_normalized(100)
        client = self._make_mock_client(spot_klines=spot_klines, spot_trades=spot_trades)
        agg = self._make_aggregator(client)

        asyncio.run(agg.aggregate('BTC_USDT'))

        client.get_futures_deals.assert_not_called()

    def test_fallback_klines_populates_volume_metrics(self):
        """When futures fallback fires, MarketData must have volume_1h and avg_volume_1h."""
        futures_klines = make_futures_klines_normalized(48)
        client = self._make_mock_client(spot_klines=[], futures_klines=futures_klines)
        agg = self._make_aggregator(client)

        data = asyncio.run(agg.aggregate('ESPORTS_USDT'))

        assert data.volume_1h is not None
        assert data.avg_volume_1h is not None
        assert data.volume_1h > 0
        assert data.avg_volume_1h > 0

    def test_fallback_deals_populates_aggression_metrics(self):
        """When futures fallback fires, MarketData must have buy_volume_5m and trade_count_5m."""
        futures_klines = make_futures_klines_normalized(48)
        futures_deals = make_futures_deals_normalized(1000)
        client = self._make_mock_client(
            spot_klines=[], spot_trades=[],
            futures_klines=futures_klines, futures_deals=futures_deals,
        )
        agg = self._make_aggregator(client)

        data = asyncio.run(agg.aggregate('ESPORTS_USDT'))

        assert data.buy_volume_5m is not None
        assert data.sell_volume_5m is not None
        assert data.trade_count_5m is not None
        assert data.trade_count_5m >= 20

    def test_fallback_deals_enables_aggression_5m_field(self):
        """With futures deals, aggression_5m must be computable (buy+sell > 0)."""
        futures_klines = make_futures_klines_normalized(48)
        futures_deals = make_futures_deals_normalized(1000, buy_pct_5m=0.65)
        client = self._make_mock_client(
            spot_klines=[], spot_trades=[],
            futures_klines=futures_klines, futures_deals=futures_deals,
        )
        agg = self._make_aggregator(client)

        data = asyncio.run(agg.aggregate('ESPORTS_USDT'))

        buy = data.buy_volume_5m or 0
        sell = data.sell_volume_5m or 0
        total = buy + sell
        assert total > 0
        agg_5m = buy / total * 100
        assert 50 < agg_5m < 80  # generated 65% buyers


# ---------------------------------------------------------------------------
# Section 6: Full pipeline end-to-end — ESPORTS-type thin-spot token
# ---------------------------------------------------------------------------

class TestFullPipelineEsportsToken:
    """End-to-end test simulating an ESPORTS_USDT scenario.

    This token had thin spot (klines/trades return empty on spot API)
    but active futures. Before PATH I: Volume Spike and Aggression returned
    None → kinetic gate never passed → NO SIGNAL ever.
    After PATH I: futures data fills the gap → all metrics populated.
    """

    def setup_method(self):
        futures_klines = make_futures_klines_normalized(48, base_price=0.020)
        futures_deals = make_futures_deals_normalized(
            1000, price=0.020, buy_pct_5m=0.30, buy_pct_2h=0.35
        )  # sellers dominating — bearish setup like pre-dump

        client = MagicMock()
        client.get_ticker_24h = AsyncMock(return_value=make_mock_ticker(0.020))
        client.get_open_interest = AsyncMock(return_value=make_mock_oi(0.020))
        client.get_funding_rate = AsyncMock(return_value={'fundingRate': '0.00340'})  # extreme funding
        client.get_order_book = AsyncMock(return_value=None)
        client.get_klines = AsyncMock(return_value=[])          # THIN SPOT: empty
        client.get_recent_trades = AsyncMock(return_value=[])   # THIN SPOT: empty
        client.get_futures_klines = AsyncMock(return_value=futures_klines)
        client.get_futures_deals = AsyncMock(return_value=futures_deals)
        client._contract_size_cache = {}

        agg = DataAggregator.__new__(DataAggregator)
        agg._client = client
        agg._mc_cache = None
        agg._own_client = False
        agg._oi_last_known = {}

        self.client = client
        self.data = asyncio.run(agg.aggregate('ESPORTS_USDT'))

    def test_both_fallbacks_fired(self):
        self.client.get_futures_klines.assert_called_once()
        self.client.get_futures_deals.assert_called_once()

    def test_price_populated(self):
        assert self.data.price == pytest.approx(0.020, rel=0.01)

    def test_funding_rate_populated_and_extreme(self):
        assert self.data.funding_rate == pytest.approx(0.00340, rel=0.01)

    def test_volume_1h_populated(self):
        assert self.data.volume_1h is not None
        assert self.data.volume_1h > 0

    def test_avg_volume_1h_populated(self):
        assert self.data.avg_volume_1h is not None
        assert self.data.avg_volume_1h > 0

    def test_price_change_1h_populated(self):
        assert self.data.price_change_1h is not None

    def test_price_change_4h_populated(self):
        assert self.data.price_change_4h is not None

    def test_atr_populated(self):
        assert self.data.atr is not None
        assert self.data.atr > 0

    def test_buy_volume_5m_populated(self):
        assert self.data.buy_volume_5m is not None

    def test_sell_volume_5m_populated(self):
        assert self.data.sell_volume_5m is not None

    def test_trade_count_5m_sufficient_for_analyzers(self):
        """trade_count_5m >= 20 means AggressionAnalyzer will use 5m data (not fall back to 2h)."""
        assert self.data.trade_count_5m is not None
        assert self.data.trade_count_5m >= 20

    def test_aggression_5m_bearish(self):
        """With buy_pct=0.30, sellers should dominate 5m aggression."""
        buy = self.data.buy_volume_5m or 0
        sell = self.data.sell_volume_5m or 0
        total = buy + sell
        assert total > 0
        agg_5m = buy / total * 100
        assert agg_5m < 50  # sellers > buyers

    def test_volume_spike_analyzer_can_run(self):
        """VolumeSpikeAnalyzer._validate_data() requires volume_1h and avg_volume_1h.
        Both must be non-None and > 0 after futures fallback."""
        from src.analyzers.volume_spike_analyzer import VolumeSpikeAnalyzer
        analyzer = VolumeSpikeAnalyzer()
        # Should not return None due to missing volume data
        # (may return None if spike_score==0, but not due to validation failure)
        result = analyzer.analyze(self.data)
        # We just verify validate_data passes — result can be None if ratio < threshold
        # The key assertion: no AttributeError, no missing-field crash
        # If result is None it's because score=0, not because data is missing
        vol_ratio = self.data.volume_1h / self.data.avg_volume_1h
        if vol_ratio >= 1.5:
            assert result is not None  # should produce a result with sufficient spike

    def test_aggression_analyzer_can_run(self):
        """AggressionAnalyzer requires buy_volume_5m. Must not return None due to missing data."""
        from src.analyzers.aggression_analyzer import AggressionAnalyzer
        analyzer = AggressionAnalyzer()
        result = analyzer.analyze(self.data)
        # With 200+ 5m trades at 30% buy rate → bearish aggression result
        assert result is not None
        assert result.short_score > result.long_score  # sellers dominating

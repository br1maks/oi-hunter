import asyncio
from typing import Optional, Dict, Any
from collections import deque
import time
import httpx
from datetime import datetime
from .config import MEXCConfig
from .exceptions import MEXCAPIException, MEXCRateLimitException, MEXCAuthException, MEXCNotFoundException, MEXCServerException, MEXCNetworkException, MEXCInvalidSymbolException

class MEXCRestClient:

    def __init__(self, api_key: Optional[str]=None, api_secret: Optional[str]=None, timeout: int=MEXCConfig.REQUEST_TIMEOUT):
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._request_timestamps: deque = deque(maxlen=MEXCConfig.RATE_LIMIT_REQUESTS_PER_SECOND * 60)
        self._weight_timestamps: deque = deque(maxlen=MEXCConfig.RATE_LIMIT_WEIGHT_PER_MINUTE)
        self._contract_size_cache: Dict[str, float] = {}

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    async def _check_rate_limit(self, weight: int=1):
        current_time = time.time()
        while self._request_timestamps and current_time - self._request_timestamps[0] > 1.0:
            self._request_timestamps.popleft()
        if len(self._request_timestamps) >= MEXCConfig.RATE_LIMIT_REQUESTS_PER_SECOND:
            sleep_time = 1.0 - (current_time - self._request_timestamps[0])
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
                current_time = time.time()
        while self._weight_timestamps and current_time - self._weight_timestamps[0] > 60.0:
            self._weight_timestamps.popleft()
        current_weight = len(self._weight_timestamps)
        if current_weight + weight > MEXCConfig.RATE_LIMIT_WEIGHT_PER_MINUTE:
            sleep_time = 60.0 - (current_time - self._weight_timestamps[0])
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
        self._request_timestamps.append(current_time)
        for _ in range(weight):
            self._weight_timestamps.append(current_time)

    async def _request(self, method: str, url: str, params: Optional[Dict[str, Any]]=None, retry_count: int=0, weight: int=1) -> Dict[str, Any]:
        if not self._client:
            raise MEXCAPIException("Client not initialized. Use 'async with' context manager")
        if retry_count == 0:
            await self._check_rate_limit(weight)
        try:
            response = await self._client.request(method=method, url=url, params=params)
            if response.status_code == 200:
                data = response.json()
                if not data.get('success', True):
                    code = data.get('code', 0)
                    msg = data.get('message', 'Unknown API error')
                    if code == 510:
                        if retry_count < MEXCConfig.MAX_RETRIES:
                            await asyncio.sleep(MEXCConfig.RETRY_DELAY * (retry_count + 1))
                            return await self._request(method, url, params, retry_count + 1, weight)
                        raise MEXCRateLimitException(msg, status_code=200, response=data)
                return data
            await self._handle_error(response, retry_count, method, url, params, weight)
        except httpx.TimeoutException as e:
            raise MEXCNetworkException(f'Request timeout: {url}', response={'error': str(e)})
        except httpx.NetworkError as e:
            raise MEXCNetworkException(f'Network error: {url}', response={'error': str(e)})
        except Exception as e:
            raise MEXCAPIException(f'Unexpected error: {str(e)}')

    async def _handle_error(self, response: httpx.Response, retry_count: int, method: str, url: str, params: Optional[Dict[str, Any]], weight: int=1):
        status_code = response.status_code
        try:
            error_data = response.json()
        except:
            error_data = {'msg': response.text}
        if status_code == 429:
            if retry_count < MEXCConfig.MAX_RETRIES:
                await asyncio.sleep(MEXCConfig.RETRY_DELAY * (retry_count + 1))
                return await self._request(method, url, params, retry_count + 1, weight)
            raise MEXCRateLimitException('Rate limit exceeded', status_code=status_code, response=error_data)
        elif status_code == 401:
            raise MEXCAuthException('Authentication failed', status_code=status_code, response=error_data)
        elif status_code == 404:
            raise MEXCNotFoundException(f'Resource not found: {url}', status_code=status_code, response=error_data)
        elif 500 <= status_code < 600:
            if retry_count < MEXCConfig.MAX_RETRIES:
                await asyncio.sleep(MEXCConfig.RETRY_DELAY * (retry_count + 1))
                return await self._request(method, url, params, retry_count + 1, weight)
            raise MEXCServerException(f'Server error: {status_code}', status_code=status_code, response=error_data)
        else:
            raise MEXCAPIException(f"API error: {error_data.get('msg', 'Unknown error')}", status_code=status_code, response=error_data)

    async def get_ticker_24h(self, symbol: str) -> Dict[str, Any]:
        normalized_symbol = MEXCConfig.spot_symbol_format(symbol)
        if not normalized_symbol:
            raise MEXCInvalidSymbolException(f'Invalid symbol: {symbol}')
        url = f'{MEXCConfig.SPOT_BASE_URL}{MEXCConfig.SPOT_TICKER_24H}'
        params = {'symbol': normalized_symbol}
        return await self._request('GET', url, params)

    async def get_open_interest(self, symbol: str) -> Dict[str, Any]:
        normalized_symbol = MEXCConfig.futures_symbol_format(symbol)
        if not normalized_symbol:
            raise MEXCInvalidSymbolException(f'Invalid symbol: {symbol}')
        if normalized_symbol in self._contract_size_cache:
            contract_size = self._contract_size_cache[normalized_symbol]
        else:
            detail_url = f'{MEXCConfig.FUTURES_BASE_URL}/api/v1/contract/detail'
            detail_response = await self._request('GET', detail_url, {'symbol': normalized_symbol})
            if not detail_response.get('success'):
                raise MEXCNotFoundException(f'Contract details not found: {normalized_symbol}', status_code=404, response=detail_response)
            contract_size = float(detail_response.get('data', {}).get('contractSize', 0.0001))
            self._contract_size_cache[normalized_symbol] = contract_size
        ticker_url = f'{MEXCConfig.FUTURES_BASE_URL}/api/v1/contract/ticker'
        ticker_response = await self._request('GET', ticker_url, {'symbol': normalized_symbol})
        if not ticker_response.get('success'):
            raise MEXCNotFoundException(f'Contract ticker not found: {normalized_symbol}', status_code=404, response=ticker_response)
        data = ticker_response.get('data', {})
        hold_vol = float(data.get('holdVol', 0))
        last_price = float(data.get('lastPrice', 0))
        open_interest_value = hold_vol * contract_size * last_price
        return {'symbol': normalized_symbol, 'openInterest': str(hold_vol), 'openInterestValue': str(open_interest_value), 'contractSize': str(contract_size), 'lastPrice': str(last_price), 'timestamp': data.get('timestamp', 0), 'amount24': str(data.get('amount24') or 0)}

    async def get_funding_rate(self, symbol: str) -> Dict[str, Any]:
        normalized_symbol = MEXCConfig.futures_symbol_format(symbol)
        if not normalized_symbol:
            raise MEXCInvalidSymbolException(f'Invalid symbol: {symbol}')
        if '_' not in normalized_symbol:
            if normalized_symbol.endswith('USDT'):
                base = normalized_symbol[:-4]
                normalized_symbol = f'{base}_USDT'
            else:
                raise MEXCInvalidSymbolException(f"Cannot parse symbol: {symbol}. Expected format: 'BTCUSDT' or 'BTC_USDT'")
        endpoint = MEXCConfig.FUTURES_FUNDING_RATE.format(symbol=normalized_symbol)
        url = f'{MEXCConfig.FUTURES_BASE_URL}{endpoint}'
        return await self._request('GET', url)

    async def get_recent_trades(self, symbol: str, limit: int=100) -> list[Dict[str, Any]]:
        normalized_symbol = MEXCConfig.spot_symbol_format(symbol)
        if not normalized_symbol:
            raise MEXCInvalidSymbolException(f'Invalid symbol: {symbol}')
        limit = min(max(1, limit), 1000)
        url = f'{MEXCConfig.SPOT_BASE_URL}{MEXCConfig.SPOT_TRADES}'
        params = {'symbol': normalized_symbol, 'limit': limit}
        return await self._request('GET', url, params)

    async def get_klines(self, symbol: str, interval: str='5m', limit: int=100) -> list[list]:
        normalized_symbol = MEXCConfig.spot_symbol_format(symbol)
        if not normalized_symbol:
            raise MEXCInvalidSymbolException(f'Invalid symbol: {symbol}')
        interval_map = {'1h': '60m'}
        normalized_interval = interval_map.get(interval, interval)
        limit = min(max(1, limit), 1000)
        url = f'{MEXCConfig.SPOT_BASE_URL}{MEXCConfig.SPOT_KLINES}'
        params = {'symbol': normalized_symbol, 'interval': normalized_interval, 'limit': limit}
        return await self._request('GET', url, params)

    async def get_futures_klines(self, symbol: str, interval: str = '1h', limit: int = 100) -> list[list]:
        normalized_symbol = MEXCConfig.futures_symbol_format(symbol)
        if not normalized_symbol:
            raise MEXCInvalidSymbolException(f'Invalid symbol: {symbol}')
        interval_map = {'1h': 'Min60', '5m': 'Min5', '15m': 'Min15', '4h': 'Min240', '1d': 'Day1'}
        futures_interval = interval_map.get(interval, 'Min60')
        limit = min(max(1, limit), 2000)
        url = f'{MEXCConfig.FUTURES_BASE_URL}{MEXCConfig.FUTURES_KLINES}/{normalized_symbol}'
        params = {'interval': futures_interval, 'limit': limit}
        response = await self._request('GET', url, params)
        if not response.get('success'):
            return []
        data = response.get('data', {})
        if not data or 'time' not in data:
            return []
        return self._normalize_futures_klines(data)

    @staticmethod
    def _normalize_futures_klines(data: dict) -> list[list]:
        """Convert futures klines dict-of-arrays to spot-compatible list-of-lists.

        Spot format: [timestamp_ms, open, high, low, close, base_vol, close_time_ms, quote_vol]
        Futures source: {time:[...seconds], open:[...], high:[...], low:[...],
                         close:[...], vol:[...contracts], amount:[...usdt]}
        """
        times   = data.get('time', [])
        opens   = data.get('open', [])
        highs   = data.get('high', [])
        lows    = data.get('low', [])
        closes  = data.get('close', [])
        vols    = data.get('vol', [])
        amounts = data.get('amount', [])
        result = []
        n = len(times)
        for i in range(n):
            try:
                ts_ms = int(times[i]) * 1000  # seconds → milliseconds
                c = closes[i] if i < len(closes) else '0'
                v = vols[i] if i < len(vols) else '0'
                if i < len(amounts) and amounts[i]:
                    quote_vol = str(amounts[i])
                else:
                    quote_vol = str(float(v or 0) * float(c or 0))
                result.append([
                    ts_ms,
                    opens[i] if i < len(opens) else '0',
                    highs[i] if i < len(highs) else '0',
                    lows[i]  if i < len(lows)  else '0',
                    c,
                    v,
                    ts_ms + 3_600_000,
                    quote_vol,
                ])
            except (TypeError, ValueError, IndexError):
                continue
        return result

    async def get_futures_deals(self, symbol: str, limit: int = 1000) -> list[dict]:
        """Fetch futures recent deals and normalize to spot trades format.

        Spot trades format: {isBuyerMaker: bool, quoteQty: str, time: int}
        Futures deals: {T: 1|0, v: contracts, p: price, t: timestamp_ms}
        T=1 → taker was buyer (isBuyerMaker=False), T=0 → taker was seller (isBuyerMaker=True)
        """
        normalized_symbol = MEXCConfig.futures_symbol_format(symbol)
        if not normalized_symbol:
            raise MEXCInvalidSymbolException(f'Invalid symbol: {symbol}')
        limit = min(max(1, limit), 2000)
        url = f'{MEXCConfig.FUTURES_BASE_URL}{MEXCConfig.FUTURES_DEALS}/{normalized_symbol}'
        params = {'limit': limit}
        response = await self._request('GET', url, params)
        if not response.get('success'):
            return []
        deals = response.get('data', [])
        if not isinstance(deals, list):
            return []
        contract_size = self._contract_size_cache.get(normalized_symbol, 1.0)
        result = []
        for d in deals:
            try:
                price = float(d.get('p', 0) or 0)
                vol_contracts = float(d.get('v', 0) or 0)
                quote_qty = price * vol_contracts * contract_size
                result.append({
                    'isBuyerMaker': d.get('T', 1) == 0,  # T=1 buy → isBuyerMaker=False
                    'quoteQty': str(quote_qty),
                    'time': int(d.get('t', 0) or 0),
                })
            except (TypeError, ValueError):
                continue
        return result

    async def get_order_book(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        normalized_symbol = MEXCConfig.futures_symbol_format(symbol)
        if not normalized_symbol:
            raise MEXCInvalidSymbolException(f'Invalid symbol: {symbol}')
        url = f'{MEXCConfig.FUTURES_BASE_URL}/api/v1/contract/depth'
        params = {'symbol': normalized_symbol, 'limit': min(limit, 100)}
        return await self._request('GET', url, params)
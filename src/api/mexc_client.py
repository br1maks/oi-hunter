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
        detail_url = f'{MEXCConfig.FUTURES_BASE_URL}/api/v1/contract/detail'
        detail_response = await self._request('GET', detail_url, {'symbol': normalized_symbol})
        if not detail_response.get('success'):
            raise MEXCNotFoundException(f'Contract details not found: {normalized_symbol}', status_code=404, response=detail_response)
        contract_size = float(detail_response.get('data', {}).get('contractSize', 0.0001))
        ticker_url = f'{MEXCConfig.FUTURES_BASE_URL}/api/v1/contract/ticker'
        ticker_response = await self._request('GET', ticker_url, {'symbol': normalized_symbol})
        if not ticker_response.get('success'):
            raise MEXCNotFoundException(f'Contract ticker not found: {normalized_symbol}', status_code=404, response=ticker_response)
        data = ticker_response.get('data', {})
        hold_vol = float(data.get('holdVol', 0))
        last_price = float(data.get('lastPrice', 0))
        open_interest_value = hold_vol * contract_size * last_price
        return {'symbol': normalized_symbol, 'openInterest': str(hold_vol), 'openInterestValue': str(open_interest_value), 'contractSize': str(contract_size), 'lastPrice': str(last_price), 'timestamp': data.get('timestamp', 0)}

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
        return await self._request('GET', url, params, weight=5)

    async def get_klines(self, symbol: str, interval: str='5m', limit: int=100) -> list[list]:
        normalized_symbol = MEXCConfig.spot_symbol_format(symbol)
        if not normalized_symbol:
            raise MEXCInvalidSymbolException(f'Invalid symbol: {symbol}')
        interval_map = {'1h': '60m'}
        normalized_interval = interval_map.get(interval, interval)
        limit = min(max(1, limit), 1000)
        url = f'{MEXCConfig.SPOT_BASE_URL}{MEXCConfig.SPOT_KLINES}'
        params = {'symbol': normalized_symbol, 'interval': normalized_interval, 'limit': limit}
        return await self._request('GET', url, params, weight=5)
import asyncio
import logging
from typing import Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)


class MarketCapCache:
    """Bulk-loads market cap data from CoinGecko, keyed by ticker symbol (uppercase).

    Usage:
        async with MarketCapCache() as cache:
            await cache.refresh(max_pages=4)
            mc = cache.get_market_cap('BTC')
    """

    COINGECKO_URL = 'https://api.coingecko.com/api/v3/coins/markets'
    COINGECKO_SEARCH_URL = 'https://api.coingecko.com/api/v3/search'
    COINPAPRIKA_SEARCH_URL = 'https://api.coinpaprika.com/v1/search'
    PAGE_SIZE = 250
    REQUEST_DELAY = 1.2  # seconds between CoinGecko pages (rate limit ~50 req/min free)

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._client: Optional[httpx.AsyncClient] = None
        # per-symbol fallback cache to avoid repeated API calls for the same miss
        self._fallback_cache: Dict[str, Optional[float]] = {}

    async def __aenter__(self) -> 'MarketCapCache':
        self._client = httpx.AsyncClient(timeout=30.0, headers={'Accept': 'application/json'})
        return self

    async def __aexit__(self, *args) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def size(self) -> int:
        return len(self._cache)

    async def refresh(self, max_pages: int = 8) -> int:
        """Bulk-load top coins from CoinGecko. Returns number of coins loaded."""
        if not self._client:
            raise RuntimeError('Use async with MarketCapCache() context manager')

        loaded = 0
        for page in range(1, max_pages + 1):
            try:
                resp = await self._client.get(
                    self.COINGECKO_URL,
                    params={
                        'vs_currency': 'usd',
                        'order': 'market_cap_desc',
                        'per_page': self.PAGE_SIZE,
                        'page': page,
                        'sparkline': 'false',
                    },
                )
                if resp.status_code == 429:
                    logger.warning('CoinGecko rate limited during bulk refresh, stopping early')
                    break
                resp.raise_for_status()
                coins = resp.json()
                if not coins:
                    break

                for coin in coins:
                    symbol = (coin.get('symbol') or '').upper()
                    if not symbol:
                        continue
                    new_mc = coin.get('market_cap') or 0
                    # keep highest market cap entry when duplicate symbols exist
                    existing = self._cache.get(symbol)
                    if existing and (existing.get('market_cap') or 0) >= new_mc:
                        continue
                    self._cache[symbol] = {
                        'market_cap': coin.get('market_cap'),
                        'fdv': coin.get('fully_diluted_valuation'),
                        'circulating_supply': coin.get('circulating_supply'),
                        'name': coin.get('name'),
                        'id': coin.get('id'),
                    }
                    loaded += 1

            except httpx.HTTPStatusError as e:
                logger.warning(f'CoinGecko page {page} HTTP error: {e}')
                break
            except Exception as e:
                logger.warning(f'CoinGecko page {page} failed: {e}')
                break

            if page < max_pages:
                await asyncio.sleep(self.REQUEST_DELAY)

        logger.info(f'MarketCapCache loaded {loaded} coins ({self.size} total in cache)')
        return loaded

    def get(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self._cache.get(symbol.upper())

    def get_market_cap(self, symbol: str) -> Optional[float]:
        entry = self._cache.get(symbol.upper())
        return entry.get('market_cap') if entry else None

    async def lookup_single(self, symbol: str) -> Optional[float]:
        """Fallback lookup for symbols not in bulk cache. Tries CoinGecko search then CoinPaprika."""
        symbol_upper = symbol.upper()

        # check fallback cache first (includes None results to avoid repeated misses)
        if symbol_upper in self._fallback_cache:
            return self._fallback_cache[symbol_upper]

        result = await self._try_coingecko_search(symbol_upper)
        if result is None:
            result = await self._try_coinpaprika(symbol_upper)

        self._fallback_cache[symbol_upper] = result
        return result

    async def _try_coingecko_search(self, symbol: str) -> Optional[float]:
        if not self._client:
            return None
        try:
            resp = await self._client.get(
                self.COINGECKO_SEARCH_URL,
                params={'query': symbol},
            )
            if resp.status_code != 200:
                return None
            coins = resp.json().get('coins', [])
            if not coins:
                return None
            # take the first result that matches symbol exactly
            coin_id = None
            for c in coins[:5]:
                if (c.get('symbol') or '').upper() == symbol:
                    coin_id = c.get('id')
                    break
            if not coin_id:
                return None

            await asyncio.sleep(0.5)
            price_resp = await self._client.get(
                'https://api.coingecko.com/api/v3/simple/price',
                params={
                    'ids': coin_id,
                    'vs_currencies': 'usd',
                    'include_market_cap': 'true',
                },
            )
            if price_resp.status_code != 200:
                return None
            data = price_resp.json().get(coin_id, {})
            mc = data.get('usd_market_cap')
            if mc:
                # store in main cache for future use
                self._cache[symbol] = {
                    'market_cap': mc,
                    'fdv': None,
                    'circulating_supply': None,
                    'name': None,
                    'id': coin_id,
                }
            return mc
        except Exception as e:
            logger.debug(f'CoinGecko search failed for {symbol}: {e}')
            return None

    async def _try_coinpaprika(self, symbol: str) -> Optional[float]:
        if not self._client:
            return None
        try:
            resp = await self._client.get(
                self.COINPAPRIKA_SEARCH_URL,
                params={'q': symbol, 'c': 'currencies', 'limit': 5},
            )
            if resp.status_code != 200:
                return None
            currencies = resp.json().get('currencies', [])
            coin_id = None
            for c in currencies:
                if (c.get('symbol') or '').upper() == symbol:
                    coin_id = c.get('id')
                    break
            if not coin_id:
                return None

            await asyncio.sleep(0.3)
            ticker_resp = await self._client.get(
                f'https://api.coinpaprika.com/v1/tickers/{coin_id}',
                params={'quotes': 'USD'},
            )
            if ticker_resp.status_code != 200:
                return None
            quotes = ticker_resp.json().get('quotes', {}).get('USD', {})
            mc = quotes.get('market_cap')
            if mc and mc > 0:
                self._cache[symbol] = {
                    'market_cap': mc,
                    'fdv': None,
                    'circulating_supply': None,
                    'name': None,
                    'id': coin_id,
                }
            return mc if mc and mc > 0 else None
        except Exception as e:
            logger.debug(f'CoinPaprika lookup failed for {symbol}: {e}')
            return None

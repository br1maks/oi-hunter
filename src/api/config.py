from typing import Final

class MEXCConfig:
    SPOT_BASE_URL: Final[str] = 'https://api.mexc.com'
    FUTURES_BASE_URL: Final[str] = 'https://api.mexc.com'
    SPOT_TICKER_24H: Final[str] = '/api/v3/ticker/24hr'
    SPOT_TRADES: Final[str] = '/api/v3/trades'
    SPOT_KLINES: Final[str] = '/api/v3/klines'
    FUTURES_OPEN_INTEREST: Final[str] = '/api/v1/contract/open_interest/{symbol}'
    FUTURES_FUNDING_RATE: Final[str] = '/api/v1/contract/funding_rate/{symbol}'
    FUTURES_TICKER: Final[str] = '/api/v1/contract/ticker'
    FUTURES_KLINES: Final[str] = '/api/v1/contract/kline'
    FUTURES_DEALS: Final[str] = '/api/v1/contract/deals'
    RATE_LIMIT_WEIGHT_PER_MINUTE: Final[int] = 1200
    RATE_LIMIT_REQUESTS_PER_SECOND: Final[int] = 20
    REQUEST_TIMEOUT: Final[int] = 20
    MAX_RETRIES: Final[int] = 3
    RETRY_DELAY: Final[float] = 1.0

    @staticmethod
    def spot_symbol_format(symbol: str) -> str:
        return symbol.replace('_', '').replace('-', '').replace('/', '').upper()

    @staticmethod
    def futures_symbol_format(symbol: str) -> str:
        normalized = symbol.replace('-', '').replace('/', '').upper()
        if '_' not in normalized and normalized.endswith('USDT'):
            base = normalized[:-4]
            normalized = f'{base}_USDT'
        return normalized
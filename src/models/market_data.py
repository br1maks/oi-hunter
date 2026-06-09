from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field

class MarketData(BaseModel):
    symbol: str = Field(..., description='Trading pair symbol (e.g., BTCUSDT)')
    exchange: str = Field(default='MEXC', description='Exchange name')
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description='Timestamp of data')
    price: float = Field(..., gt=0, description='Current price in USDT')
    high_24h: Optional[float] = Field(None, gt=0, description='24h high price')
    low_24h: Optional[float] = Field(None, gt=0, description='24h low price')
    volume_24h: float = Field(..., ge=0, description='24h trading volume in USDT')
    volume_1h: Optional[float] = Field(None, ge=0, description='1h trading volume in USDT')
    avg_volume_1h: Optional[float] = Field(None, ge=0, description='Average 1h volume (baseline)')
    price_change_1h: Optional[float] = Field(None, description='Price change % in 1h')
    price_change_4h: Optional[float] = Field(None, description='Price change % in 4h')
    price_change_24h: Optional[float] = Field(None, description='Price change % in 24h')
    atr: Optional[float] = Field(None, ge=0, description='Average True Range (volatility)')
    open_interest_usd: float = Field(..., ge=0, description='Open Interest in USD')
    oi_change_5m: Optional[float] = Field(None, description='OI change % in 5 minutes')
    oi_change_1h: Optional[float] = Field(None, description='OI change % in 1 hour')
    market_cap_usd: Optional[float] = Field(None, gt=0, description='Market Cap in USD (circulating) - None if not found')
    circulating_supply: Optional[float] = Field(None, gt=0, description='Circulating supply')
    fdv: Optional[float] = Field(None, gt=0, description='Fully Diluted Valuation')

    @property
    def oi_mc_ratio(self) -> Optional[float]:
        if self.market_cap_usd is None or self.market_cap_usd <= 0:
            return None
        return self.open_interest_usd / self.market_cap_usd
    funding_rate: float = Field(..., description='Current funding rate')
    buy_volume_5m: Optional[float] = Field(None, ge=0, description='Buy volume in 5 min')
    sell_volume_5m: Optional[float] = Field(None, ge=0, description='Sell volume in 5 min')
    trade_count_5m: Optional[int] = Field(None, ge=0, description='Number of individual trades in last 5 min')
    trade_count_2h: Optional[int] = Field(None, ge=0, description='Number of individual trades in last 2 hours')
    buy_volume_2h: Optional[float] = Field(None, ge=0, description='Buy volume in 2 hours')
    sell_volume_2h: Optional[float] = Field(None, ge=0, description='Sell volume in 2 hours')

    @property
    def aggression_5m(self) -> Optional[float]:
        if self.buy_volume_5m is None or self.sell_volume_5m is None:
            return None
        total = self.buy_volume_5m + self.sell_volume_5m
        if total == 0:
            return 50.0
        return self.buy_volume_5m / total * 100

    @property
    def aggression_2h(self) -> Optional[float]:
        if self.buy_volume_2h is None or self.sell_volume_2h is None:
            return None
        total = self.buy_volume_2h + self.sell_volume_2h
        if total == 0:
            return 50.0
        return self.buy_volume_2h / total * 100
    liquidation_detected: bool = Field(default=False, description='Liquidation cascade detected')
    liquidation_side: Optional[str] = Field(None, description='LONGS or SHORTS liquidated')
    liquidation_volume: Optional[float] = Field(None, description='Liquidation volume USD')
    liquidation_context: Optional[str] = Field(None, description='DURING or AFTER cascade')
    is_new_listing: bool = Field(default=False, description='Listed < 30 days ago')
    days_since_listing: Optional[int] = Field(None, ge=0, description='Days since listing on exchange')
    ob_bid_total: Optional[float] = Field(None, ge=0, description='Total bid volume (contracts, top 20)')
    ob_ask_total: Optional[float] = Field(None, ge=0, description='Total ask volume (contracts, top 20)')
    ob_bid_wall: Optional[float] = Field(None, ge=0, description='Largest single bid order (contracts)')
    ob_ask_wall: Optional[float] = Field(None, ge=0, description='Largest single ask order (contracts)')
    ob_t1_bid_vol: Optional[float] = Field(None, ge=0, description='Bid volume within 0.5% of price (Tier 1, immediate)')
    ob_t1_ask_vol: Optional[float] = Field(None, ge=0, description='Ask volume within 0.5% of price (Tier 1, immediate)')
    ob_t2_bid_vol: Optional[float] = Field(None, ge=0, description='Bid volume 0.5–2% below price (Tier 2, near-term)')
    ob_t2_ask_vol: Optional[float] = Field(None, ge=0, description='Ask volume 0.5–2% above price (Tier 2, near-term)')
    ob_spread_pct: Optional[float] = Field(None, ge=0, description='Bid-ask spread as % of price')

    # Squeeze Detector inputs (computed in DataAggregator._parse_klines)
    vci: Optional[float] = Field(None, ge=0, description='Volatility Compression Index (ATR_5/ATR_20, < 0.65 = compressed)')
    cfc: int = Field(default=0, ge=0, description='Consecutive flat candles count (range < 2.5%)')
    vwap: Optional[float] = Field(None, gt=0, description='24h VWAP (typical price weighted by volume)')

    class Config:
        json_schema_extra = {'example': {'symbol': 'LIGHTUSDT', 'exchange': 'MEXC', 'timestamp': '2026-01-26T18:30:00Z', 'price': 0.35, 'high_24h': 0.42, 'low_24h': 0.33, 'volume_24h': 1500000, 'volume_1h': 85000, 'avg_volume_1h': 62500, 'price_change_1h': -2.5, 'price_change_4h': -8.3, 'price_change_24h': -15.3, 'atr': 0.028, 'open_interest_usd': 1500000, 'oi_change_5m': -8.2, 'oi_change_1h': -15.0, 'market_cap_usd': 4285714, 'circulating_supply': 12244897, 'fdv': 8500000, 'funding_rate': -0.0012, 'buy_volume_5m': 85000, 'sell_volume_5m': 215000, 'buy_volume_2h': 2500000, 'sell_volume_2h': 3500000, 'liquidation_detected': True, 'liquidation_side': 'LONGS', 'liquidation_volume': 350000, 'liquidation_context': 'AFTER', 'is_new_listing': True, 'days_since_listing': 12}}
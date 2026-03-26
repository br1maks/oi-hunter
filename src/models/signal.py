from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field
from .analyzer_result import AnalyzerResult

class Target(BaseModel):
    target_number: Literal[1, 2, 3] = Field(..., description='Target number (T1/T2/T3)')
    target_price: float = Field(..., gt=0, description='Target price in USDT')
    percent_allocation: float = Field(..., ge=0, le=100, description='% of position to close')
    expected_gain_percent: float = Field(..., description='Expected gain % from entry')

    class Config:
        json_schema_extra = {'example': {'target_number': 1, 'target_price': 0.38, 'percent_allocation': 30.0, 'expected_gain_percent': 8.57}}

class Signal(BaseModel):
    symbol: str = Field(..., description='Trading pair (e.g., LIGHTUSDT)')
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description='Signal generation time')
    direction: Literal['LONG', 'SHORT'] = Field(..., description='Trade direction')
    entry_price: float = Field(..., gt=0, description='Entry price in USDT')
    stop_loss: float = Field(..., gt=0, description='Stop loss price in USDT')
    stop_loss_percent: float = Field(..., description='Stop loss distance in %')
    targets: list[Target] = Field(..., min_length=3, max_length=3, description='3 targets (T1/T2/T3)')
    overall_score: float = Field(..., ge=0, le=10, description='Weighted overall score (0-10)')
    confidence: float = Field(..., ge=0, le=1, description='Overall confidence (0-1)')
    analyzer_results: list[AnalyzerResult] = Field(..., min_length=1, description='All analyzer results that contributed')
    reason: str = Field(..., description='Human-readable explanation of the signal')
    key_factors: list[str] = Field(..., min_length=1, description='List of key factors (bullet points)')
    current_price: float = Field(..., gt=0, description='Current price at signal time')
    oi_mc_ratio: Optional[float] = Field(None, ge=0, description='Current OI/MC ratio (None if market cap unavailable)')
    market_cap_usd: Optional[float] = Field(None, gt=0, description='Current market cap (None if not found)')
    funding_rate: float = Field(..., description='Current funding rate')
    volume_24h: float = Field(..., ge=0, description='24h trading volume in USDT')
    price_change_24h: Optional[float] = Field(None, description='24h price change %')
    exchange: str = Field(default='MEXC', description='Exchange name')
    is_new_listing: bool = Field(default=False, description='Listed < 30 days ago')
    days_since_listing: Optional[int] = Field(None, ge=0, description='Days since listing')
    liquidation_detected: bool = Field(default=False, description='Liquidation cascade detected')
    liquidation_side: Optional[str] = Field(None, description='LONGS or SHORTS liquidated')
    liquidation_volume: Optional[float] = Field(None, ge=0, description='Liquidation volume USD')
    liquidation_context: Optional[str] = Field(None, description='DURING or AFTER cascade')

    @property
    def risk_reward_ratio(self) -> float:
        weighted_gain = sum((t.expected_gain_percent * (t.percent_allocation / 100.0) for t in self.targets))
        risk = abs(self.stop_loss_percent)
        if risk == 0:
            return 0.0
        return weighted_gain / risk

    class Config:
        json_schema_extra = {'example': {'symbol': 'LIGHTUSDT', 'timestamp': '2026-01-26T18:32:00Z', 'direction': 'LONG', 'entry_price': 0.35, 'stop_loss': 0.315, 'stop_loss_percent': -10.0, 'targets': [{'target_number': 1, 'target_price': 0.38, 'percent_allocation': 30.0, 'expected_gain_percent': 8.57}, {'target_number': 2, 'target_price': 0.42, 'percent_allocation': 40.0, 'expected_gain_percent': 20.0}, {'target_number': 3, 'target_price': 0.49, 'percent_allocation': 30.0, 'expected_gain_percent': 40.0}], 'overall_score': 8.7, 'confidence': 0.85, 'analyzer_results': [], 'reason': 'Strong LONG setup after liquidation cascade with OI/MC in optimal zone', 'key_factors': ['OI/MC ratio 0.28 in optimal zone (0.16-0.30)', 'Massive long liquidation detected ($300K+)', 'Signal generated AFTER cascade (capitulation complete)', 'Strong buy aggression shift: 95% → 78% (2H trend)', 'Negative funding rate (-0.12%) - shorts paying longs'], 'current_price': 0.35, 'oi_mc_ratio': 0.28, 'market_cap_usd': 4285714, 'funding_rate': -0.0012, 'volume_24h': 1500000, 'price_change_24h': -15.3, 'exchange': 'MEXC', 'is_new_listing': True, 'days_since_listing': 12, 'liquidation_detected': True, 'liquidation_side': 'LONGS', 'liquidation_volume': 350000, 'liquidation_context': 'AFTER'}}
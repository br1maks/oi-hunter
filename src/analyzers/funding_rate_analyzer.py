from typing import Optional
from .base import BaseAnalyzer
from ..models.market_data import MarketData
from ..models.analyzer_result import AnalyzerResult

class FundingRateAnalyzer(BaseAnalyzer):

    def __init__(self, weight: float=1.0):
        super().__init__(weight=weight)
        self._fr_cache: dict[str, float] = {}

    @property
    def analyzer_name(self) -> str:
        return 'Funding Rate Analyzer'

    def _validate_data(self, data: MarketData) -> bool:
        return super()._validate_data(data)

    def _score_funding(self, rate: float) -> tuple[float, float, str, str]:
        if rate <= -0.005:
            return (10.0, 0.0, 'VERY_BULLISH', 'Ultra-extreme negative - massive squeeze pressure')
        elif rate <= -0.001:
            return (10.0, 0.0, 'BULLISH', 'Extreme negative - strong squeeze potential')
        elif rate < -0.0008:
            return (9.0, 1.0, 'BULLISH', 'Very negative - high squeeze potential')
        elif rate < -0.0005:
            return (7.0, 2.0, 'BULLISH', 'Negative - moderate squeeze potential')
        elif rate < -0.0002:
            return (5.0, 3.0, 'SLIGHTLY_BULLISH', 'Slightly negative - mild squeeze potential')
        elif rate < 0:
            return (4.0, 3.0, 'NEUTRAL', 'Near neutral negative')
        elif rate < 0.0002:
            return (3.0, 4.0, 'NEUTRAL', 'Near neutral positive')
        elif rate < 0.0005:
            return (3.0, 5.0, 'SLIGHTLY_BEARISH', 'Slightly positive - longs starting to pay')
        elif rate < 0.0008:
            return (2.0, 6.0, 'BEARISH', 'Positive - longs paying, pressure building')
        elif rate < 0.001:
            return (1.0, 8.0, 'BEARISH', 'High positive - longs overleveraged')
        elif rate < 0.005:
            return (0.0, 10.0, 'VERY_BEARISH', 'Extreme positive - longs crushed!')
        else:
            return (0.0, 10.0, 'VERY_BEARISH', 'Ultra-extreme positive - massive long liquidation risk')

    def analyze(self, data: MarketData) -> Optional[AnalyzerResult]:
        if not self._validate_data(data):
            return None
        rate = data.funding_rate
        long_score, short_score, direction, interpretation = self._score_funding(rate)
        confidence = self._calculate_confidence(data)
        blocks_long = rate >= 0.005
        blocks_short = rate <= -0.005
        if abs(rate) >= 0.005:
            alert_level = 'critical'
        elif abs(rate) >= 0.001:
            alert_level = 'warning'
        else:
            alert_level = 'info'
        rate_pct = rate * 100
        reasoning = f'Funding {rate_pct:+.4f}% [{direction}] - {interpretation}'
        symbol = data.symbol
        if symbol in self._fr_cache:
            prev_rate = self._fr_cache[symbol]
            fr_velocity = rate - prev_rate
            if abs(fr_velocity) > 5e-05:
                v_pct = fr_velocity * 100
                if fr_velocity > 0.0001 and prev_rate < -0.0001:
                    long_score = min(10.0, long_score + 1.5)
                    reasoning += f' | FR↑ {v_pct:+.4f}% (short covering)'
                elif fr_velocity > 5e-05 and prev_rate < 0:
                    long_score = min(10.0, long_score + 0.5)
                    reasoning += f' | FR↑ recovering'
                elif fr_velocity > 0.0001 and prev_rate >= 0:
                    short_score = min(10.0, short_score + 0.5)
                    reasoning += f' | FR↑ {v_pct:+.4f}% (longs over-leveraging)'
                elif fr_velocity < -0.0001 and rate < 0:
                    long_score = min(10.0, long_score + 0.5)
                    reasoning += f' | FR↓ {v_pct:+.4f}% (shorts accumulating, squeeze fuel+)'
                elif fr_velocity < -0.0001:
                    reasoning += f' | FR↓ {v_pct:+.4f}% (funding weakening)'
        self._fr_cache[symbol] = rate
        # Conflict guard: extreme negative FR requires OI growth to produce a squeeze.
        # Shorts must keep building (OI growing) for a forced squeeze to happen.
        # OI declining = shorts covering voluntarily, no forced squeeze coming.
        # Cap long_score so FR alone cannot pass the signal threshold against bearish momentum.
        if (rate <= -0.001
                and data.oi_change_1h is not None and data.oi_change_1h < 0
                and data.price_change_1h is not None and data.price_change_1h < -1.0):
            if long_score > 6.0:
                long_score = 6.0
                reasoning += ' | No squeeze fuel: OI declining + price falling (capped 6.0)'
        return AnalyzerResult(analyzer_name=self.analyzer_name, long_score=long_score, short_score=short_score, confidence=confidence, reasoning=reasoning, blocks_long=blocks_long, blocks_short=blocks_short, alert_level=alert_level, key_value=rate_pct, key_label='Funding Rate %')

    def _calculate_confidence(self, data: MarketData) -> float:
        rate = abs(data.funding_rate)
        if rate >= 0.005:
            return 0.95
        elif rate >= 0.001:
            return 0.85
        elif rate >= 0.0005:
            return 0.8
        else:
            return 0.6
from typing import Optional
from .base import BaseAnalyzer
from ..models.market_data import MarketData
from ..models.analyzer_result import AnalyzerResult

class AggressionAnalyzer(BaseAnalyzer):
    SHIFT_THRESHOLD = 15.0

    def __init__(self, weight: float=1.5):
        super().__init__(weight=weight)

    @property
    def analyzer_name(self) -> str:
        return 'Aggression Analyzer'

    def _validate_data(self, data: MarketData) -> bool:
        if not super()._validate_data(data):
            return False
        if data.aggression_2h is None:
            return False
        return True

    def _score_aggression(self, agg: float) -> tuple[float, str]:
        if agg >= 85:
            return (10.0, 'Extreme buying pressure')
        elif agg >= 80:
            return (9.0, 'Very strong buying')
        elif agg >= 75:
            return (8.0, 'Strong buying')
        elif agg >= 70:
            return (7.0, 'Good buying')
        elif agg >= 65:
            return (6.0, 'Moderate buying')
        elif agg >= 60:
            return (5.0, 'Slight buying bias')
        elif agg >= 55:
            return (4.0, 'Balanced with slight buy bias')
        elif agg >= 50:
            return (3.0, 'Balanced')
        elif agg >= 45:
            return (2.0, 'Balanced with slight sell bias')
        elif agg >= 40:
            return (1.0, 'Slight selling bias')
        else:
            return (0.0, 'Strong selling pressure')

    def _detect_shift(self, agg_2h: float, agg_5m: float) -> dict:
        diff = agg_5m - agg_2h
        if abs(diff) <= self.SHIFT_THRESHOLD:
            return {'shift_detected': False, 'direction': None, 'magnitude': diff, 'long_modifier': 0.0, 'short_modifier': 0.0}
        abs_diff = abs(diff)
        if abs_diff >= 35:
            modifier = 4.0
        elif abs_diff >= 25:
            modifier = 3.0
        else:
            modifier = 1.5
        if diff < 0:
            return {'shift_detected': True, 'direction': 'WEAKENING', 'magnitude': abs_diff, 'long_modifier': -modifier, 'short_modifier': +modifier}
        else:
            return {'shift_detected': True, 'direction': 'STRENGTHENING', 'magnitude': abs_diff, 'long_modifier': +modifier, 'short_modifier': -modifier}

    def analyze(self, data: MarketData) -> Optional[AnalyzerResult]:
        if not self._validate_data(data):
            return None
        agg_2h = data.aggression_2h
        long_score, long_interp = self._score_aggression(agg_2h)
        short_score, short_interp = self._score_aggression(100.0 - agg_2h)
        reasoning_parts = [f'2H Aggression: {agg_2h:.1f}% - {long_interp}']
        if data.aggression_5m is not None:
            shift = self._detect_shift(agg_2h, data.aggression_5m)
            if shift['shift_detected']:
                long_score = max(0.0, min(10.0, long_score + shift['long_modifier']))
                short_score = max(0.0, min(10.0, short_score + shift['short_modifier']))
                reasoning_parts.append(f"5M: {data.aggression_5m:.1f}% | SHIFT {shift['direction']} ({shift['magnitude']:.1f}pp) → long {shift['long_modifier']:+.1f}, short {shift['short_modifier']:+.1f}")
            else:
                reasoning_parts.append(f'5M: {data.aggression_5m:.1f}% | No significant shift')
        blocks_long = agg_2h < 25.0
        blocks_short = agg_2h > 75.0
        if agg_2h >= 85 or agg_2h <= 15:
            alert_level = 'critical'
        elif agg_2h >= 75 or agg_2h <= 25:
            alert_level = 'warning'
        else:
            alert_level = 'info'
        confidence = self._calculate_confidence(data)
        reasoning = ' | '.join(reasoning_parts)
        return AnalyzerResult(analyzer_name=self.analyzer_name, long_score=long_score, short_score=short_score, confidence=confidence, reasoning=reasoning, blocks_long=blocks_long, blocks_short=blocks_short, alert_level=alert_level, key_value=agg_2h, key_label='2H Aggression %')

    def _calculate_confidence(self, data: MarketData) -> float:
        confidence = 0.7
        if data.aggression_5m is not None:
            confidence = 0.85
        if data.volume_24h and data.volume_24h > 1000000:
            confidence = min(1.0, confidence + 0.1)
        return confidence
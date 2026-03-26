from typing import Optional
from .base import BaseAnalyzer
from ..models.market_data import MarketData
from ..models.analyzer_result import AnalyzerResult

class VolumeSpikeAnalyzer(BaseAnalyzer):

    def __init__(self, weight: float=1.0):
        super().__init__(weight=weight)

    @property
    def analyzer_name(self) -> str:
        return 'Volume Spike Analyzer'

    def _validate_data(self, data: MarketData) -> bool:
        if not super()._validate_data(data):
            return False
        if data.volume_1h is None or data.avg_volume_1h is None:
            return False
        if data.volume_1h <= 0 or data.avg_volume_1h <= 0:
            return False
        return True

    def _calculate_volume_ratio(self, data: MarketData) -> float:
        return data.volume_1h / data.avg_volume_1h

    def _score_spike(self, ratio: float) -> float:
        if ratio >= 5.0:
            return 10.0
        elif ratio >= 3.0:
            return 9.0
        elif ratio >= 2.0:
            return 7.0
        elif ratio >= 1.5:
            return 5.0
        else:
            return 0.0

    def analyze(self, data: MarketData) -> Optional[AnalyzerResult]:
        if not self._validate_data(data):
            return None
        volume_ratio = self._calculate_volume_ratio(data)
        spike_score = self._score_spike(volume_ratio)
        if spike_score == 0:
            return None
        price_change = data.price_change_1h if data.price_change_1h is not None else 0
        if price_change < -5:
            long_score = 0.0
            short_score = spike_score
            direction = 'BEARISH'
            blocks_long = volume_ratio >= 2.0
            blocks_short = False
            is_early_detection = False
        elif price_change > 5:
            long_score = spike_score
            short_score = 0.0
            direction = 'BULLISH'
            blocks_long = False
            blocks_short = volume_ratio >= 2.0
            is_early_detection = False
        else:
            aggression = data.aggression_2h
            if aggression is None:
                return None
            if aggression >= 70 and volume_ratio >= 2.0:
                long_score = spike_score * 0.7
                short_score = 0.0
                direction = 'PRE_PUMP'
                blocks_long = False
                blocks_short = True
                is_early_detection = True
            elif aggression <= 30 and volume_ratio >= 2.0:
                long_score = 0.0
                short_score = spike_score * 0.7
                direction = 'PRE_DUMP'
                blocks_long = True
                blocks_short = False
                is_early_detection = True
            else:
                return None
        if volume_ratio >= 5.0:
            alert_level = 'critical'
        elif volume_ratio >= 2.0:
            alert_level = 'warning'
        else:
            alert_level = 'info'
        if is_early_detection:
            aggression = data.aggression_2h
            reasoning = f'Volume spike {volume_ratio:.1f}x | Direction: {direction} (EARLY!) | Aggression: {aggression:.0f}% | Price: {price_change:+.1f}% (not moved yet)'
        else:
            reasoning = f'Volume spike {volume_ratio:.1f}x | Direction: {direction} | Price change: {price_change:+.1f}%'
        confidence = self._calculate_confidence(data, volume_ratio, is_early_detection)
        return AnalyzerResult(analyzer_name=self.analyzer_name, long_score=long_score, short_score=short_score, confidence=confidence, reasoning=reasoning, blocks_long=blocks_long, blocks_short=blocks_short, alert_level=alert_level, key_value=volume_ratio, key_label='Volume Ratio')

    def _calculate_confidence(self, data: MarketData, volume_ratio: float, is_early_detection: bool=False) -> float:
        if is_early_detection:
            confidence = 0.5
            confidence += 0.1
            if volume_ratio >= 5.0:
                confidence += 0.2
            elif volume_ratio >= 3.0:
                confidence += 0.15
            elif volume_ratio >= 2.0:
                confidence += 0.1
            return min(0.75, confidence)
        else:
            confidence = 0.5
            if data.price_change_1h is not None:
                confidence += 0.2
            if volume_ratio >= 3.0:
                confidence += 0.2
            elif volume_ratio >= 2.0:
                confidence += 0.1
            return min(1.0, confidence)
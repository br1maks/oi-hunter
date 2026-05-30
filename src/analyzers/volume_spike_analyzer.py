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

    def _price_move_threshold(self, data: MarketData) -> float:
        if data.atr and data.atr > 0:
            atr_pct = data.atr / data.price * 100
            return min(15.0, max(5.0, atr_pct * 0.3))
        return 5.0

    def _score_spike(self, ratio: float) -> float:
        if ratio >= 5.0:
            return 10.0
        elif ratio >= 3.0:
            return 9.0
        elif ratio >= 2.0:
            return 7.0
        elif ratio >= 1.75:
            return 6.0
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
        price_threshold = self._price_move_threshold(data)
        if price_change <= -price_threshold:
            long_score = 0.0
            short_score = spike_score
            direction = 'BEARISH'
            blocks_long = volume_ratio >= 2.0
            blocks_short = False
            is_early_detection = False
        elif price_change >= price_threshold:
            long_score = spike_score
            short_score = 0.0
            direction = 'BULLISH'
            blocks_long = False
            blocks_short = volume_ratio >= 2.0
            is_early_detection = False
        else:
            # PRE_PUMP/PRE_DUMP requires a reliable aggression reading.
            # Prefer 5m (current momentum) if count is sufficient; fall back to 2h if also sufficient.
            # Without enough trades the reading is noise — don't fire early detection on it.
            if (data.aggression_5m is not None
                    and data.trade_count_5m is not None
                    and data.trade_count_5m >= 20):
                aggression = data.aggression_5m
                agg_source = '5M'
            elif (data.aggression_2h is not None
                    and data.trade_count_2h is not None
                    and data.trade_count_2h >= 50):
                aggression = data.aggression_2h
                agg_source = '2H'
            else:
                return None
            if aggression >= 70 and volume_ratio >= 3.0:
                long_score = spike_score * 0.7
                short_score = 0.0
                direction = 'PRE_PUMP'
                blocks_long = False
                blocks_short = True
                is_early_detection = True
            elif aggression <= 30 and volume_ratio >= 3.0:
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
        elif volume_ratio >= 1.75:
            alert_level = 'warning'
        else:
            alert_level = 'info'
        if is_early_detection:
            price_str = f'{data.price_change_1h:+.1f}%' if data.price_change_1h is not None else 'N/A'
            reasoning = f'Volume spike {volume_ratio:.1f}x | Direction: {direction} (EARLY!) | Aggression ({agg_source}): {aggression:.0f}% | Price: {price_str}'
        else:
            reasoning = f'Volume spike {volume_ratio:.1f}x | Direction: {direction} | Price change: {price_change:+.1f}%'
        confidence = self._calculate_confidence(data, volume_ratio, is_early_detection)
        return AnalyzerResult(analyzer_name=self.analyzer_name, long_score=long_score, short_score=short_score, confidence=confidence, reasoning=reasoning, blocks_long=blocks_long, blocks_short=blocks_short, alert_level=alert_level, key_value=volume_ratio, key_label='Volume Ratio')

    def _calculate_confidence(self, data: MarketData, volume_ratio: float, is_early_detection: bool=False) -> float:
        if is_early_detection:
            if volume_ratio >= 5.0:
                return 0.70
            return 0.65
        else:
            if volume_ratio >= 3.0:
                return 0.9
            elif volume_ratio >= 2.0:
                return 0.8
            return 0.7

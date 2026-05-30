from typing import Optional
from .base import BaseAnalyzer
from ..models.market_data import MarketData
from ..models.analyzer_result import AnalyzerResult

class AlreadyPumpedAnalyzer(BaseAnalyzer):

    def __init__(self, weight: float=0.5):
        super().__init__(weight=weight)

    @property
    def analyzer_name(self) -> str:
        return 'Already Pumped Analyzer'

    def _validate_data(self, data: MarketData) -> bool:
        if not super()._validate_data(data):
            return False
        if data.price_change_4h is None and data.price_change_24h is None:
            return False
        return True

    def _get_pump_percent(self, data: MarketData) -> float:
        changes = []
        if data.price_change_4h is not None:
            changes.append(data.price_change_4h)
        if data.price_change_24h is not None:
            changes.append(data.price_change_24h)
        if not changes:
            return 0.0
        max_change = max(changes)
        return max(0.0, max_change)

    def analyze(self, data: MarketData) -> Optional[AnalyzerResult]:
        if not self._validate_data(data):
            return None
        pump = self._get_pump_percent(data)
        if pump < 15:
            return None
        if pump > 200:
            long_score = 0.0
            short_score = 10.0
            blocks_long = True
            alert_level = 'critical'
            severity = 'EXTREME'
        elif pump > 100:
            long_score = 0.0
            short_score = 9.0
            blocks_long = True
            alert_level = 'critical'
            severity = 'VERY HIGH'
        elif pump > 50:
            long_score = 1.0
            short_score = 8.0
            blocks_long = True
            alert_level = 'warning'
            severity = 'HIGH'
        elif pump > 30:
            long_score = 3.0
            short_score = 6.0
            blocks_long = False
            alert_level = 'warning'
            severity = 'MODERATE'
        else:
            long_score = 4.5
            short_score = 5.0
            blocks_long = False
            alert_level = 'info'
            severity = 'LOW'
        is_fresh_listing = data.is_new_listing and (data.days_since_listing is None or data.days_since_listing <= 7)
        if is_fresh_listing:
            blocks_long = False
            short_score = round(short_score * 0.5, 1)
            if alert_level == 'critical':
                alert_level = 'warning'
            reasoning = f'[NEW LISTING] Pumped +{pump:.1f}% | {severity} pump | Launch behavior — short risky'
        elif blocks_long:
            reasoning = f'Already pumped +{pump:.1f}% | Risk: {severity} | LONG blocked | Short setup'
        else:
            reasoning = f'Already pumped +{pump:.1f}% | Risk: {severity} | Long entry risk elevated'
        confidence = self._calculate_confidence(data, pump)
        return AnalyzerResult(analyzer_name=self.analyzer_name, long_score=long_score, short_score=short_score, confidence=confidence, reasoning=reasoning, blocks_long=blocks_long, blocks_short=False, alert_level=alert_level, key_value=pump, key_label='Pump %')

    def _calculate_confidence(self, data: MarketData, pump: float) -> float:
        both = data.price_change_4h is not None and data.price_change_24h is not None
        if pump > 100:
            return 1.0 if both else 0.8
        elif pump > 50:
            return 0.9 if both else 0.7
        return 0.8 if both else 0.6
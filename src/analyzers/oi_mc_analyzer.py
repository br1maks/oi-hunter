from typing import Optional
from .base import BaseAnalyzer
from ..models.market_data import MarketData
from ..models.analyzer_result import AnalyzerResult

class OIMCAnalyzer(BaseAnalyzer):

    def __init__(self, weight: float=2.0):
        super().__init__(weight=weight)

    @property
    def analyzer_name(self) -> str:
        return 'OI/MC Analyzer'

    def _validate_data(self, data: MarketData) -> bool:
        if not super()._validate_data(data):
            return False
        if data.open_interest_usd <= 0:
            return False
        return True

    def _score_for_long(self, ratio: float) -> tuple[float, str]:
        if ratio < 0.1:
            return (2.0, 'Too low - insufficient fuel')
        elif ratio < 0.16:
            return (5.0, 'Low - building interest')
        elif ratio < 0.2:
            return (9.0, 'Optimal lower range - healthy leverage')
        elif ratio < 0.26:
            return (10.0, 'Optimal - perfect sweet spot!')
        elif ratio < 0.3:
            return (9.0, 'Optimal upper range - still healthy')
        elif ratio < 0.35:
            return (7.0, 'Elevated - caution starting')
        elif ratio < 0.4:
            return (6.0, 'Elevated - manageable but watchful')
        elif ratio < 0.45:
            return (4.0, 'High - significant caution needed')
        elif ratio < 0.5:
            return (3.0, 'High - profit-taking zone')
        elif ratio < 0.55:
            return (1.0, 'Danger - overleveraged, correction likely')
        elif ratio < 0.6:
            return (0.0, 'Danger - exit existing longs')
        else:
            return (0.0, 'EXTREME DANGER - never long!')

    def _score_for_short(self, ratio: float) -> tuple[float, str]:
        if ratio < 0.4:
            return (0.0, 'Too low for short')
        elif ratio < 0.5:
            return (2.0, 'Slightly elevated - not yet')
        elif ratio < 0.55:
            return (4.0, 'Moderate - early short setup')
        elif ratio < 0.6:
            return (6.0, 'High - decent short opportunity')
        elif ratio < 0.65:
            return (8.0, 'Very high - good short setup')
        elif ratio < 0.7:
            return (9.0, 'Extreme - excellent short!')
        elif ratio < 0.75:
            return (10.0, 'CRITICAL - perfect short setup!')
        else:
            return (10.0, 'EXTREME DANGER - maximum short opportunity!')

    def analyze(self, data: MarketData) -> Optional[AnalyzerResult]:
        if not self._validate_data(data):
            return None
        if data.market_cap_usd is None or data.market_cap_usd <= 0:
            return AnalyzerResult(analyzer_name=self.analyzer_name, long_score=5.0, short_score=5.0, confidence=0.3, reasoning='OI/MC unavailable — market cap not found on CoinGecko', blocks_long=False, blocks_short=False, alert_level='info', key_value=None, key_label='OI/MC Ratio')
        ratio = data.oi_mc_ratio
        long_score, long_interp = self._score_for_long(ratio)
        short_score, short_interp = self._score_for_short(ratio)
        blocks_long = ratio >= 0.55
        blocks_short = False
        if ratio >= 0.6:
            alert_level = 'critical'
        elif ratio >= 0.5:
            alert_level = 'warning'
        else:
            alert_level = 'info'
        if ratio < 0.3:
            risk = 'LOW'
        elif ratio < 0.5:
            risk = 'MEDIUM'
        elif ratio < 0.7:
            risk = 'HIGH'
        else:
            risk = 'EXTREME'
        confidence = self._calculate_confidence(data)
        reasoning = f'OI/MC ratio {ratio:.4f} [{risk}] - Long: {long_interp} | Short: {short_interp} (OI: ${data.open_interest_usd:,.0f}, MC: ${data.market_cap_usd:,.0f})'
        return AnalyzerResult(analyzer_name=self.analyzer_name, long_score=long_score, short_score=short_score, confidence=confidence, reasoning=reasoning, blocks_long=blocks_long, blocks_short=blocks_short, alert_level=alert_level, key_value=ratio, key_label='OI/MC Ratio')

    def _calculate_confidence(self, data: MarketData) -> float:
        base = 0.7
        if data.volume_24h > 1000000:
            base += 0.15
        elif data.volume_24h > 100000:
            base += 0.1
        if data.oi_change_1h is not None:
            base += 0.1
        return min(base, 1.0)
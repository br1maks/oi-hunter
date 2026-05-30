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
        if ratio < 0.10:
            return (2.0, 'Too low - insufficient futures interest')
        elif ratio < 0.13:
            return (4.0, 'Low - interest slowly building')
        elif ratio < 0.16:
            return (6.5, 'Low-mid - momentum gaining')
        elif ratio < 0.20:
            return (9.0, 'Optimal lower range - healthy leverage')
        elif ratio < 0.26:
            return (10.0, 'Optimal - perfect sweet spot!')
        elif ratio < 0.30:
            return (9.0, 'Optimal upper range - still healthy')
        elif ratio < 0.35:
            return (7.0, 'Elevated - caution starting')
        elif ratio < 0.40:
            return (5.5, 'Elevated - manageable but watchful')
        elif ratio < 0.45:
            return (4.0, 'High - significant caution needed')
        elif ratio < 0.50:
            return (2.0, 'High - approaching danger zone')
        else:
            return (0.0, 'Danger - overleveraged, longs blocked')

    def _score_for_short(self, ratio: float) -> tuple[float, str]:
        if ratio < 0.40:
            return (0.0, 'Too low for short')
        elif ratio < 0.46:
            return (2.0, 'Slightly elevated - not yet')
        elif ratio < 0.50:
            return (3.5, 'Elevated - short setup forming')
        elif ratio < 0.55:
            return (5.0, 'Moderate danger - early short setup')
        elif ratio < 0.60:
            return (6.0, 'High - decent short opportunity')
        elif ratio < 0.65:
            return (8.0, 'Very high - good short setup')
        elif ratio < 0.70:
            return (9.0, 'Extreme - excellent short!')
        elif ratio < 0.75:
            return (10.0, 'CRITICAL - perfect short setup!')
        else:
            return (10.0, 'EXTREME DANGER - maximum short opportunity!')

    def analyze(self, data: MarketData) -> Optional[AnalyzerResult]:
        if not self._validate_data(data):
            return None
        if data.market_cap_usd is None or data.market_cap_usd <= 0:
            return AnalyzerResult(analyzer_name=self.analyzer_name, long_score=5.0, short_score=5.0, confidence=0.3, reasoning='OI/MC unavailable — market cap not found', blocks_long=False, blocks_short=False, alert_level='info', key_value=None, key_label='OI/MC Ratio')
        ratio = data.oi_mc_ratio
        long_score, long_interp = self._score_for_long(ratio)
        short_score, short_interp = self._score_for_short(ratio)

        # OI trend adjustment: direction matters, not just the snapshot value.
        # For longs: fast-rising OI in elevated zone = worsening; falling OI = deleveraging.
        # For shorts: OI surging above danger threshold = more trapped longs = better short.
        oi_trend_note = ''
        if data.oi_change_1h is not None:
            oi_1h = data.oi_change_1h
            if oi_1h > 5.0 and ratio > 0.30:
                long_score = max(0.0, long_score - 1.5)
                oi_trend_note = f' | OI +{oi_1h:.1f}% rising fast'
            elif oi_1h < -3.0 and 0.35 <= ratio < 0.50:
                # Only apply deleverage bonus below the block threshold —
                # above 0.50 longs are blocked anyway, the bonus would be wasted.
                long_score = min(10.0, long_score + 1.0)
                oi_trend_note = f' | OI {oi_1h:.1f}% deleveraging'
            if oi_1h > 5.0 and ratio >= 0.50:
                # Longs piling into danger zone at high speed = more squeeze fuel.
                short_score = min(10.0, short_score + 1.5)
                oi_trend_note += ' | surge boosts short'

        blocks_long = ratio >= 0.50
        blocks_short = False
        if ratio >= 0.60:
            alert_level = 'critical'
        elif ratio >= 0.50:
            alert_level = 'warning'
        else:
            alert_level = 'info'
        if ratio < 0.30:
            risk = 'LOW'
        elif ratio < 0.50:
            risk = 'MEDIUM'
        elif ratio < 0.70:
            risk = 'HIGH'
        else:
            risk = 'EXTREME'
        confidence = self._calculate_confidence(data)
        reasoning = f'OI/MC ratio {ratio:.4f} [{risk}] - Long: {long_interp} | Short: {short_interp}{oi_trend_note} (OI: ${data.open_interest_usd:,.0f}, MC: ${data.market_cap_usd:,.0f})'
        return AnalyzerResult(analyzer_name=self.analyzer_name, long_score=long_score, short_score=short_score, confidence=confidence, reasoning=reasoning, blocks_long=blocks_long, blocks_short=blocks_short, alert_level=alert_level, key_value=ratio, key_label='OI/MC Ratio')

    def _calculate_confidence(self, data: MarketData) -> float:
        base = 0.7
        if data.volume_24h > 1000000:
            base += 0.15
        elif data.volume_24h > 100000:
            base += 0.1
        if data.oi_change_1h is not None:
            base += 0.1
        # Extreme ratios are historically the most reliable signals.
        # Near 0.20-0.26 (sweet spot) or above 0.65 (extreme danger) — high confidence.
        ratio = data.oi_mc_ratio if (data.market_cap_usd and data.market_cap_usd > 0) else None
        if ratio is not None:
            if ratio >= 0.65 or (0.18 <= ratio <= 0.28):
                base += 0.05
        return min(base, 1.0)
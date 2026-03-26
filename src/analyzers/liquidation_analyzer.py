from typing import Optional
from .base import BaseAnalyzer
from ..models.market_data import MarketData
from ..models.analyzer_result import AnalyzerResult

class LiquidationAnalyzer(BaseAnalyzer):

    def __init__(self, weight: float=1.0):
        super().__init__(weight=weight)

    @property
    def analyzer_name(self) -> str:
        return 'Liquidation Analyzer'

    def _validate_data(self, data: MarketData) -> bool:
        if not super()._validate_data(data):
            return False
        if data.oi_change_1h is None and data.oi_change_5m is None:
            return False
        return True

    def _detect_liquidation(self, data: MarketData) -> dict:
        if data.liquidation_detected and data.liquidation_side:
            return {'detected': True, 'side': data.liquidation_side, 'context': data.liquidation_context or 'UNCERTAIN', 'severity': min(1.0, (data.liquidation_volume or 0) / max(data.volume_24h, 1) * 24)}
        oi_change = data.oi_change_1h if data.oi_change_1h is not None else data.oi_change_5m
        if oi_change is None:
            return {'detected': False, 'side': None, 'context': 'UNCERTAIN', 'severity': 0}
        price_change = data.price_change_1h if data.price_change_1h is not None else 0
        volume_ratio = 1.0
        if data.volume_1h and data.avg_volume_1h and (data.avg_volume_1h > 0):
            volume_ratio = data.volume_1h / data.avg_volume_1h
        oi_drop = oi_change < -5
        volume_elevated = volume_ratio > 2.0
        price_moved = abs(price_change) > 5
        if not oi_drop:
            return {'detected': False, 'side': None, 'context': 'UNCERTAIN', 'severity': 0}
        if oi_change < -20:
            severity = 1.0
        elif oi_change < -15:
            severity = 0.8
        elif oi_change < -10:
            severity = 0.6
        else:
            severity = 0.4
        if price_change < -3:
            side = 'LONGS'
        elif price_change > 3:
            side = 'SHORTS'
        else:
            side = None
        if abs(price_change) > 5 and oi_change <= -10 and (volume_ratio > 2.0):
            context = 'DURING'
        elif abs(price_change) < 3 and volume_ratio < 1.5:
            context = 'AFTER'
        else:
            context = 'UNCERTAIN'
        if oi_change <= -10:
            detected = True
        else:
            detected = volume_elevated or price_moved
        return {'detected': detected, 'side': side, 'context': context, 'severity': severity}

    def _detect_flat_oi_divergence(self, data: MarketData) -> Optional[dict]:
        if data.oi_change_1h is None or data.price_change_1h is None:
            return None
        oi_change = data.oi_change_1h
        price_change = data.price_change_1h
        oi_flat = abs(oi_change) < 2.0
        price_falling = price_change < -3.0
        if not (oi_flat and price_falling):
            return None
        if price_change < -10:
            severity = 1.0
        elif price_change < -7:
            severity = 0.8
        elif price_change < -5:
            severity = 0.6
        else:
            severity = 0.4
        return {'oi_change': oi_change, 'price_change': price_change, 'severity': severity}

    def _build_possible_drawdown_result(self, divergence: dict, data: MarketData) -> AnalyzerResult:
        severity = divergence['severity']
        long_score = 0.0
        short_score = 5.0 + severity * 2.0
        short_score = min(7.0, short_score)
        alert_level = 'warning' if severity >= 0.6 else 'info'
        confidence = self._calculate_confidence(data) * 0.8
        reasoning = f"W DAO Possible Drawdown: OI flat ({divergence['oi_change']:+.1f}%) while price falling ({divergence['price_change']:+.1f}%) | traders holding losing longs, cascade imminent"
        return AnalyzerResult(analyzer_name=self.analyzer_name, long_score=long_score, short_score=short_score, confidence=confidence, reasoning=reasoning, blocks_long=True, blocks_short=False, alert_level=alert_level, key_value=divergence['price_change'], key_label='Price Drop (OI Flat)')

    def _detect_price_up_oi_down(self, data: MarketData) -> Optional[dict]:
        if data.oi_change_1h is None or data.price_change_1h is None:
            return None
        oi_change = data.oi_change_1h
        price_change = data.price_change_1h
        if price_change <= 2.0 or oi_change >= -3.0:
            return None
        severity = min(1.0, (abs(oi_change) - 3.0) / 2.0)
        return {'oi_change': oi_change, 'price_change': price_change, 'severity': severity}

    def _detect_price_down_oi_up(self, data: MarketData) -> Optional[dict]:
        if data.oi_change_1h is None or data.price_change_1h is None:
            return None
        oi_change = data.oi_change_1h
        price_change = data.price_change_1h
        if price_change >= -2.0 or oi_change <= 3.0:
            return None
        severity = min(1.0, (oi_change - 3.0) / 7.0)
        return {'oi_change': oi_change, 'price_change': price_change, 'severity': severity}

    def _build_price_down_oi_up_result(self, divergence: dict, data: MarketData) -> AnalyzerResult:
        severity = divergence['severity']
        long_score = 0.0
        short_score = min(7.0, 5.0 + severity * 2.0)
        alert_level = 'warning' if severity >= 0.5 else 'info'
        confidence = self._calculate_confidence(data) * 0.85
        reasoning = f"Price↓+OI↑ bearish confirmation: price {divergence['price_change']:+.1f}%, OI {divergence['oi_change']:+.1f}% | new shorts opening into falling price — downtrend confirmed"
        return AnalyzerResult(analyzer_name=self.analyzer_name, long_score=long_score, short_score=short_score, confidence=confidence, reasoning=reasoning, blocks_long=True, blocks_short=False, alert_level=alert_level, key_value=divergence['oi_change'], key_label='OI Δ (Price Down)')

    def _build_price_up_oi_down_result(self, divergence: dict, data: MarketData) -> AnalyzerResult:
        severity = divergence['severity']
        long_score = 0.0
        short_score = min(7.0, 5.0 + severity * 2.0)
        alert_level = 'warning' if severity >= 0.5 else 'info'
        confidence = self._calculate_confidence(data) * 0.8
        reasoning = f"Price↑+OI↓ divergence: price {divergence['price_change']:+.1f}%, OI {divergence['oi_change']:+.1f}% | longs exiting into strength — distribution, EXIT longs"
        return AnalyzerResult(analyzer_name=self.analyzer_name, long_score=long_score, short_score=short_score, confidence=confidence, reasoning=reasoning, blocks_long=True, blocks_short=False, alert_level=alert_level, key_value=divergence['oi_change'], key_label='OI Δ (Price Up)')

    def analyze(self, data: MarketData) -> Optional[AnalyzerResult]:
        if not self._validate_data(data):
            return None
        liq = self._detect_liquidation(data)
        if not liq['detected']:
            divergence = self._detect_flat_oi_divergence(data)
            if divergence:
                return self._build_possible_drawdown_result(divergence, data)
            exit_signal = self._detect_price_up_oi_down(data)
            if exit_signal:
                return self._build_price_up_oi_down_result(exit_signal, data)
            bearish_confirm = self._detect_price_down_oi_up(data)
            if bearish_confirm:
                return self._build_price_down_oi_up_result(bearish_confirm, data)
            return None
        side = liq['side']
        context = liq['context']
        severity = liq['severity']
        if context == 'DURING':
            if side == 'LONGS':
                long_score = 0.0
                short_score = 8.0 + severity * 2.0
                blocks_long = True
                blocks_short = False
            elif side == 'SHORTS':
                long_score = 8.0 + severity * 2.0
                short_score = 0.0
                blocks_long = False
                blocks_short = True
            else:
                long_score = 3.0
                short_score = 3.0
                blocks_long = False
                blocks_short = False
        elif context == 'AFTER':
            if side == 'LONGS':
                long_score = 7.0 + severity * 3.0
                short_score = 1.0
                blocks_long = False
                blocks_short = False
            elif side == 'SHORTS':
                long_score = 1.0
                short_score = 7.0 + severity * 3.0
                blocks_long = False
                blocks_short = False
            else:
                long_score = 4.0
                short_score = 4.0
                blocks_long = False
                blocks_short = False
        else:
            long_score = 3.0
            short_score = 3.0
            blocks_long = False
            blocks_short = False
        long_score = max(0.0, min(10.0, long_score))
        short_score = max(0.0, min(10.0, short_score))
        if severity >= 0.8:
            alert_level = 'critical'
        elif severity >= 0.4:
            alert_level = 'warning'
        else:
            alert_level = 'info'
        oi_change = data.oi_change_1h if data.oi_change_1h is not None else data.oi_change_5m
        reasoning = f"Liquidation {context}: {side or 'UNKNOWN'} side | OI change: {oi_change:+.1f}% | Severity: {severity:.1f}"
        confidence = self._calculate_confidence(data)
        return AnalyzerResult(analyzer_name=self.analyzer_name, long_score=long_score, short_score=short_score, confidence=confidence, reasoning=reasoning, blocks_long=blocks_long, blocks_short=blocks_short, alert_level=alert_level, key_value=oi_change, key_label='OI Change %')

    def _calculate_confidence(self, data: MarketData) -> float:
        if data.liquidation_detected and data.liquidation_side:
            return 0.9
        confidence = 0.5
        if data.oi_change_1h is not None:
            confidence += 0.1
        if data.volume_1h and data.avg_volume_1h:
            confidence += 0.1
        if data.price_change_1h is not None:
            confidence += 0.1
        return min(1.0, confidence)
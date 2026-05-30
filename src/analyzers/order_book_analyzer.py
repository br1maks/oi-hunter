from typing import Optional
from .base import BaseAnalyzer
from ..models.market_data import MarketData
from ..models.analyzer_result import AnalyzerResult

class OrderBookAnalyzer(BaseAnalyzer):
    WALL_THRESHOLD = 0.3
    T1_THRESHOLD = 0.3
    T2_THRESHOLD = 0.4

    def __init__(self, weight: float=1.0):
        super().__init__(weight=weight)

    @property
    def analyzer_name(self) -> str:
        return 'Order Book'

    def _validate_data(self, data: MarketData) -> bool:
        if not super()._validate_data(data):
            return False
        if data.ob_bid_total is None or data.ob_ask_total is None:
            return False
        if data.ob_bid_total <= 0 or data.ob_ask_total <= 0:
            return False
        return True

    def _score_imbalance(self, ratio: float) -> tuple[float, float, str]:
        if ratio >= 3.0:
            return (9.0, 1.0, f'Bids dominate {ratio:.1f}x — strong buy pressure')
        elif ratio >= 2.0:
            return (8.0, 2.0, f'Bids dominate {ratio:.1f}x — buyers in control')
        elif ratio >= 1.5:
            return (7.0, 3.0, f'Bids slightly dominant {ratio:.1f}x — mild buy pressure')
        elif ratio >= 1.2:
            return (6.0, 4.0, f'Balanced book, bids lead {ratio:.1f}x')
        elif ratio >= 0.83:
            return (5.0, 5.0, f'Balanced order book {ratio:.1f}x — neutral')
        elif ratio > 0.67:
            return (4.0, 6.0, f'Asks slightly dominant {1/ratio:.1f}x — mild sell pressure')
        elif ratio > 0.5:
            return (3.0, 7.0, f'Asks dominate {1/ratio:.1f}x — sellers in control')
        elif ratio > 0.33:
            return (2.0, 8.0, f'Asks dominate {1/ratio:.1f}x — strong sell pressure')
        else:
            return (1.0, 9.0, f'Asks dominate {1/ratio:.1f}x — extreme sell pressure')

    def analyze(self, data: MarketData) -> Optional[AnalyzerResult]:
        if not self._validate_data(data):
            return None
        bid_total = data.ob_bid_total
        ask_total = data.ob_ask_total
        imbalance = bid_total / ask_total
        long_score, short_score, interpretation = self._score_imbalance(imbalance)
        tier_details: list[str] = []
        mod_long = 0.0
        mod_short = 0.0
        if data.ob_t1_ask_vol is not None and ask_total > 0:
            t1_ask_pct = data.ob_t1_ask_vol / ask_total
            if t1_ask_pct >= self.T1_THRESHOLD:
                mod_short += 2.0
                mod_long -= 0.5
                tier_details.append(f'T1 Ask {t1_ask_pct:.0%} immediate')
        if data.ob_t1_bid_vol is not None and bid_total > 0:
            t1_bid_pct = data.ob_t1_bid_vol / bid_total
            if t1_bid_pct >= self.T1_THRESHOLD:
                mod_long += 2.0
                mod_short -= 0.5
                tier_details.append(f'T1 Bid {t1_bid_pct:.0%} immediate')
        if data.ob_t2_ask_vol is not None and ask_total > 0:
            t2_ask_pct = data.ob_t2_ask_vol / ask_total
            if t2_ask_pct >= self.T2_THRESHOLD:
                mod_short += 1.0
                tier_details.append(f'T2 Ask {t2_ask_pct:.0%} near-term')
        if data.ob_t2_bid_vol is not None and bid_total > 0:
            t2_bid_pct = data.ob_t2_bid_vol / bid_total
            if t2_bid_pct >= self.T2_THRESHOLD:
                mod_long += 1.0
                tier_details.append(f'T2 Bid {t2_bid_pct:.0%} near-term')
        wall_details: list[str] = []
        if data.ob_ask_wall is not None and ask_total > 0:
            ask_wall_pct = data.ob_ask_wall / ask_total
            if ask_wall_pct >= self.WALL_THRESHOLD:
                mod_short += 1.0
                wall_details.append(f'Ask wall {ask_wall_pct:.0%} of asks')
        if data.ob_bid_wall is not None and bid_total > 0:
            bid_wall_pct = data.ob_bid_wall / bid_total
            if bid_wall_pct >= self.WALL_THRESHOLD:
                mod_long += 1.0
                wall_details.append(f'Bid wall {bid_wall_pct:.0%} of bids')
        long_score = max(0.0, min(10.0, long_score + mod_long))
        short_score = max(0.0, min(10.0, short_score + mod_short))
        blocks_long = imbalance < 0.5 and data.ob_t1_ask_vol is not None and (ask_total > 0) and (data.ob_t1_ask_vol / ask_total >= self.T1_THRESHOLD)
        blocks_short = imbalance > 2.0 and data.ob_t1_bid_vol is not None and (bid_total > 0) and (data.ob_t1_bid_vol / bid_total >= self.T1_THRESHOLD)
        if imbalance <= 0.33 or imbalance >= 3.0:
            alert_level = 'critical'
        elif imbalance <= 0.5 or imbalance >= 2.0:
            alert_level = 'warning'
        else:
            alert_level = 'info'
        confidence = 0.75
        if imbalance >= 2.0 or imbalance <= 0.5:
            confidence += 0.05
        if data.ob_spread_pct is not None:
            if data.ob_spread_pct < 0.05:
                confidence += 0.05
            elif data.ob_spread_pct > 1.0:
                confidence -= 0.2
            elif data.ob_spread_pct > 0.5:
                confidence -= 0.1
        confidence = max(0.5, min(0.9, confidence))
        parts = [interpretation]
        parts.extend(tier_details)
        parts.extend(wall_details)
        if data.ob_spread_pct is not None:
            if data.ob_spread_pct > 0.5:
                parts.append(f'Wide spread {data.ob_spread_pct:.2f}%')
            else:
                parts.append(f'Spread {data.ob_spread_pct:.2f}%')
        reasoning = ' | '.join(parts)
        return AnalyzerResult(analyzer_name=self.analyzer_name, long_score=long_score, short_score=short_score, confidence=confidence, reasoning=reasoning, blocks_long=blocks_long, blocks_short=blocks_short, alert_level=alert_level, key_value=imbalance, key_label='Bid/Ask Ratio')
import logging
from dataclasses import dataclass
from typing import Optional
from ..models.market_data import MarketData

logger = logging.getLogger(__name__)


@dataclass
class RegimeResult:
    regime: str
    long_mult: float
    short_mult: float
    skip: bool
    reasoning: str


class MarketRegimeDetector:
    """Classifies the current market microstructure regime for a token.

    Returns multipliers applied to long/short scores in SignalGenerator.
    Only ILLIQUID causes a skip (spread > 5% = physically can't enter).
    """

    ILLIQUID_SPREAD = 5.0      # % — skip signal entirely
    BREAKOUT_VOL_RATIO = 2.0   # volume_1h / avg_volume_1h
    BREAKOUT_PRICE_MOVE = 1.5  # |price_1h| % to confirm breakout is real
    DEAD_RANGE_PRICE_4H = 0.5  # |price_4h| < 0.5% = confirmed sideways
    DEAD_RANGE_VOL_RATIO = 0.5 # volume below half of average

    # BREAKOUT directional multipliers by OB pressure
    OB_BULL_THRESHOLD = 1.3    # bid_total / ask_total > this = buying pressure
    OB_BEAR_THRESHOLD = 0.77   # bid_total / ask_total < this = selling pressure

    def detect(self, data: MarketData) -> RegimeResult:
        spread = data.ob_spread_pct
        vol_ratio = self._vol_ratio(data)
        atr_pct = self._atr_pct(data)
        price_1h = data.price_change_1h
        price_4h = data.price_change_4h

        # 1. ILLIQUID — only hard skip
        if spread is not None and spread > self.ILLIQUID_SPREAD:
            return RegimeResult(
                regime='ILLIQUID',
                long_mult=1.0,
                short_mult=1.0,
                skip=True,
                reasoning=f'spread {spread:.2f}% > 5% — untradeable',
            )

        # 2. BREAKOUT_FORMING — volume spike + real price move
        breakout = (
            vol_ratio is not None and vol_ratio > self.BREAKOUT_VOL_RATIO
            and price_1h is not None and abs(price_1h) > self.BREAKOUT_PRICE_MOVE
        )
        if breakout:
            long_mult, short_mult = self._breakout_mults(data)
            direction = 'bullish' if price_1h > 0 else 'bearish'
            return RegimeResult(
                regime='BREAKOUT_FORMING',
                long_mult=long_mult,
                short_mult=short_mult,
                skip=False,
                reasoning=f'{direction} breakout: vol {vol_ratio:.1f}x avg, price_1h {price_1h:+.1f}%',
            )

        # 3. DEAD_RANGE — confirmed sideways with low volume
        dead = (
            price_4h is not None and abs(price_4h) < self.DEAD_RANGE_PRICE_4H
            and vol_ratio is not None and vol_ratio < self.DEAD_RANGE_VOL_RATIO
        )
        if dead:
            return RegimeResult(
                regime='DEAD_RANGE',
                long_mult=0.85,
                short_mult=0.85,
                skip=False,
                reasoning=f'sideways: price_4h {price_4h:+.2f}%, vol {vol_ratio:.2f}x avg',
            )

        # 4. LIQUID_TRENDING — normal, no adjustment
        parts = []
        if spread is not None:
            parts.append(f'spread {spread:.2f}%')
        if vol_ratio is not None:
            parts.append(f'vol {vol_ratio:.1f}x')
        if atr_pct is not None:
            parts.append(f'atr {atr_pct:.1f}%')
        return RegimeResult(
            regime='LIQUID_TRENDING',
            long_mult=1.0,
            short_mult=1.0,
            skip=False,
            reasoning=', '.join(parts) if parts else 'normal market',
        )

    def _vol_ratio(self, data: MarketData) -> Optional[float]:
        if data.volume_1h and data.avg_volume_1h and data.avg_volume_1h > 0:
            return data.volume_1h / data.avg_volume_1h
        return None

    def _atr_pct(self, data: MarketData) -> Optional[float]:
        if data.atr and data.atr > 0 and data.price > 0:
            return data.atr / data.price * 100
        return None

    def _breakout_mults(self, data: MarketData) -> tuple[float, float]:
        ob_ratio = None
        if data.ob_bid_total and data.ob_ask_total and data.ob_ask_total > 0:
            ob_ratio = data.ob_bid_total / data.ob_ask_total

        if ob_ratio is None:
            return (1.10, 1.10)
        if ob_ratio > self.OB_BULL_THRESHOLD:
            return (1.15, 0.90)   # buying pressure → boost long
        if ob_ratio < self.OB_BEAR_THRESHOLD:
            return (0.90, 1.15)   # selling pressure → boost short
        return (1.10, 1.10)       # neutral breakout

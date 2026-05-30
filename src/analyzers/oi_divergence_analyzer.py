import logging
from typing import Optional
from .base import BaseAnalyzer
from ..models.market_data import MarketData
from ..models.analyzer_result import AnalyzerResult

logger = logging.getLogger(__name__)


class OIDivergenceAnalyzer(BaseAnalyzer):
    """Detects divergence between OI, volume, and price — signature of smart money activity.

    Three patterns (checked in priority order):
      1. DISTRIBUTION   — price pumping, OI not growing -> smart money exiting into the rally
      2. WASH_TRADING   — massive volume spike, OI barely moves -> fake/artificial activity
      3. SILENT_ACCUM   — OI building quietly with below-avg volume -> two variants:
           - neutral/positive funding -> institutional long accumulation (bullish, long_score=6.5)
           - strongly negative funding -> possible short accumulation (bearish, short_score=5.0)

    Requires oi_change_1h to be populated (monitor mode with OITracker enrichment).
    Returns None in batch scan without OI history.
    """

    # Pattern 1 — Distribution thresholds
    DIST_PRICE_MIN = 2.5    # price_change_1h >= this % triggers basic check
    DIST_OI_MAX = 0.0       # oi_change_1h must be <= this (not growing at all)
    DIST_PRICE_STRONG = 4.0 # stronger price move -> looser OI threshold
    DIST_OI_STRONG = 0.5    # oi_change_1h < this even on strong 4%+ price move

    # Pattern 2 — Wash trading thresholds
    WASH_VOL_RATIO = 3.0    # volume_1h / avg_volume_1h must exceed this
    WASH_OI_MAX = 0.5       # |oi_change_1h| must be below this % (OI barely changed)

    # Pattern 3 — Silent accumulation thresholds
    ACCUM_OI_MIN = 5.0      # oi_change_1h must exceed this % (meaningful OI growth)
    ACCUM_VOL_MAX = 0.8     # volume_ratio must be below this (below-average volume)
    ACCUM_PRICE_FLAT = 1.0  # |price_change_1h| must be below this (price not moving)

    def __init__(self, weight: float = 1.0):
        super().__init__(weight=weight)

    @property
    def analyzer_name(self) -> str:
        return 'OI Divergence'

    def analyze(self, data: MarketData) -> Optional[AnalyzerResult]:
        if not self._validate_data(data):
            return None
        if data.oi_change_1h is None:
            return None

        oi_1h = data.oi_change_1h
        price_1h = data.price_change_1h
        vol_ratio = self._vol_ratio(data)

        # ── Pattern 1: DISTRIBUTION ──────────────────────────────────────────────
        # Price rallying but OI not growing = smart money exiting into retail buying.
        # Most dangerous whale trap: entering long here means buying from the whale.
        #
        # Exception: negative funding rate means the market was heavy with shorts.
        # Price up + OI down in that context = shorts being squeezed out = BULLISH.
        # Do not flag this as distribution — it's a short squeeze.
        is_short_squeeze_context = data.funding_rate < -0.0005
        if price_1h is not None and not is_short_squeeze_context:
            basic_dist = price_1h >= self.DIST_PRICE_MIN and oi_1h <= self.DIST_OI_MAX
            strong_dist = price_1h >= self.DIST_PRICE_STRONG and oi_1h < self.DIST_OI_STRONG
            if basic_dist or strong_dist:
                logger.debug('[OI Divergence] %s: price %+.1f%% OI %+.2f%% -> DISTRIBUTION -> blocks_long',
                             data.symbol, price_1h, oi_1h)
                return AnalyzerResult(
                    analyzer_name=self.analyzer_name,
                    long_score=2.0,
                    short_score=7.5,
                    confidence=0.85,
                    reasoning=f'Price {price_1h:+.1f}% but OI {oi_1h:+.2f}% -> distribution, smart money exiting',
                    blocks_long=True,
                    blocks_short=False,
                    alert_level='warning',
                    key_value=round(price_1h - oi_1h, 2),
                    key_label='Price/OI divergence %',
                )

        # ── Pattern 2: WASH TRADING ──────────────────────────────────────────────
        # Massive volume but OI barely changes = positions not being opened.
        # Real trading creates positions. Volume without OI = artificial activity.
        # Neutralises VolumeSpikeAnalyzer which currently scores this positively.
        if vol_ratio is not None and vol_ratio >= self.WASH_VOL_RATIO:
            if abs(oi_1h) <= self.WASH_OI_MAX:
                logger.debug('[OI Divergence] %s: vol %.1fx OI %+.2f%% -> WASH_TRADING -> neutralised',
                             data.symbol, vol_ratio, oi_1h)
                return AnalyzerResult(
                    analyzer_name=self.analyzer_name,
                    long_score=1.0,
                    short_score=1.0,
                    confidence=0.80,
                    reasoning=f'Volume {vol_ratio:.1f}x spike but OI only {oi_1h:+.2f}% -> wash trading suspected',
                    blocks_long=False,
                    blocks_short=False,
                    alert_level='warning',
                    key_value=round(vol_ratio, 2),
                    key_label='Vol/OI ratio',
                )

        # ── Pattern 3: SILENT ACCUMULATION ───────────────────────────────────────
        # OI building significantly while volume is below average and price quiet.
        # BUT: OI growth alone doesn't reveal direction — longs OR shorts could be building.
        # Funding rate resolves the ambiguity:
        #   neutral/positive funding → longs dominant → institutional long accumulation (bullish)
        #   strongly negative funding → shorts dominant → smart money may be building shorts (bearish)
        if oi_1h >= self.ACCUM_OI_MIN:
            price_flat = price_1h is None or abs(price_1h) <= self.ACCUM_PRICE_FLAT
            vol_quiet = vol_ratio is not None and vol_ratio <= self.ACCUM_VOL_MAX
            if price_flat and vol_quiet:
                is_short_accum = data.funding_rate < -0.0003
                if is_short_accum:
                    logger.debug('[OI Divergence] %s: OI %+.2f%% vol %.1fx negative funding -> SHORT_ACCUM',
                                 data.symbol, oi_1h, vol_ratio)
                    return AnalyzerResult(
                        analyzer_name=self.analyzer_name,
                        long_score=3.5,
                        short_score=5.0,
                        confidence=0.65,
                        reasoning=f'OI {oi_1h:+.2f}% quietly (vol {vol_ratio:.1f}x) but negative funding -> possible short accumulation',
                        blocks_long=False,
                        blocks_short=False,
                        alert_level='warning',
                        key_value=round(oi_1h, 2),
                        key_label='Silent OI growth %',
                    )
                logger.debug('[OI Divergence] %s: OI %+.2f%% vol %.1fx -> SILENT_ACCUM -> long=6.5',
                             data.symbol, oi_1h, vol_ratio)
                return AnalyzerResult(
                    analyzer_name=self.analyzer_name,
                    long_score=6.5,
                    short_score=1.5,
                    confidence=0.75,
                    reasoning=f'OI {oi_1h:+.2f}% quietly (vol {vol_ratio:.1f}x avg) -> institutional accumulation',
                    blocks_long=False,
                    blocks_short=False,
                    alert_level='info',
                    key_value=round(oi_1h, 2),
                    key_label='Silent OI growth %',
                )

        return None

    def _vol_ratio(self, data: MarketData) -> Optional[float]:
        if data.volume_1h is not None and data.avg_volume_1h is not None and data.avg_volume_1h > 0:
            return data.volume_1h / data.avg_volume_1h
        return None

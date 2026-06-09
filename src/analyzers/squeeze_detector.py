import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from ..models.market_data import MarketData
from ..models.squeeze_alert import SqueezeAlert

logger = logging.getLogger(__name__)


@dataclass
class SqueezeScores:
    """Full computation result from SqueezeDetector.detect()."""
    long_score: float
    short_score: float
    c1_l: Optional[float]
    c2_l: Optional[float]
    c3_l: Optional[float]
    c4_l: Optional[float]
    fa_l: float
    c1_s: Optional[float]
    c2_s: Optional[float]
    c3_s: Optional[float]
    c4_s: Optional[float]
    fa_s: float


class SqueezeDetector:
    ALERT_THRESHOLD_STRONG = 8.0
    ALERT_THRESHOLD_WATCH = 5.5
    ALERT_THRESHOLD_TRIGGERED = 6.0   # min score to fire TRIGGERED (between WATCH and STRONG)
    MIN_OI_USD = 200_000
    MIN_VOLUME_24H = 200_000
    MAX_SPREAD_PCT = 2.5
    COOLDOWN_MINUTES = 30
    COOLDOWN_TRIGGERED_MINUTES = 10   # shorter cooldown — TRIGGERED is time-critical
    WATCH_MIN_DURATION_MINUTES = 15  # symbol must have been in WATCH this long before STRONG → Telegram
    WATCH_EXPIRY_MINUTES = 60        # WATCH entry expires after this long (stale conditions)
    MIN_C3_TRADES = 20  # minimum independent trades for a reliable 5m aggression reading
    VCI_COMPRESSED_THRESHOLD = 0.65  # VCI below this = spring coiled
    VCI_EXPANDING_THRESHOLD = 0.80   # VCI above this (after compression) = spring releasing
    VCI_MAX_AGE_SECONDS = 1200       # 20 min — discard prev VCI if token was absent that long

    def __init__(self):
        # stores (timestamp, cooldown_minutes) — TRIGGERED uses shorter cooldown than STRONG
        self._cooldown: dict[str, tuple[datetime, int]] = {}
        self._watch_log: dict[str, datetime] = {}
        self._ob_ratio_history: dict[str, deque] = {}
        # Stores (vci_value, stored_at) — timestamp guards against stale reads after token gaps
        self._vci_prev: dict[str, tuple[float, datetime]] = {}

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def detect(self, data: MarketData, update_history: bool = True) -> SqueezeScores:
        """
        Returns SqueezeScores with all component values and final scores.
        Maintains internal state for P6 OB Trend history.
        Pass update_history=False for re-check calls (e.g. monitor alert path)
        to avoid contaminating the P6 streak with duplicate observations.
        """
        if not self._passes_hard_filters(data):
            return SqueezeScores(
                long_score=0.0, short_score=0.0,
                c1_l=None, c2_l=None, c3_l=None, c4_l=None, fa_l=0.0,
                c1_s=None, c2_s=None, c3_s=None, c4_s=None, fa_s=0.0,
            )

        # Long squeeze
        c1_l = self._c1_trapped_shorts(data)
        c2_l = self._c2_ask_vacuum(data)
        c3_l = self._c3_buy_aggression(data)
        c4_l = self._c4_compression(data)
        fa_l = self._funding_adj_long(data)
        long_score = self._composite(c1_l, c2_l, c3_l, c4_l, fa_l)
        long_score += self._p1_vci_boost(data)
        long_score += self._p2_fr_resilience_boost(data)
        long_score += self._p3_cfc_boost(data)
        long_score += self._p5_vwap_boost_long(data)
        long_score += self._p6_ob_trend_boost(data, 'long', update_history=update_history)
        long_score = min(10.0, max(0.0, long_score))

        # Short squeeze
        c1_s = self._c1_trapped_longs(data)
        c2_s = self._c2_bid_vacuum(data)
        c3_s = self._c3_sell_aggression(data)
        c4_s = self._c4_over_extension(data)
        fa_s = self._funding_adj_short(data)
        short_score = self._composite(c1_s, c2_s, c3_s, c4_s, fa_s)
        short_score += self._p1_vci_boost(data)
        short_score += self._p4_absorption_boost(data)
        short_score += self._p6_ob_trend_boost(data, 'short', update_history=update_history)
        short_score = min(10.0, max(0.0, short_score))

        logger.debug(
            '[Squeeze] %s: LONG=%.1f (C1=%s C2=%s C3=%s C4=%s FR=%+.1f) | '
            'SHORT=%.1f (C1=%s C2=%s C3=%s C4=%s FR=%+.1f)',
            data.symbol,
            long_score, c1_l, c2_l, c3_l, c4_l, fa_l,
            short_score, c1_s, c2_s, c3_s, c4_s, fa_s,
        )

        # Track VCI history for TRIGGERED detection (main scan only, not re-check calls).
        # Timestamp lets should_alert() discard stale values from token-gap periods.
        if update_history and data.vci is not None:
            self._vci_prev[data.symbol] = (data.vci, datetime.now(timezone.utc))

        return SqueezeScores(
            long_score=round(long_score, 2),
            short_score=round(short_score, 2),
            c1_l=c1_l, c2_l=c2_l, c3_l=c3_l, c4_l=c4_l, fa_l=fa_l,
            c1_s=c1_s, c2_s=c2_s, c3_s=c3_s, c4_s=c4_s, fa_s=fa_s,
        )

    # ------------------------------------------------------------------
    # Alert logic
    # ------------------------------------------------------------------

    def should_alert(
        self,
        symbol: str,
        scores: SqueezeScores,
        data: Optional[MarketData] = None,
    ) -> Optional[tuple]:
        """
        Returns (direction, level) or None.
        direction: 'LONG_SQUEEZE' or 'SHORT_SQUEEZE'
        level: 'WATCH' (log only) | 'STRONG' (send Telegram) | 'TRIGGERED' (send immediately)

        Two-phase confirmation: STRONG requires prior WATCH within WATCH_EXPIRY_MINUTES.
        TRIGGERED bypasses the wait when VCI expansion is detected in real time:
          - VCI was compressed last cycle (< VCI_COMPRESSED_THRESHOLD)
          - VCI is now expanding (> VCI_EXPANDING_THRESHOLD)
          - aggression spike confirms direction (>= 70%)
        Pass data=market_data from the monitor to enable TRIGGERED detection.
        """
        best = max(scores.long_score, scores.short_score)
        self._reset_cooldown_if_invalidated(symbol, best)

        if self._is_on_cooldown(symbol):
            return None

        # Require at least one core component (C1 or C2) with a positive score.
        long_has_core = (scores.c1_l is not None and scores.c1_l > 0) or \
                        (scores.c2_l is not None and scores.c2_l > 0)
        short_has_core = (scores.c1_s is not None and scores.c1_s > 0) or \
                         (scores.c2_s is not None and scores.c2_s > 0)

        long_ok = scores.long_score >= self.ALERT_THRESHOLD_WATCH and long_has_core
        short_ok = scores.short_score >= self.ALERT_THRESHOLD_WATCH and short_has_core

        if not long_ok and not short_ok:
            return None

        if long_ok and (not short_ok or scores.long_score >= scores.short_score):
            direction = 'LONG_SQUEEZE'
            score = scores.long_score
        else:
            direction = 'SHORT_SQUEEZE'
            score = scores.short_score

        now = datetime.now(timezone.utc)

        # TRIGGERED: VCI spring releasing right now — skip 15-min WATCH requirement.
        # Requires: prev VCI compressed → current VCI expanding + directional aggression spike.
        if data is not None and score >= self.ALERT_THRESHOLD_TRIGGERED:
            prev_entry = self._vci_prev.get(symbol)
            curr_vci = data.vci
            agg = data.aggression_5m
            tc = data.trade_count_5m

            prev_vci = None
            if prev_entry is not None:
                stored_vci, stored_at = prev_entry
                age_sec = (now - stored_at).total_seconds()
                if age_sec <= self.VCI_MAX_AGE_SECONDS:
                    prev_vci = stored_vci  # fresh enough to trust

            vci_transition = (
                prev_vci is not None
                and prev_vci < self.VCI_COMPRESSED_THRESHOLD
                and curr_vci is not None
                and curr_vci > self.VCI_EXPANDING_THRESHOLD
            )
            # Aggression must be directionally confirmed with enough trades to be reliable
            agg_reliable = tc is not None and tc >= self.MIN_C3_TRADES
            if direction == 'LONG_SQUEEZE':
                agg_confirms = agg_reliable and agg is not None and agg >= 70.0
            else:
                agg_confirms = agg_reliable and agg is not None and (100.0 - agg) >= 70.0
            if vci_transition and agg_confirms:
                self._set_cooldown(symbol, minutes=self.COOLDOWN_TRIGGERED_MINUTES)
                self._clear_watch(symbol)
                logger.info(
                    '[Squeeze TRIGGERED] %s → %s | VCI %.3f→%.3f agg=%.1f score=%.1f',
                    symbol, direction, prev_vci, curr_vci, agg, score,
                )
                return (direction, 'TRIGGERED')

        if score >= self.ALERT_THRESHOLD_STRONG and self._is_in_watch(symbol, now):
            self._set_cooldown(symbol)
            self._clear_watch(symbol)
            return (direction, 'STRONG')

        # WATCH level (or STRONG without prior WATCH — defer to next cycle)
        self._record_watch(symbol, now)
        return (direction, 'WATCH')

    def build_alert(
        self,
        data: MarketData,
        direction: str,
        scores: SqueezeScores,
        level: Optional[str] = None,
    ) -> SqueezeAlert:
        """Construct a SqueezeAlert from computed scores and market data.

        Pass level='TRIGGERED'/'STRONG'/'WATCH' explicitly when known (from should_alert).
        Falls back to score-based inference when level is None.
        """
        if direction == 'LONG_SQUEEZE':
            score = scores.long_score
            c1, c2, c3, c4, fa = scores.c1_l, scores.c2_l, scores.c3_l, scores.c4_l, scores.fa_l
            ob_ratio = (
                data.ob_bid_total / data.ob_ask_total
                if data.ob_bid_total and data.ob_ask_total and data.ob_ask_total > 0
                else None
            )
            if level == 'TRIGGERED':
                reasoning = 'VCI expanding now — short liquidations triggering'
            else:
                reasoning = 'Watch for price break up → short liquidations trigger'
        else:
            score = scores.short_score
            c1, c2, c3, c4, fa = scores.c1_s, scores.c2_s, scores.c3_s, scores.c4_s, scores.fa_s
            ob_ratio = (
                data.ob_ask_total / data.ob_bid_total
                if data.ob_ask_total and data.ob_bid_total and data.ob_bid_total > 0
                else None
            )
            if level == 'TRIGGERED':
                reasoning = 'VCI expanding now — long liquidations triggering'
            else:
                reasoning = 'Watch for price break down → long liquidations trigger'

        if level is None:
            level = 'STRONG' if score >= self.ALERT_THRESHOLD_STRONG else 'WATCH'

        accel = None
        if data.aggression_5m is not None and data.aggression_2h is not None:
            if direction == 'LONG_SQUEEZE':
                accel = data.aggression_5m - data.aggression_2h
            else:
                accel = (100.0 - data.aggression_5m) - (100.0 - data.aggression_2h)

        return SqueezeAlert(
            symbol=data.symbol,
            timestamp=datetime.now(timezone.utc),
            direction=direction,
            alert_level=level,
            squeeze_score=round(score, 2),
            c1_score=round(c1, 1) if c1 is not None else None,
            c2_score=round(c2, 1) if c2 is not None else None,
            c3_score=round(c3, 1) if c3 is not None else None,
            c4_score=round(c4, 1) if c4 is not None else None,
            funding_adj=round(fa, 2),
            price=data.price,
            oi_usd=data.open_interest_usd,
            oi_change_1h=data.oi_change_1h,
            price_change_1h=data.price_change_1h,
            price_change_4h=data.price_change_4h,
            ob_ratio=round(ob_ratio, 2) if ob_ratio is not None else None,
            aggression_5m=data.aggression_5m,
            aggression_accel=round(accel, 1) if accel is not None else None,
            funding_rate=data.funding_rate,
            vci=round(data.vci, 3) if data.vci is not None else None,
            cfc=data.cfc,
            reasoning=reasoning,
        )

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _passes_hard_filters(self, data: MarketData) -> bool:
        if data.open_interest_usd < self.MIN_OI_USD:
            return False
        if data.volume_24h < self.MIN_VOLUME_24H:
            return False
        if data.ob_spread_pct is not None and data.ob_spread_pct > self.MAX_SPREAD_PCT:
            return False
        return True

    def _composite(
        self,
        c1: Optional[float],
        c2: Optional[float],
        c3: Optional[float],
        c4: Optional[float],
        funding_adj: float,
    ) -> float:
        weights = {1: 0.30, 2: 0.30, 3: 0.25, 4: 0.15}
        components = {1: c1, 2: c2, 3: c3, 4: c4}
        available = {k: v for k, v in components.items() if v is not None}
        if not available:
            return 0.0
        total_weight = sum(weights[k] for k in available)
        weighted_sum = sum(available[k] * weights[k] for k in available)
        score = weighted_sum / total_weight
        return max(0.0, min(10.0, score + funding_adj))

    # ------------------------------------------------------------------
    # Long squeeze components
    # ------------------------------------------------------------------

    def _c1_trapped_shorts(self, data: MarketData) -> Optional[float]:
        if data.oi_change_1h is None or data.price_change_1h is None:
            return None
        # Guard: absolute OI change must be significant — on small OI tokens a large %
        # change can represent just $2k, which is noise from a single small trader
        abs_change_usd = data.open_interest_usd * abs(data.oi_change_1h) / 100
        if abs_change_usd < 5_000:
            return None
        # Guard: after a strong recent pump OI grows from FOMO longs, not trapped shorts
        if data.price_change_4h is not None and data.price_change_4h > 20.0:
            return None
        oi = data.oi_change_1h
        pc = data.price_change_1h
        # Strong divergence: OI up, price down
        if oi >= 8.0 and pc <= -1.0:
            return 10.0
        if oi >= 5.0 and pc <= -0.5:
            return 8.5
        # Silent accumulation: OI up, price barely moves — most dangerous for shorts
        # Checked before moderate divergence because 8.0 > 7.0
        if oi >= 5.0 and abs(pc) < 0.5:
            return 8.0
        if oi >= 3.0 and abs(pc) < 0.5:
            return 6.5
        # Moderate divergence
        if oi >= 3.0 and pc <= 0.0:
            return 7.0
        # Weak signal
        if oi >= 1.0 and pc <= 0.0:
            return 4.5
        if oi > 0.0:
            return 2.0
        return 0.0

    def _c2_ask_vacuum(self, data: MarketData) -> Optional[float]:
        if not data.ob_bid_total or not data.ob_ask_total or data.ob_ask_total <= 0:
            return None
        ratio = data.ob_bid_total / data.ob_ask_total
        if ratio >= 4.0:
            score = 10.0
        elif ratio >= 3.0:
            score = 9.0
        elif ratio >= 2.5:
            score = 8.0
        elif ratio >= 2.0:
            score = 7.0
        elif ratio >= 1.7:
            score = 6.0
        elif ratio >= 1.5:
            score = 5.0
        elif ratio >= 1.2:
            score = 3.5
        elif ratio >= 1.0:
            score = 2.0
        else:
            return 0.0
        if data.ob_t1_bid_vol and data.ob_t1_ask_vol and data.ob_t1_ask_vol > 0:
            t1 = data.ob_t1_bid_vol / data.ob_t1_ask_vol
            if t1 >= 2.0:
                score = min(10.0, score + 1.0)
            elif t1 >= 1.5:
                score = min(10.0, score + 0.5)
        return score

    def _c3_buy_aggression(self, data: MarketData) -> Optional[float]:
        if data.aggression_5m is None:
            return None
        if data.trade_count_5m is None or data.trade_count_5m < self.MIN_C3_TRADES:
            return None
        buy = data.aggression_5m
        if buy >= 80:
            score = 9.0
        elif buy >= 72:
            score = 7.5
        elif buy >= 65:
            score = 6.0
        elif buy >= 60:
            score = 4.5
        elif buy >= 55:
            score = 3.0
        elif buy >= 53:
            score = 2.0
        else:
            return 0.0
        if data.aggression_2h is not None:
            delta = buy - data.aggression_2h
            if delta >= 15:
                score = min(10.0, score + 2.0)
            elif delta >= 10:
                score = min(10.0, score + 1.5)
            elif delta >= 7:
                score = min(10.0, score + 1.0)
        return score

    def _c4_compression(self, data: MarketData) -> Optional[float]:
        pc1 = data.price_change_1h
        pc4 = data.price_change_4h
        # Override: price already broke upward — spring released, no setup
        if pc1 is not None and pc1 > 4.0:
            return 0.0
        a = pc1 is not None and abs(pc1) < 1.0
        b = pc4 is not None and abs(pc4) < 3.5
        c = (
            data.volume_1h is not None
            and data.avg_volume_1h is not None
            and data.avg_volume_1h > 0
            and data.volume_1h / data.avg_volume_1h < 1.0
        )
        if a and b and c:
            return 8.0
        if a and b:
            return 6.0
        if a and c:
            return 5.0
        if b and c:
            return 4.5
        if a:
            return 3.0
        if b:
            return 2.0
        return None  # no evaluable conditions → redistribute weight

    def _funding_adj_long(self, data: MarketData) -> float:
        fr = data.funding_rate
        if fr <= -0.002:
            return 1.0
        if fr <= -0.001:
            return 0.7
        if fr <= -0.0005:
            return 0.4
        if fr >= 0.002:
            return -0.7
        if fr >= 0.001:
            return -0.4
        return 0.0

    # ------------------------------------------------------------------
    # Short squeeze components
    # ------------------------------------------------------------------

    def _c1_trapped_longs(self, data: MarketData) -> Optional[float]:
        ratio = data.oi_mc_ratio
        if ratio is not None:
            if ratio >= 0.60:
                score = 10.0
            elif ratio >= 0.50:
                score = 8.5
            elif ratio >= 0.40:
                score = 7.0
            elif ratio >= 0.35:
                score = 5.5
            elif ratio >= 0.30:
                score = 3.0
            else:
                score = 0.0
            # Boost: longs piling in at the top
            if (data.oi_change_1h is not None and data.oi_change_1h >= 5.0
                    and data.price_change_1h is not None and data.price_change_1h >= 2.0):
                score = min(10.0, score + 2.0)
            return score
        # Fallback: no market cap data
        oi = data.oi_change_1h
        pc = data.price_change_1h
        if oi is None or pc is None:
            return None
        abs_change_usd = data.open_interest_usd * abs(oi) / 100
        if abs_change_usd < 5_000:
            return None
        if oi >= 8.0 and pc >= 3.0:
            return 7.0
        if oi >= 5.0 and pc >= 2.0:
            return 5.5
        return 0.0

    def _c2_bid_vacuum(self, data: MarketData) -> Optional[float]:
        if not data.ob_ask_total or not data.ob_bid_total or data.ob_bid_total <= 0:
            return None
        ratio = data.ob_ask_total / data.ob_bid_total
        if ratio >= 4.0:
            score = 10.0
        elif ratio >= 3.0:
            score = 9.0
        elif ratio >= 2.5:
            score = 8.0
        elif ratio >= 2.0:
            score = 7.0
        elif ratio >= 1.7:
            score = 6.0
        elif ratio >= 1.5:
            score = 5.0
        elif ratio >= 1.2:
            score = 3.5
        elif ratio >= 1.0:
            score = 2.0
        else:
            return 0.0
        if data.ob_t1_ask_vol and data.ob_t1_bid_vol and data.ob_t1_bid_vol > 0:
            t1 = data.ob_t1_ask_vol / data.ob_t1_bid_vol
            if t1 >= 2.0:
                score = min(10.0, score + 1.0)
            elif t1 >= 1.5:
                score = min(10.0, score + 0.5)
        return score

    def _c3_sell_aggression(self, data: MarketData) -> Optional[float]:
        if data.aggression_5m is None:
            return None
        if data.trade_count_5m is None or data.trade_count_5m < self.MIN_C3_TRADES:
            return None
        sell = 100.0 - data.aggression_5m
        if sell >= 80:
            score = 9.0
        elif sell >= 72:
            score = 7.5
        elif sell >= 65:
            score = 6.0
        elif sell >= 60:
            score = 4.5
        elif sell >= 55:
            score = 3.0
        elif sell >= 53:
            score = 2.0
        else:
            return 0.0
        if data.aggression_2h is not None:
            sell_2h = 100.0 - data.aggression_2h
            delta = sell - sell_2h
            if delta >= 15:
                score = min(10.0, score + 2.0)
            elif delta >= 10:
                score = min(10.0, score + 1.5)
            elif delta >= 7:
                score = min(10.0, score + 1.0)
        return score

    def _c4_over_extension(self, data: MarketData) -> float:
        pc1 = data.price_change_1h or 0.0
        pc4 = data.price_change_4h or 0.0
        pc24 = data.price_change_24h or 0.0
        s1 = 8.0 if pc1 >= 5.0 else 6.0 if pc1 >= 3.0 else 4.0 if pc1 >= 2.0 else 2.0 if pc1 >= 1.0 else 0.0
        s4 = 9.0 if pc4 >= 10.0 else 7.0 if pc4 >= 6.0 else 5.0 if pc4 >= 3.0 else 0.0
        base = max(s1, s4)
        if base == 0.0:
            return 0.0  # no current over-extension — 24h history alone is not enough
        bonus = 2.5 if pc24 >= 30.0 else 1.5 if pc24 >= 20.0 else 0.5 if pc24 >= 10.0 else 0.0
        return min(10.0, base + bonus)

    def _funding_adj_short(self, data: MarketData) -> float:
        fr = data.funding_rate
        if fr >= 0.002:
            return 1.0
        if fr >= 0.001:
            return 0.7
        if fr >= 0.0005:
            return 0.4
        if fr <= -0.002:
            return -0.7
        if fr <= -0.001:
            return -0.4
        if fr <= -0.0005:
            return -0.2
        return 0.0

    # ------------------------------------------------------------------
    # Polling boosters
    # ------------------------------------------------------------------

    def _p1_vci_boost(self, data: MarketData) -> float:
        """Volatility Compression Index boost. Applies to both directions."""
        if data.vci is None:
            return 0.0
        # Post-pump distortion: after recent pump ATR_20 inflated → VCI falsely low
        # Use price_change_4h for more current context than 24h
        pc4 = data.price_change_4h
        if pc4 is not None and pc4 > 15.0:
            pump_factor = 0.3   # last 4h were a pump → VCI compression is normalization, not signal
        elif data.price_change_24h is not None and data.price_change_24h > 60.0:
            pump_factor = 0.5   # large 24h pump but 4h normal → moderate dampening
        else:
            pump_factor = 1.0
        vci = data.vci
        if vci < 0.45:
            boost = 2.0
        elif vci < 0.55:
            boost = 1.7
        elif vci < 0.65:
            boost = 1.4
        elif vci < 0.70:
            boost = 1.1
        elif vci < 0.75:
            boost = 0.8
        elif vci < 0.80:
            boost = 0.5
        elif vci < 0.85:
            boost = 0.3
        else:
            boost = 0.0
        return boost * pump_factor

    def _p2_fr_resilience_boost(self, data: MarketData) -> float:
        """Bears paying but price holds → hidden buyers. Long only."""
        fr = data.funding_rate
        pc1 = data.price_change_1h
        if pc1 is None:
            return 0.0
        pc4 = data.price_change_4h
        # Strongest tier: confirm with 4h price hold as well
        if fr <= -0.002 and pc4 is not None and pc1 > -0.5 and pc4 > -1.5:
            return 2.0
        if fr <= -0.001 and pc1 > -1.0:
            return 1.6
        if fr <= -0.0005 and pc1 > -0.5:
            return 1.2
        return 0.0

    def _p3_cfc_boost(self, data: MarketData) -> float:
        """Consecutive flat candles → spring loading. Long only."""
        cfc = data.cfc
        if cfc >= 7:
            return 1.5
        if cfc >= 5:
            return 1.2
        if cfc >= 4:
            return 1.0
        if cfc >= 3:
            return 0.7
        if cfc >= 2:
            return 0.4
        return 0.0

    def _p4_absorption_boost(self, data: MarketData) -> float:
        """Buyers can't move price → distribution at top. Short only."""
        agg = data.aggression_5m
        pc1 = data.price_change_1h
        pc4 = data.price_change_4h
        if agg is None or pc1 is None:
            return 0.0
        # If price already fell 4h — this is accumulation at bottom, not distribution
        if pc4 is not None and pc4 < -3.0:
            return 0.0
        if agg >= 70 and pc1 < 0.5:
            return 2.0
        if agg >= 65 and pc1 < 1.0:
            return 1.4
        if agg >= 60 and pc1 < 0.5:
            return 1.1
        return 0.0

    def _p5_vwap_boost_long(self, data: MarketData) -> float:
        """Price below fair value + OI building → accumulation. Long only."""
        if data.vwap is None or data.vwap <= 0:
            return 0.0
        pct = (data.price - data.vwap) / data.vwap * 100
        oi = data.oi_change_1h or 0.0
        if pct < -3.0 and oi > 2.0:
            return 1.0
        if pct < -2.0 and oi > 1.0:
            return 0.7
        if pct < -1.0 and oi > 0.5:
            return 0.5
        return 0.0

    def _p6_ob_trend_boost(self, data: MarketData, direction: str, update_history: bool = True) -> float:
        """Consecutive OB ratio increases → building pressure. Both directions."""
        if direction == 'long':
            if not data.ob_bid_total or not data.ob_ask_total or data.ob_ask_total <= 0:
                return 0.0
            ratio = data.ob_bid_total / data.ob_ask_total
        else:
            if not data.ob_ask_total or not data.ob_bid_total or data.ob_bid_total <= 0:
                return 0.0
            ratio = data.ob_ask_total / data.ob_bid_total

        key = f'{data.symbol}_{direction}'
        hist = self._ob_ratio_history.get(key, deque(maxlen=5))
        if update_history:
            hist.append(ratio)
            self._ob_ratio_history[key] = hist

        if len(hist) < 3:
            return 0.0

        items = list(hist)
        consecutive = 0
        for i in range(len(items) - 1, 0, -1):
            if items[i] > items[i - 1] * 1.05:
                consecutive += 1
            else:
                break

        if consecutive >= 4:
            return 1.5
        if consecutive >= 3:
            return 1.2
        if consecutive >= 2:
            return 0.9
        return 0.0

    # ------------------------------------------------------------------
    # Cooldown
    # ------------------------------------------------------------------

    def _is_on_cooldown(self, symbol: str) -> bool:
        entry = self._cooldown.get(symbol)
        if entry is None:
            return False
        ts, minutes = entry
        return (datetime.now(timezone.utc) - ts).total_seconds() < minutes * 60

    def _set_cooldown(self, symbol: str, minutes: Optional[int] = None) -> None:
        if minutes is None:
            minutes = self.COOLDOWN_MINUTES
        self._cooldown[symbol] = (datetime.now(timezone.utc), minutes)

    def _reset_cooldown_if_invalidated(self, symbol: str, score: float) -> None:
        # Do not reset cooldown based on score — time-based expiry only.
        # Score oscillates naturally; resetting on dips caused repeated alerts every few cycles.
        pass

    def _is_in_watch(self, symbol: str, now: datetime) -> bool:
        ts = self._watch_log.get(symbol)
        if ts is None:
            return False
        elapsed_min = (now - ts).total_seconds() / 60
        # Must have been watching long enough (signal persistence), but not too long (stale)
        return self.WATCH_MIN_DURATION_MINUTES <= elapsed_min <= self.WATCH_EXPIRY_MINUTES

    def _record_watch(self, symbol: str, now: datetime) -> None:
        # Preserve original entry time, but reset if the previous entry expired.
        # Without the reset, an expired entry blocks the WATCH→STRONG cycle indefinitely.
        existing = self._watch_log.get(symbol)
        if existing is None or (now - existing).total_seconds() / 60 > self.WATCH_EXPIRY_MINUTES:
            self._watch_log[symbol] = now

    def _clear_watch(self, symbol: str) -> None:
        self._watch_log.pop(symbol, None)

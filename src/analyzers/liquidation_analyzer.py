import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from .base import BaseAnalyzer
from ..models.market_data import MarketData
from ..models.analyzer_result import AnalyzerResult

logger = logging.getLogger(__name__)


@dataclass
class LiquidationEvent:
    """Tracks an active liquidation cascade across monitor cycles."""
    side: Optional[str]          # LONGS, SHORTS, or None
    severity: float              # 0.4–1.0 (updated to worst seen)
    low_price: float             # minimum price since cascade start
    last_during_at: datetime     # timestamp of last DURING detection
    wait_seconds: int            # adaptive wait from end of cascade
    stabilization_attempts: int  # failed stabilization check counter


class LiquidationAnalyzer(BaseAnalyzer):

    def __init__(self, weight: float = 1.0):
        super().__init__(weight=weight)
        self._events: dict[str, LiquidationEvent] = {}

    @property
    def analyzer_name(self) -> str:
        return 'Liquidation Analyzer'

    def _validate_data(self, data: MarketData) -> bool:
        if not super()._validate_data(data):
            return False
        if data.oi_change_1h is None and data.oi_change_5m is None:
            return False
        return True

    # ------------------------------------------------------------------
    # Unchanged detection helpers
    # ------------------------------------------------------------------

    def _price_threshold(self, data: MarketData, pct: float) -> float:
        if data.atr and data.atr > 0 and data.price > 0:
            atr_pct = data.atr / data.price * 100
            return max(pct, atr_pct * 0.3)
        return pct

    def _detect_liquidation(self, data: MarketData) -> dict:
        if data.liquidation_detected and data.liquidation_side:
            return {
                'detected': True,
                'side': data.liquidation_side,
                'context': data.liquidation_context or 'UNCERTAIN',
                'severity': min(1.0, (data.liquidation_volume or 0) / max(data.volume_24h, 1) * 24),
            }
        oi_change = data.oi_change_1h if data.oi_change_1h is not None else data.oi_change_5m
        if oi_change is None:
            return {'detected': False, 'side': None, 'context': 'UNCERTAIN', 'severity': 0}
        price_change = data.price_change_1h if data.price_change_1h is not None else 0
        volume_ratio = 1.0
        if data.volume_1h and data.avg_volume_1h and data.avg_volume_1h > 0:
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
        side_thresh = self._price_threshold(data, 3.0)
        if price_change < -side_thresh:
            side = 'LONGS'
        elif price_change > side_thresh:
            side = 'SHORTS'
        else:
            side = None
        during_thresh = self._price_threshold(data, 5.0)
        after_thresh = self._price_threshold(data, 3.0)
        if abs(price_change) > during_thresh and oi_change <= -10 and volume_ratio > 2.0:
            context = 'DURING'
        elif abs(price_change) < after_thresh and volume_ratio < 1.5:
            context = 'AFTER'
        else:
            context = 'UNCERTAIN'
        detected = oi_change <= -10 or volume_elevated or price_moved
        return {'detected': detected, 'side': side, 'context': context, 'severity': severity}

    def _detect_flat_oi_divergence(self, data: MarketData) -> Optional[dict]:
        if data.oi_change_1h is None or data.price_change_1h is None:
            return None
        oi_change = data.oi_change_1h
        price_change = data.price_change_1h
        if not (abs(oi_change) < 2.0 and price_change < -3.0):
            return None
        if price_change <= -10:
            severity = 1.0
        elif price_change <= -7:
            severity = 0.8
        elif price_change <= -5:
            severity = 0.6
        else:
            severity = 0.4
        return {'oi_change': oi_change, 'price_change': price_change, 'severity': severity}

    def _detect_price_up_oi_down(self, data: MarketData) -> Optional[dict]:
        if data.oi_change_1h is None or data.price_change_1h is None:
            return None
        oi_change = data.oi_change_1h
        price_change = data.price_change_1h
        # Threshold raised to -5% to avoid overlap with OIDivergenceAnalyzer which already
        # covers price↑+OI<0 (distribution pattern). This version specifically targets
        # significant long exodus that signals cascade risk, not mild distribution.
        if price_change <= 2.0 or oi_change >= -5.0:
            return None
        severity = min(1.0, (abs(oi_change) - 5.0) / 5.0)
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

    # ------------------------------------------------------------------
    # PATH C: Adaptive timing helpers
    # ------------------------------------------------------------------

    def _calc_wait_seconds(self, atr_pct: Optional[float], severity: float) -> int:
        """Compute adaptive wait time from cascade END based on volatility + severity."""
        if atr_pct is None or atr_pct < 2.0:
            base = 8 * 60
        elif atr_pct < 5.0:
            base = 15 * 60
        elif atr_pct < 15.0:
            base = 25 * 60
        else:
            base = 40 * 60
        # severity 0.4 → ×0.96, severity 1.0 → ×1.2
        return int(base * (0.8 + severity * 0.4))

    def _is_stabilized(self, data: MarketData, event: LiquidationEvent) -> bool:
        """Return True when market shows ≥2 of available stabilization signals."""
        checks_passed = 0
        checks_available = 0

        # OI stopped falling — prefer 5m (more current), fall back to 1h
        oi_check = data.oi_change_5m if data.oi_change_5m is not None else data.oi_change_1h
        if oi_check is not None:
            checks_available += 1
            threshold = -3.0 if data.oi_change_5m is not None else -5.0
            if oi_check > threshold:
                checks_passed += 1

        # Volume returning to normal
        if data.volume_1h and data.avg_volume_1h and data.avg_volume_1h > 0:
            checks_available += 1
            if (data.volume_1h / data.avg_volume_1h) < 1.5:
                checks_passed += 1

        # Price bounced at least 0.5% off the cascade low
        checks_available += 1
        if data.price > event.low_price * 1.005:
            checks_passed += 1

        return checks_passed >= 2

    # ------------------------------------------------------------------
    # Result builders
    # ------------------------------------------------------------------

    def _build_during_result(self, liq: dict, data: MarketData) -> AnalyzerResult:
        side, severity = liq['side'], liq['severity']
        if side == 'LONGS':
            long_score, short_score = 0.0, min(10.0, 8.0 + severity * 2.0)
            blocks_long, blocks_short = True, False
        elif side == 'SHORTS':
            long_score, short_score = min(10.0, 8.0 + severity * 2.0), 0.0
            blocks_long, blocks_short = False, True
        else:
            long_score = short_score = 3.0
            blocks_long = blocks_short = False
        oi_change = data.oi_change_1h if data.oi_change_1h is not None else data.oi_change_5m
        alert_level = 'critical' if severity >= 0.8 else 'warning'
        reasoning = f'Liquidation DURING: {side or "UNKNOWN"} | OI {oi_change:+.1f}% | Severity {severity:.1f}'
        return AnalyzerResult(
            analyzer_name=self.analyzer_name,
            long_score=long_score, short_score=short_score,
            confidence=self._calculate_confidence(data),
            reasoning=reasoning,
            blocks_long=blocks_long, blocks_short=blocks_short,
            alert_level=alert_level,
            key_value=oi_change, key_label='OI Change %',
        )

    def _build_after_result(self, liq: dict, data: MarketData) -> AnalyzerResult:
        side, severity = liq['side'], liq['severity']
        if side == 'LONGS':
            long_score, short_score = min(10.0, 7.0 + severity * 3.0), 1.0
        elif side == 'SHORTS':
            long_score, short_score = 1.0, min(10.0, 7.0 + severity * 3.0)
        else:
            long_score = short_score = 4.0
        oi_change = data.oi_change_1h if data.oi_change_1h is not None else data.oi_change_5m
        alert_level = 'critical' if severity >= 0.8 else 'warning'
        reasoning = f'Liquidation AFTER: {side or "UNKNOWN"} | OI {oi_change:+.1f}% | Severity {severity:.1f} | entry window open'
        return AnalyzerResult(
            analyzer_name=self.analyzer_name,
            long_score=long_score, short_score=short_score,
            confidence=self._calculate_confidence(data),
            reasoning=reasoning,
            blocks_long=False, blocks_short=False,
            alert_level=alert_level,
            key_value=oi_change, key_label='OI Change %',
        )

    def _build_hold_result(self, event: LiquidationEvent, elapsed: float, data: MarketData) -> AnalyzerResult:
        elapsed_min = int(elapsed // 60)
        wait_min = event.wait_seconds // 60
        attempts_str = f' | attempt {event.stabilization_attempts}/5' if event.stabilization_attempts > 0 else ''
        reasoning = f'Liquidation: awaiting stabilization {elapsed_min}m/{wait_min}m{attempts_str}'
        oi_change = data.oi_change_1h if data.oi_change_1h is not None else data.oi_change_5m
        return AnalyzerResult(
            analyzer_name=self.analyzer_name,
            long_score=1.0, short_score=1.0,
            confidence=self._calculate_confidence(data),
            reasoning=reasoning,
            blocks_long=False, blocks_short=False,
            alert_level='info',
            key_value=oi_change, key_label='OI Change %',
        )

    def _purge_stale_events(self, now: datetime) -> None:
        """Remove events where wait period + 24h has elapsed since last DURING — symbol likely delisted or unavailable."""
        stale = [
            sym for sym, ev in self._events.items()
            if (now - ev.last_during_at).total_seconds() > ev.wait_seconds + 86400
        ]
        for sym in stale:
            logger.warning(f'[Liquidation] purging stale event for {sym} (no DURING seen in >24h past wait window)')
            del self._events[sym]

    # ------------------------------------------------------------------
    # State machine helpers
    # ------------------------------------------------------------------

    def _handle_during(self, symbol: str, liq: dict, data: MarketData, now: datetime) -> None:
        """Create or update the active cascade event."""
        event = self._events.get(symbol)
        if event is None:
            atr_pct = (data.atr / data.price * 100) if data.atr and data.price > 0 else None
            wait_sec = self._calc_wait_seconds(atr_pct, liq['severity'])
            self._events[symbol] = LiquidationEvent(
                side=liq['side'],
                severity=liq['severity'],
                low_price=data.price,
                last_during_at=now,
                wait_seconds=wait_sec,
                stabilization_attempts=0,
            )
            logger.debug(
                f'[Liquidation] {symbol} cascade start ({liq["side"]}, sev={liq["severity"]:.1f})'
                f' → wait={wait_sec // 60}min after cascade ends'
            )
        else:
            event.last_during_at = now
            event.low_price = min(event.low_price, data.price)
            event.stabilization_attempts = 0
            if liq['severity'] > event.severity:
                event.severity = liq['severity']
                atr_pct = (data.atr / data.price * 100) if data.atr and data.price > 0 else None
                event.wait_seconds = self._calc_wait_seconds(atr_pct, event.severity)
            if liq['side'] is not None:
                event.side = liq['side']

    def _handle_waiting(self, symbol: str, data: MarketData, now: datetime) -> AnalyzerResult:
        """Handle symbol with a tracked event where DURING is no longer firing."""
        event = self._events[symbol]
        elapsed = (now - event.last_during_at).total_seconds()

        if elapsed < event.wait_seconds:
            logger.debug(f'[Liquidation] {symbol} waiting {elapsed / 60:.1f}m/{event.wait_seconds // 60}m')
            return self._build_hold_result(event, elapsed, data)

        # Wait expired — check stabilization
        if self._is_stabilized(data, event):
            logger.debug(f'[Liquidation] {symbol} AFTER ready (stabilized, {elapsed / 60:.1f}m elapsed)')
            result_liq = {'side': event.side, 'severity': event.severity}
            del self._events[symbol]
            return self._build_after_result(result_liq, data)

        event.stabilization_attempts += 1

        if event.stabilization_attempts > 5:
            logger.debug(f'[Liquidation] {symbol} force AFTER after {event.stabilization_attempts} failed stabilization attempts')
            result_liq = {'side': event.side, 'severity': event.severity * 0.8}
            del self._events[symbol]
            return self._build_after_result(result_liq, data)

        logger.debug(f'[Liquidation] {symbol} stabilization attempt {event.stabilization_attempts}/5 failed')
        return self._build_hold_result(event, elapsed, data)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def analyze(self, data: MarketData) -> Optional[AnalyzerResult]:
        now = datetime.now(timezone.utc)
        self._purge_stale_events(now)
        if not self._validate_data(data):
            return None

        liq = self._detect_liquidation(data)
        symbol = data.symbol

        # ── Phase 1: active cascade (DURING) ──
        if liq['detected'] and liq['context'] == 'DURING':
            self._handle_during(symbol, liq, data, now)
            return self._build_during_result(liq, data)

        # ── Phase 2: tracked event (waiting / stabilizing) ──
        if symbol in self._events:
            return self._handle_waiting(symbol, data, now)

        # ── Phase 3: organic AFTER (no tracked event) ──
        if liq['detected'] and liq['context'] == 'AFTER':
            return self._build_after_result(liq, data)

        # ── Phase 4: detected but UNCERTAIN ──
        if liq['detected']:
            oi_change = data.oi_change_1h if data.oi_change_1h is not None else data.oi_change_5m
            return AnalyzerResult(
                analyzer_name=self.analyzer_name,
                long_score=3.0, short_score=3.0,
                confidence=self._calculate_confidence(data) * 0.7,
                reasoning=f'Liquidation UNCERTAIN | OI {oi_change:+.1f}%',
                blocks_long=False, blocks_short=False,
                alert_level='info',
                key_value=oi_change, key_label='OI Change %',
            )

        # ── Phase 5: no cascade — check divergence patterns ──
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

    # ------------------------------------------------------------------
    # Divergence result builders (unchanged)
    # ------------------------------------------------------------------

    def _build_possible_drawdown_result(self, divergence: dict, data: MarketData) -> AnalyzerResult:
        severity = divergence['severity']
        short_score = min(7.0, 5.0 + severity * 2.0)
        alert_level = 'warning' if severity >= 0.6 else 'info'
        confidence = self._calculate_confidence(data) * 0.8
        reasoning = (
            f"Possible Drawdown: OI flat ({divergence['oi_change']:+.1f}%) while price falling"
            f" ({divergence['price_change']:+.1f}%) | traders holding losing longs, cascade imminent"
        )
        return AnalyzerResult(
            analyzer_name=self.analyzer_name,
            long_score=0.0, short_score=short_score,
            confidence=confidence, reasoning=reasoning,
            blocks_long=True, blocks_short=False,
            alert_level=alert_level,
            key_value=divergence['price_change'], key_label='Price Drop (OI Flat)',
        )

    def _build_price_down_oi_up_result(self, divergence: dict, data: MarketData) -> AnalyzerResult:
        severity = divergence['severity']
        short_score = min(7.0, 5.0 + severity * 2.0)
        alert_level = 'warning' if severity >= 0.5 else 'info'
        confidence = self._calculate_confidence(data) * 0.85
        # If buyers are in control (aggression >= 60), price drop + OI up more likely
        # reflects longs accumulating the dip than new shorts — don't block long.
        agg = data.aggression_2h
        if agg is not None and agg >= 60.0:
            blocks_long = False
            reasoning = (
                f"Price↓+OI↑ ambiguous: price {divergence['price_change']:+.1f}%,"
                f" OI {divergence['oi_change']:+.1f}% | aggression {agg:.0f}% → likely long accumulation"
            )
        else:
            blocks_long = True
            reasoning = (
                f"Price↓+OI↑ bearish confirmation: price {divergence['price_change']:+.1f}%,"
                f" OI {divergence['oi_change']:+.1f}% | new shorts opening into falling price — downtrend confirmed"
            )
        return AnalyzerResult(
            analyzer_name=self.analyzer_name,
            long_score=0.0, short_score=short_score,
            confidence=confidence, reasoning=reasoning,
            blocks_long=blocks_long, blocks_short=False,
            alert_level=alert_level,
            key_value=divergence['oi_change'], key_label='OI Δ (Price Down)',
        )

    def _build_price_up_oi_down_result(self, divergence: dict, data: MarketData) -> AnalyzerResult:
        severity = divergence['severity']
        short_score = min(7.0, 5.0 + severity * 2.0)
        alert_level = 'warning' if severity >= 0.5 else 'info'
        confidence = self._calculate_confidence(data) * 0.8
        reasoning = (
            f"Price↑+OI↓ divergence: price {divergence['price_change']:+.1f}%,"
            f" OI {divergence['oi_change']:+.1f}% | longs exiting into strength — distribution, EXIT longs"
        )
        return AnalyzerResult(
            analyzer_name=self.analyzer_name,
            long_score=0.0, short_score=short_score,
            confidence=confidence, reasoning=reasoning,
            blocks_long=True, blocks_short=False,
            alert_level=alert_level,
            key_value=divergence['oi_change'], key_label='OI Δ (Price Up)',
        )

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

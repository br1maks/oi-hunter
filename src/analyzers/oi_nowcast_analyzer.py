import logging
from typing import Optional, List, Tuple
from datetime import datetime
from ..models.market_data import MarketData
from ..models.analyzer_result import AnalyzerResult
from .base import BaseAnalyzer

logger = logging.getLogger(__name__)

def normalize_symbol(symbol: str) -> str:
    if '_' in symbol:
        return symbol
    if symbol.endswith('USDT'):
        base = symbol[:-4]
        return f'{base}_USDT'
    return symbol

class OINowcastAnalyzer(BaseAnalyzer):
    MIN_POINTS_BASIC = 3
    MIN_POINTS_ACCEL = 4
    MIN_POINTS_RELIABLE = 10
    _phase_cache: dict = {}
    _current_cycle_id: int = 0

    def __init__(self, weight: float=1.5):
        super().__init__(weight)
        self._db = None
        self._oi_repo = None

    @property
    def analyzer_name(self) -> str:
        return 'OI Nowcast'

    @classmethod
    def begin_cycle(cls) -> None:
        cls._current_cycle_id += 1

    def set_database(self, db) -> None:
        from ..database import OIRepository
        self._db = db
        self._oi_repo = OIRepository(db)

    def _calculate_velocity(self, oi_history: List[Tuple[datetime, float]]) -> float:
        if len(oi_history) < 2:
            return 0.0
        first_time = oi_history[0][0]
        times = [(t - first_time).total_seconds() / 60 for t, _ in oi_history]
        oi_values = [oi for _, oi in oi_history]
        n = len(times)
        sum_x = sum(times)
        sum_y = sum(oi_values)
        sum_xy = sum((t * oi for t, oi in zip(times, oi_values)))
        sum_x2 = sum((t ** 2 for t in times))
        denominator = n * sum_x2 - sum_x ** 2
        if abs(denominator) < 1e-10:
            return 0.0
        slope = (n * sum_xy - sum_x * sum_y) / denominator
        return slope

    def _calculate_acceleration(self, oi_history: List[Tuple[datetime, float]]) -> float:
        if len(oi_history) < self.MIN_POINTS_ACCEL:
            return 0.0
        mid = len(oi_history) // 2
        older_half = oi_history[:mid]
        recent_half = oi_history[mid:]
        velocity_older = self._calculate_velocity(older_half)
        velocity_recent = self._calculate_velocity(recent_half)
        older_mid = older_half[len(older_half) // 2][0]
        recent_mid = recent_half[len(recent_half) // 2][0]
        dt = (recent_mid - older_mid).total_seconds() / 60
        if dt < 1e-10:
            return 0.0
        return (velocity_recent - velocity_older) / dt

    def _predict_oi(self, current_oi: float, velocity: float, acceleration: float, minutes_ahead: int) -> dict:
        t = minutes_ahead
        predicted_oi = current_oi + velocity * t + 0.5 * acceleration * t ** 2
        predicted_oi = max(0, predicted_oi)
        if current_oi > 0:
            change_pct = (predicted_oi - current_oi) / current_oi * 100
        else:
            change_pct = 0.0
        if abs(velocity) > 0:
            stability = 1.0 - min(1.0, 0.5 * abs(acceleration) * t / (abs(velocity) + 1e-10))
            confidence = 0.5 + stability * 0.5
        else:
            confidence = 0.5
        confidence *= 1.0 - minutes_ahead * 0.02
        return {'predicted_oi': predicted_oi, 'predicted_change_pct': change_pct, 'confidence': max(0.3, min(1.0, confidence))}

    def _score_prediction(self, predicted_change_pct: float) -> Tuple[float, float, str]:
        pct = predicted_change_pct
        if pct > 10:
            return (9.0, 1.0, 'OI SURGING - strong momentum!')
        elif pct > 5:
            return (8.0, 2.0, 'OI growing - momentum building')
        elif pct > 2:
            return (6.0, 3.0, 'OI stable growth')
        elif pct > -2:
            return (5.0, 5.0, 'OI stable - neutral')
        elif pct > -5:
            return (3.0, 6.0, 'OI weakening - take profits')
        elif pct > -10:
            return (1.0, 8.0, 'OI COLLAPSING - EXIT signal!')
        else:
            return (0.0, 10.0, 'OI CRASHING - EMERGENCY EXIT!')

    def _classify_phase(self, predicted_change_pct: float, acceleration: float, prev_phase: Optional[str]) -> str:
        pct = predicted_change_pct
        if pct > 5:
            if prev_phase in ('SURGING', 'OVERHEATED') and acceleration < 0:
                return 'OVERHEATED'
            return 'SURGING'
        elif pct > 2:
            return 'GROWING'
        elif pct > -2:
            return 'STABLE'
        elif pct > -5:
            return 'WEAKENING'
        else:
            return 'COLLAPSING'

    def _get_phase_transition_bonus(self, prev_phase: Optional[str], current_phase: str) -> Tuple[float, float, str]:
        if prev_phase is None or prev_phase == current_phase:
            return (0.0, 0.0, '')
        transition = (prev_phase, current_phase)
        if transition in [('STABLE', 'GROWING'), ('STABLE', 'SURGING')]:
            return (2.0, 0.0, 'POSSIBLE PUMP')
        if transition == ('GROWING', 'SURGING'):
            return (1.5, 0.0, 'CONFIRMED PUMP')
        if transition in [('COLLAPSING', 'WEAKENING'), ('COLLAPSING', 'STABLE'), ('COLLAPSING', 'GROWING'), ('WEAKENING', 'STABLE'), ('WEAKENING', 'GROWING')]:
            return (1.5, 0.0, 'REBOUND')
        if transition in [('SURGING', 'OVERHEATED'), ('GROWING', 'OVERHEATED')]:
            return (0.0, 2.0, 'OVERHEATED - EXIT WARNING')
        if transition in [('STABLE', 'WEAKENING'), ('STABLE', 'COLLAPSING')]:
            return (0.0, 2.0, 'POSSIBLE DRAWDOWN')
        if transition in [('GROWING', 'WEAKENING'), ('GROWING', 'COLLAPSING')]:
            return (0.0, 2.0, 'CONFIRMED DRAWDOWN')
        if transition in [('SURGING', 'WEAKENING'), ('SURGING', 'COLLAPSING'), ('OVERHEATED', 'WEAKENING'), ('OVERHEATED', 'COLLAPSING')]:
            return (0.0, 3.0, 'REVERSAL SIGNAL!')
        if transition == ('WEAKENING', 'COLLAPSING'):
            return (0.0, 1.5, 'STRONG SELLOFF')
        if transition == ('WEAKENING', 'SURGING'):
            return (2.0, 0.0, 'REBOUND')
        if transition == ('COLLAPSING', 'SURGING'):
            return (2.5, 0.0, 'STRONG REBOUND')
        if transition == ('SURGING', 'GROWING'):
            return (0.0, 1.0, 'DECELERATING')
        if transition in [('SURGING', 'STABLE'), ('OVERHEATED', 'STABLE')]:
            return (0.0, 2.0, 'MOMENTUM STALL')
        if transition == ('OVERHEATED', 'GROWING'):
            return (0.0, 1.5, 'COOLING')
        return (0.0, 0.0, '')

    def analyze(self, data: MarketData) -> Optional[AnalyzerResult]:
        if self._oi_repo is None:
            return None
        symbol = normalize_symbol(data.symbol)
        if data.open_interest_usd <= 0:
            return None
        try:
            oi_history = self._oi_repo.get_history(symbol, minutes=30)
        except Exception as e:
            logger.warning(f'OI Nowcast DB error for {symbol}: {e}')
            return None
        num_points = len(oi_history)
        if num_points < self.MIN_POINTS_BASIC:
            return AnalyzerResult(analyzer_name=self.analyzer_name, long_score=5.0, short_score=5.0, confidence=0.3, reasoning=f'Warming up: {num_points}/{self.MIN_POINTS_BASIC} data points', key_value=float(num_points), key_label='Data Points')
        current_oi = oi_history[-1][1]
        if current_oi <= 0:
            return None
        velocity = self._calculate_velocity(oi_history)
        acceleration = self._calculate_acceleration(oi_history)
        # Guard: suspicious OI collapse — large OI drop without price movement.
        # Causes: delta-neutral exit (whale closed both long+short) or API artifact.
        # The subsequent OI "rebound" is from an artificially low base, not real accumulation.
        suspicious_collapse = (
            data.oi_change_1h is not None and data.oi_change_1h < -25.0
            and data.price_change_1h is not None and abs(data.price_change_1h) < 3.0
        )
        predictions = {}
        for minutes in [5, 10, 15]:
            predictions[f'{minutes}min'] = self._predict_oi(current_oi, velocity, acceleration, minutes)
        pred_10min = predictions['10min']
        long_score, short_score, interpretation = self._score_prediction(pred_10min['predicted_change_pct'])
        cycle_id = OINowcastAnalyzer._current_cycle_id
        entry = OINowcastAnalyzer._phase_cache.get(symbol)
        if entry is None:
            prev_phase = None
        elif entry[2] == cycle_id:
            prev_phase = entry[0]
        else:
            prev_phase = entry[1]
        current_phase = self._classify_phase(pred_10min['predicted_change_pct'], acceleration, prev_phase)
        long_bonus, short_bonus, transition_label = self._get_phase_transition_bonus(prev_phase, current_phase)
        if suspicious_collapse and long_bonus > 0:
            long_bonus *= 0.5
        long_score = min(10.0, long_score + long_bonus)
        short_score = min(10.0, short_score + short_bonus)
        # Price-OI direction check: OI growing while price falling = shorts entering,
        # not longs accumulating. Two tiers based on OI surge strength.
        price_dir_note = ''
        if data.price_change_1h is not None and velocity > 0:
            price_drop = -data.price_change_1h
            predicted_change = pred_10min['predicted_change_pct']
            if price_drop >= 0.5 and predicted_change >= 5.0:
                # OI SURGING + price falling: the surge is shorts, not longs.
                # Flip the kinetic interpretation so OINowcast provides short kinetic confirmation.
                kinetic = long_score
                long_score = max(1.0, 10.0 - kinetic)
                short_score = min(10.0, kinetic * 0.75)
                price_dir_note = f' [BEARISH DIV: OI surging price{data.price_change_1h:+.1f}%→short kinetic {short_score:.1f}]'
            elif price_drop >= 0.5:
                # OI growing (not surging) + price falling: moderate penalty.
                penalty = min(3.0, price_drop * 1.5)
                long_score = max(1.0, long_score - penalty)
                short_score = min(10.0, short_score + penalty)
                price_dir_note = f' [price↓{data.price_change_1h:+.1f}%→shorts {short_score:.1f}]'
        OINowcastAnalyzer._phase_cache[symbol] = (prev_phase, current_phase, cycle_id)
        blocks_long = pred_10min['predicted_change_pct'] <= -5
        blocks_short = pred_10min['predicted_change_pct'] >= 10
        if short_bonus > 0 or price_dir_note:
            blocks_short = False
        if pred_10min['predicted_change_pct'] <= -10:
            alert_level = 'critical'
        elif pred_10min['predicted_change_pct'] <= -5:
            alert_level = 'warning'
        else:
            alert_level = 'info'
        base_confidence = pred_10min['confidence']
        if num_points < self.MIN_POINTS_ACCEL:
            base_confidence *= 0.8
        elif num_points >= self.MIN_POINTS_RELIABLE:
            base_confidence = min(1.0, base_confidence * 1.1)
        if suspicious_collapse:
            base_confidence *= 0.5
        base_confidence = max(0.3, base_confidence)
        velocity_dir = '+' if velocity > 0 else ''
        velocity_pct = velocity / current_oi * 100
        def _fmt_pct(pct: float) -> str:
            if abs(pct) < 0.05:
                return '~0%'
            return f'{pct:+.2f}%'
        if prev_phase is not None and prev_phase != current_phase:
            phase_prefix = f'[{prev_phase}->{current_phase}]'
            if transition_label:
                phase_prefix += f' {transition_label}'
            phase_prefix += ' |'
        else:
            phase_prefix = f'[{current_phase}]'
        collapse_note = (f' | SUSPICIOUS: OI {data.oi_change_1h:.0f}% collapse without price move (confidence*0.5)'
                         if suspicious_collapse else '')
        reasoning = f"{phase_prefix} {interpretation} | Velocity: {velocity_dir}{velocity:,.0f} USD/min ({velocity_pct:+.3f}%/min) | 5m: {_fmt_pct(predictions['5min']['predicted_change_pct'])}, 10m: {_fmt_pct(predictions['10min']['predicted_change_pct'])}, 15m: {_fmt_pct(predictions['15min']['predicted_change_pct'])}{price_dir_note}{collapse_note}"
        return AnalyzerResult(analyzer_name=self.analyzer_name, long_score=long_score, short_score=short_score, confidence=base_confidence, reasoning=reasoning, key_value=pred_10min['predicted_change_pct'], key_label='Predicted OI 10m %', blocks_long=blocks_long, blocks_short=blocks_short, alert_level=alert_level)
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from ..database.models import SignalHistory
from ..models.signal import Signal

logger = logging.getLogger(__name__)


class ForwardTester:
    """Records signal outcomes for forward-testing.

    Lifecycle per signal:
      1. record_signal()     — called once when signal fires
      2. update_outcomes()   — called each scan cycle; closes signals that hit a boundary
      3. get_stats()         — Telegram /stats command

    Outcome values stored in SignalHistory.result:
      WIN_T1 / WIN_T2 / WIN_T3  — price reached target 1/2/3
      STOPPED                   — price hit stop loss
      EXPIRED                   — signal still open after EXPIRE_HOURS
    """

    DEDUP_HOURS = 4
    EXPIRE_HOURS = 72

    def __init__(self, db) -> None:
        self._db = db
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Schema migration (idempotent)
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        """Add analyzer_breakdown column if the DB was created before this column existed."""
        try:
            with self._db.session() as s:
                s.execute(text('ALTER TABLE signal_history ADD COLUMN analyzer_breakdown TEXT'))
        except Exception:
            pass  # column already exists — expected on all but the first run

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_signal(self, signal: Signal, market_data=None) -> Optional[int]:
        """Persist a new signal. Returns DB row id, or None if duplicate / error."""
        if self._is_duplicate(signal):
            logger.debug(f'Skipping duplicate: {signal.direction} {signal.symbol}')
            return None
        try:
            oi_usd = getattr(market_data, 'open_interest_usd', None)
            aggression_2h = getattr(market_data, 'aggression_2h', None)
            with self._db.session() as s:
                row = SignalHistory(
                    symbol=signal.symbol,
                    timestamp=signal.timestamp.replace(tzinfo=None),
                    direction=signal.direction,
                    score=signal.overall_score,
                    confidence=signal.confidence,
                    entry_price=signal.entry_price,
                    stop_loss=signal.stop_loss,
                    target_1=signal.targets[0].target_price,
                    target_2=signal.targets[1].target_price,
                    target_3=signal.targets[2].target_price,
                    oi_usd=oi_usd,
                    oi_mc_ratio=signal.oi_mc_ratio,
                    funding_rate=signal.funding_rate,
                    aggression_2h=aggression_2h,
                    analyzer_breakdown=self._make_breakdown(signal),
                )
                s.add(row)
                s.flush()
                signal_id = row.id
            logger.info(
                f'Recorded signal #{signal_id}: {signal.direction} {signal.symbol}'
                f' score={signal.overall_score} entry={signal.entry_price}'
            )
            return signal_id
        except Exception as e:
            logger.error(f'Failed to record signal for {signal.symbol}: {e}')
            return None

    def _is_duplicate(self, signal: Signal) -> bool:
        """True if an open signal for same symbol+direction exists within DEDUP_HOURS."""
        cutoff = datetime.utcnow() - timedelta(hours=self.DEDUP_HOURS)
        try:
            with self._db.session() as s:
                existing = (
                    s.query(SignalHistory)
                    .filter(
                        SignalHistory.symbol == signal.symbol,
                        SignalHistory.direction == signal.direction,
                        SignalHistory.result.is_(None),
                        SignalHistory.timestamp >= cutoff,
                    )
                    .first()
                )
                return existing is not None
        except Exception as e:
            logger.warning(f'Dedup check failed: {e}')
            return False

    @staticmethod
    def _make_breakdown(signal: Signal) -> str:
        return json.dumps([
            {
                'name': r.analyzer_name,
                'l': round(r.long_score, 1),
                's': round(r.short_score, 1),
                'c': round(r.confidence, 2),
            }
            for r in signal.analyzer_results
        ])

    # ------------------------------------------------------------------
    # Outcome tracking
    # ------------------------------------------------------------------

    def update_outcomes(self, snapshots: List) -> int:
        """Check open signals against the current snapshot prices.

        Called once per scan cycle after scan_all() completes.
        Returns the number of signals closed in this call.
        """
        price_map: Dict[str, float] = {
            snap.symbol: snap.price for snap in snapshots if snap.price > 0
        }
        updated = 0
        try:
            with self._db.session() as s:
                open_signals = (
                    s.query(SignalHistory).filter(SignalHistory.result.is_(None)).all()
                )
                if not open_signals:
                    return 0
                now = datetime.utcnow()
                expire_cutoff = now - timedelta(hours=self.EXPIRE_HOURS)
                for sig in open_signals:
                    if sig.timestamp < expire_cutoff:
                        sig.result = 'EXPIRED'
                        sig.exit_timestamp = now
                        updated += 1
                        logger.info(
                            f'Expired: {sig.direction} {sig.symbol}'
                            f' (open > {self.EXPIRE_HOURS}h)'
                        )
                        continue
                    current_price = price_map.get(sig.symbol)
                    if not current_price:
                        continue
                    outcome = self._check_outcome(sig, current_price)
                    if outcome:
                        sig.exit_price = outcome['exit_price']
                        sig.exit_timestamp = now
                        sig.pnl_percent = round(outcome['pnl'], 2)
                        sig.result = outcome['result']
                        updated += 1
                        logger.info(
                            f'Outcome: {sig.direction} {sig.symbol}'
                            f' → {outcome["result"]} {outcome["pnl"]:+.1f}%'
                        )
        except Exception as e:
            logger.error(f'Failed to update outcomes: {e}')
            updated = 0  # session was rolled back — nothing was actually saved
        return updated

    @staticmethod
    def _check_outcome(sig: SignalHistory, price: float) -> Optional[Dict[str, Any]]:
        """Return outcome dict if price crossed a boundary, else None.

        Stop loss is checked first (conservative: avoids recording WIN if price
        is currently below stop, regardless of whether a target was hit earlier).
        Targets are checked best-to-worst so the highest hit level is captured.
        """
        entry = sig.entry_price
        if not entry or entry <= 0:
            return None
        stop, t1, t2, t3 = sig.stop_loss, sig.target_1, sig.target_2, sig.target_3

        if sig.direction == 'LONG':
            pnl = (price / entry - 1) * 100
            if stop and price <= stop:
                return {'result': 'STOPPED', 'exit_price': price, 'pnl': pnl}
            if t3 and price >= t3:
                return {'result': 'WIN_T3', 'exit_price': price, 'pnl': pnl}
            if t2 and price >= t2:
                return {'result': 'WIN_T2', 'exit_price': price, 'pnl': pnl}
            if t1 and price >= t1:
                return {'result': 'WIN_T1', 'exit_price': price, 'pnl': pnl}
        else:  # SHORT: profit when price falls
            pnl = (entry - price) / entry * 100
            if stop and price >= stop:
                return {'result': 'STOPPED', 'exit_price': price, 'pnl': pnl}
            if t3 and price <= t3:
                return {'result': 'WIN_T3', 'exit_price': price, 'pnl': pnl}
            if t2 and price <= t2:
                return {'result': 'WIN_T2', 'exit_price': price, 'pnl': pnl}
            if t1 and price <= t1:
                return {'result': 'WIN_T1', 'exit_price': price, 'pnl': pnl}
        return None

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return forward-test statistics for /stats Telegram command."""
        try:
            with self._db.session() as s:
                closed = (
                    s.query(SignalHistory)
                    .filter(
                        SignalHistory.result.isnot(None),
                        SignalHistory.result != 'EXPIRED',
                    )
                    .all()
                )
                open_count = (
                    s.query(SignalHistory).filter(SignalHistory.result.is_(None)).count()
                )

                # All ORM attribute access happens inside the session to avoid
                # DetachedInstanceError (expire_on_commit=True causes SQLAlchemy
                # to expire object attributes after session.commit()).
                total = len(closed)
                if total == 0:
                    return {'total': 0, 'open': open_count, 'win_rate': 0.0, 'avg_pnl': 0.0}

                wins = [r for r in closed if r.result and r.result.startswith('WIN')]
                losses = [r for r in closed if r.result == 'STOPPED']

                pnl_vals = [r.pnl_percent for r in closed if r.pnl_percent is not None]
                avg_pnl = sum(pnl_vals) / len(pnl_vals) if pnl_vals else 0.0

                long_closed = [r for r in closed if r.direction == 'LONG']
                short_closed = [r for r in closed if r.direction == 'SHORT']
                long_wins = sum(1 for r in wins if r.direction == 'LONG')
                short_wins = sum(1 for r in wins if r.direction == 'SHORT')

                return {
                    'total': total,
                    'open': open_count,
                    'wins': len(wins),
                    'losses': len(losses),
                    'win_rate': round(len(wins) / total * 100, 1),
                    'avg_pnl': round(avg_pnl, 2),
                    'best': round(max(pnl_vals), 2) if pnl_vals else 0.0,
                    'worst': round(min(pnl_vals), 2) if pnl_vals else 0.0,
                    'long_total': len(long_closed),
                    'long_wins': long_wins,
                    'long_win_rate': round(long_wins / len(long_closed) * 100, 1) if long_closed else 0.0,
                    'short_total': len(short_closed),
                    'short_wins': short_wins,
                    'short_win_rate': round(short_wins / len(short_closed) * 100, 1) if short_closed else 0.0,
                    't1_wins': sum(1 for r in wins if r.result == 'WIN_T1'),
                    't2_wins': sum(1 for r in wins if r.result == 'WIN_T2'),
                    't3_wins': sum(1 for r in wins if r.result == 'WIN_T3'),
                }
        except Exception as e:
            logger.error(f'Failed to get stats: {e}')
            return {'total': 0, 'open': 0, 'error': str(e)}

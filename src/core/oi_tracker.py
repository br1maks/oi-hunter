import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional, Set
from ..database import DatabaseManager, OIRepository, get_database
logger = logging.getLogger(__name__)

class OITracker:
    DEFAULT_TOP_N = 50
    CLEANUP_HOURS = 24

    def __init__(self, db: Optional[DatabaseManager]=None, top_n: int=DEFAULT_TOP_N):
        self._db = db or get_database()
        self._repo = OIRepository(self._db)
        self._top_n = top_n
        self._current_watchlist: Set[str] = set()

    @property
    def watchlist(self) -> Set[str]:
        return self._current_watchlist.copy()

    @property
    def watchlist_size(self) -> int:
        return len(self._current_watchlist)

    def record_snapshots(self, snapshots: List[Dict], sort_key: str='anomaly_score') -> int:
        if not snapshots:
            return 0
        sorted_snapshots = sorted(snapshots, key=lambda x: x.get(sort_key, 0), reverse=True)
        top_snapshots = sorted_snapshots[:self._top_n]
        self._current_watchlist = {s.get('symbol') for s in top_snapshots if s.get('symbol')}
        records = []
        now = datetime.now(timezone.utc)
        for snap in top_snapshots:
            symbol = snap.get('symbol')
            if not symbol:
                continue
            oi_usd = snap.get('oi_usd')
            if oi_usd is None:
                oi_contracts = snap.get('oi_contracts', 0)
                price = snap.get('price', 0)
                contract_size = snap.get('contract_size', 1)
                oi_usd = oi_contracts * price * contract_size
            if oi_usd <= 0:
                continue
            records.append({'symbol': symbol, 'oi_usd': oi_usd, 'price': snap.get('price', 0), 'volume_24h': snap.get('volume_24h'), 'timestamp': now})
        if records:
            saved = self._repo.save_snapshots_batch(records)
            logger.debug(f'OITracker: Saved {saved} OI snapshots')
            return saved
        return 0

    def record_single(self, symbol: str, oi_usd: float, price: float, volume_24h: Optional[float]=None) -> bool:
        try:
            self._repo.save_snapshot(symbol=symbol, oi_usd=oi_usd, price=price, volume_24h=volume_24h)
            self._current_watchlist.add(symbol)
            return True
        except Exception as e:
            logger.error(f'Failed to record OI for {symbol}: {e}')
            return False

    def cleanup_old_data(self, hours: int=CLEANUP_HOURS) -> int:
        try:
            deleted = self._repo.cleanup_old_data(hours=hours)
            if deleted > 0:
                logger.info(f'OITracker: Cleaned up {deleted} old records')
            return deleted
        except Exception as e:
            logger.error(f'Failed to cleanup old data: {e}')
            return 0

    def get_oi_change_pct(self, symbol: str, minutes: int) -> Optional[float]:
        try:
            history = self._repo.get_history(symbol, minutes=int(minutes * 1.2))
            if len(history) < 2:
                return None
            current_oi = history[-1][1]
            from datetime import timedelta
            current_ts = history[-1][0]
            target_ts = current_ts - timedelta(minutes=minutes)
            closest = min(history[:-1], key=lambda x: abs((x[0] - target_ts).total_seconds()))
            actual_minutes_ago = (current_ts - closest[0]).total_seconds() / 60
            if actual_minutes_ago < minutes * 0.5:
                return None
            past_oi = closest[1]
            if past_oi <= 0:
                return None
            return (current_oi - past_oi) / past_oi * 100
        except Exception as e:
            logger.debug(f'get_oi_change_pct failed for {symbol}: {e}')
            return None

    def get_tracked_symbols(self) -> List[str]:
        return self._repo.get_tracked_symbols()

    def get_stats(self) -> Dict:
        return {'watchlist_size': len(self._current_watchlist), 'total_records': self._repo.get_record_count(), 'tracked_symbols': len(self._repo.get_tracked_symbols())}

    def is_tracking(self, symbol: str) -> bool:
        return symbol in self._current_watchlist

    def add_to_watchlist(self, symbol: str) -> None:
        self._current_watchlist.add(symbol)

    def remove_from_watchlist(self, symbol: str) -> None:
        self._current_watchlist.discard(symbol)
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from sqlalchemy import desc, func
from sqlalchemy.orm import Session
from .models import OIHistory
from .connection import DatabaseManager, get_database

class OIRepository:

    def __init__(self, db: Optional[DatabaseManager]=None):
        self._db = db or get_database()

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def save_snapshot(self, symbol: str, oi_usd: float, price: float, volume_24h: Optional[float]=None, timestamp: Optional[datetime]=None) -> OIHistory:
        with self._db.session() as session:
            record = OIHistory(symbol=symbol, timestamp=timestamp or self._utcnow(), oi_usd=oi_usd, price=price, volume_24h=volume_24h)
            session.add(record)
            session.flush()
            session.refresh(record)
            session.expunge(record)
            return record

    def save_snapshots_batch(self, snapshots: List[dict]) -> int:
        with self._db.session() as session:
            now = self._utcnow()
            records = [OIHistory(symbol=s['symbol'], timestamp=s.get('timestamp', now), oi_usd=s['oi_usd'], price=s['price'], volume_24h=s.get('volume_24h')) for s in snapshots]
            session.add_all(records)
            return len(records)

    def get_history(self, symbol: str, minutes: int=30) -> List[Tuple[datetime, float]]:
        cutoff = self._utcnow() - timedelta(minutes=minutes)
        with self._db.session() as session:
            records = session.query(OIHistory).filter(OIHistory.symbol == symbol, OIHistory.timestamp >= cutoff).order_by(OIHistory.timestamp).all()
            return [(r.timestamp, r.oi_usd) for r in records]

    def get_latest(self, symbol: str) -> Optional[OIHistory]:
        with self._db.session() as session:
            record = session.query(OIHistory).filter(OIHistory.symbol == symbol).order_by(desc(OIHistory.timestamp)).first()
            if record is not None:
                session.expunge(record)
            return record

    def get_record_count(self, symbol: Optional[str]=None) -> int:
        with self._db.session() as session:
            query = session.query(func.count(OIHistory.id))
            if symbol:
                query = query.filter(OIHistory.symbol == symbol)
            return query.scalar()

    def get_tracked_symbols(self) -> List[str]:
        with self._db.session() as session:
            result = session.query(OIHistory.symbol).distinct().all()
            return [r[0] for r in result]

    def cleanup_old_data(self, hours: int=24) -> int:
        cutoff = self._utcnow() - timedelta(hours=hours)
        with self._db.session() as session:
            deleted = session.query(OIHistory).filter(OIHistory.timestamp < cutoff).delete()
            return deleted

    def get_velocity_data(self, symbol: str, minutes: int=15) -> List[Tuple[float, float]]:
        history = self.get_history(symbol, minutes)
        if len(history) < 2:
            return []
        first_time = history[0][0]
        return [((ts - first_time).total_seconds() / 60, oi) for ts, oi in history]
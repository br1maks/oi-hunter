import pytest
import os
from datetime import datetime, timedelta, timezone

def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
from pathlib import Path
from src.database import DatabaseManager, OIRepository, OIHistory

class TestDatabaseManager:

    def test_singleton(self):
        db1 = DatabaseManager()
        db2 = DatabaseManager()
        assert db1 is db2

    def test_creates_db_file(self):
        db = DatabaseManager()
        assert db.db_path.exists()

    def test_session_context_manager(self):
        db = DatabaseManager()
        with db.session() as session:
            assert session is not None
            assert session.is_active

class TestOIRepository:

    def setup_method(self):
        self.db = DatabaseManager()
        self.repo = OIRepository(self.db)
        with self.db.session() as session:
            session.query(OIHistory).filter(OIHistory.symbol == 'TEST_USDT').delete()

    def test_save_snapshot(self):
        record = self.repo.save_snapshot(symbol='TEST_USDT', oi_usd=1000000.0, price=100.0, volume_24h=500000.0)
        assert record.id is not None
        assert record.symbol == 'TEST_USDT'
        assert record.oi_usd == 1000000.0

    def test_save_batch(self):
        snapshots = [{'symbol': 'TEST_USDT', 'oi_usd': 1000000, 'price': 100}, {'symbol': 'TEST_USDT', 'oi_usd': 1050000, 'price': 101}, {'symbol': 'TEST_USDT', 'oi_usd': 1100000, 'price': 102}]
        count = self.repo.save_snapshots_batch(snapshots)
        assert count == 3

    def test_get_history(self):
        now = _utcnow()
        for i in range(5):
            self.repo.save_snapshot(symbol='TEST_USDT', oi_usd=1000000 + i * 10000, price=100.0, timestamp=now - timedelta(minutes=4 - i))
        history = self.repo.get_history('TEST_USDT', minutes=10)
        assert len(history) == 5
        assert history[0][1] == 1000000
        assert history[4][1] == 1040000

    def test_get_history_empty(self):
        history = self.repo.get_history('NONEXISTENT_USDT', minutes=30)
        assert history == []

    def test_get_latest(self):
        now = _utcnow()
        self.repo.save_snapshot('TEST_USDT', 1000000, 100, timestamp=now - timedelta(minutes=5))
        self.repo.save_snapshot('TEST_USDT', 1100000, 110, timestamp=now)
        latest = self.repo.get_latest('TEST_USDT')
        assert latest is not None
        assert latest.oi_usd == 1100000

    def test_cleanup_old_data(self):
        now = _utcnow()
        self.repo.save_snapshot('TEST_USDT', 1000000, 100, timestamp=now - timedelta(hours=25))
        self.repo.save_snapshot('TEST_USDT', 1100000, 110, timestamp=now)
        deleted = self.repo.cleanup_old_data(hours=24)
        assert deleted >= 1
        history = self.repo.get_history('TEST_USDT', minutes=60)
        assert len(history) >= 1

    def test_get_tracked_symbols(self):
        self.repo.save_snapshot('TEST_USDT', 1000000, 100)
        self.repo.save_snapshot('TEST2_USDT', 2000000, 200)
        symbols = self.repo.get_tracked_symbols()
        assert 'TEST_USDT' in symbols
        assert 'TEST2_USDT' in symbols

    def teardown_method(self):
        with self.db.session() as session:
            session.query(OIHistory).filter(OIHistory.symbol.like('TEST%')).delete(synchronize_session='fetch')
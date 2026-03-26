import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from src.core.oi_tracker import OITracker
from src.database import DatabaseManager, OIRepository

class TestOITrackerInit:

    def test_default_top_n(self):
        with patch('src.core.oi_tracker.get_database') as mock_db:
            mock_db.return_value = MagicMock()
            tracker = OITracker()
            assert tracker._top_n == 50

    def test_custom_top_n(self):
        with patch('src.core.oi_tracker.get_database') as mock_db:
            mock_db.return_value = MagicMock()
            tracker = OITracker(top_n=20)
            assert tracker._top_n == 20

    def test_empty_watchlist_on_init(self):
        with patch('src.core.oi_tracker.get_database') as mock_db:
            mock_db.return_value = MagicMock()
            tracker = OITracker()
            assert tracker.watchlist_size == 0
            assert tracker.watchlist == set()

class TestRecordSnapshots:

    def setup_method(self):
        self.mock_db = MagicMock(spec=DatabaseManager)
        self.mock_repo = MagicMock(spec=OIRepository)
        with patch('src.core.oi_tracker.OIRepository') as MockRepo:
            MockRepo.return_value = self.mock_repo
            self.tracker = OITracker(db=self.mock_db, top_n=3)

    def test_empty_snapshots(self):
        result = self.tracker.record_snapshots([])
        assert result == 0

    def test_sorts_by_anomaly_score(self):
        snapshots = [{'symbol': 'LOW_USDT', 'oi_usd': 100, 'price': 1.0, 'anomaly_score': 2.0}, {'symbol': 'HIGH_USDT', 'oi_usd': 100, 'price': 1.0, 'anomaly_score': 9.0}, {'symbol': 'MID_USDT', 'oi_usd': 100, 'price': 1.0, 'anomaly_score': 5.0}]
        self.mock_repo.save_snapshots_batch.return_value = 3
        self.tracker.record_snapshots(snapshots)
        watchlist = self.tracker.watchlist
        assert 'HIGH_USDT' in watchlist
        assert 'MID_USDT' in watchlist

    def test_takes_top_n_only(self):
        snapshots = [{'symbol': f'TOKEN{i}_USDT', 'oi_usd': 100, 'price': 1.0, 'anomaly_score': float(i)} for i in range(10)]
        self.mock_repo.save_snapshots_batch.return_value = 3
        self.tracker.record_snapshots(snapshots)
        watchlist = self.tracker.watchlist
        assert len(watchlist) == 3
        assert 'TOKEN9_USDT' in watchlist
        assert 'TOKEN8_USDT' in watchlist
        assert 'TOKEN7_USDT' in watchlist
        assert 'TOKEN0_USDT' not in watchlist

    def test_skips_missing_symbol(self):
        snapshots = [{'oi_usd': 100, 'price': 1.0, 'anomaly_score': 9.0}, {'symbol': 'VALID_USDT', 'oi_usd': 100, 'price': 1.0, 'anomaly_score': 8.0}]
        self.mock_repo.save_snapshots_batch.return_value = 1
        result = self.tracker.record_snapshots(snapshots)
        call_args = self.mock_repo.save_snapshots_batch.call_args
        records = call_args[0][0]
        assert len(records) == 1
        assert records[0]['symbol'] == 'VALID_USDT'

    def test_skips_zero_oi(self):
        snapshots = [{'symbol': 'ZERO_USDT', 'oi_usd': 0, 'price': 1.0, 'anomaly_score': 9.0}, {'symbol': 'NEGATIVE_USDT', 'oi_usd': -100, 'price': 1.0, 'anomaly_score': 8.0}, {'symbol': 'VALID_USDT', 'oi_usd': 100, 'price': 1.0, 'anomaly_score': 7.0}]
        self.mock_repo.save_snapshots_batch.return_value = 1
        self.tracker.record_snapshots(snapshots)
        call_args = self.mock_repo.save_snapshots_batch.call_args
        records = call_args[0][0]
        assert len(records) == 1
        assert records[0]['symbol'] == 'VALID_USDT'

    def test_calculates_oi_from_contracts(self):
        snapshots = [{'symbol': 'CALC_USDT', 'oi_contracts': 1000, 'price': 2.5, 'contract_size': 10, 'anomaly_score': 9.0}]
        self.mock_repo.save_snapshots_batch.return_value = 1
        self.tracker.record_snapshots(snapshots)
        call_args = self.mock_repo.save_snapshots_batch.call_args
        records = call_args[0][0]
        assert records[0]['oi_usd'] == 25000

class TestRecordSingle:

    def setup_method(self):
        self.mock_db = MagicMock(spec=DatabaseManager)
        self.mock_repo = MagicMock(spec=OIRepository)
        with patch('src.core.oi_tracker.OIRepository') as MockRepo:
            MockRepo.return_value = self.mock_repo
            self.tracker = OITracker(db=self.mock_db)

    def test_record_single_success(self):
        result = self.tracker.record_single(symbol='BTC_USDT', oi_usd=1000000, price=50000, volume_24h=500000)
        assert result is True
        self.mock_repo.save_snapshot.assert_called_once()
        assert 'BTC_USDT' in self.tracker.watchlist

    def test_record_single_adds_to_watchlist(self):
        self.tracker.record_single('NEW_USDT', 100, 1.0)
        assert 'NEW_USDT' in self.tracker.watchlist

    def test_record_single_handles_error(self):
        self.mock_repo.save_snapshot.side_effect = Exception('DB Error')
        result = self.tracker.record_single('FAIL_USDT', 100, 1.0)
        assert result is False

class TestWatchlistManagement:

    def setup_method(self):
        self.mock_db = MagicMock(spec=DatabaseManager)
        self.mock_repo = MagicMock(spec=OIRepository)
        with patch('src.core.oi_tracker.OIRepository') as MockRepo:
            MockRepo.return_value = self.mock_repo
            self.tracker = OITracker(db=self.mock_db)

    def test_add_to_watchlist(self):
        self.tracker.add_to_watchlist('BTC_USDT')
        assert 'BTC_USDT' in self.tracker.watchlist

    def test_remove_from_watchlist(self):
        self.tracker.add_to_watchlist('BTC_USDT')
        self.tracker.remove_from_watchlist('BTC_USDT')
        assert 'BTC_USDT' not in self.tracker.watchlist

    def test_is_tracking(self):
        self.tracker.add_to_watchlist('BTC_USDT')
        assert self.tracker.is_tracking('BTC_USDT') is True
        assert self.tracker.is_tracking('ETH_USDT') is False

    def test_watchlist_returns_copy(self):
        self.tracker.add_to_watchlist('BTC_USDT')
        watchlist = self.tracker.watchlist
        watchlist.add('FAKE_USDT')
        assert 'FAKE_USDT' not in self.tracker.watchlist

class TestCleanup:

    def setup_method(self):
        self.mock_db = MagicMock(spec=DatabaseManager)
        self.mock_repo = MagicMock(spec=OIRepository)
        with patch('src.core.oi_tracker.OIRepository') as MockRepo:
            MockRepo.return_value = self.mock_repo
            self.tracker = OITracker(db=self.mock_db)

    def test_cleanup_default_24h(self):
        self.mock_repo.cleanup_old_data.return_value = 100
        deleted = self.tracker.cleanup_old_data()
        self.mock_repo.cleanup_old_data.assert_called_once_with(hours=24)
        assert deleted == 100

    def test_cleanup_custom_hours(self):
        self.mock_repo.cleanup_old_data.return_value = 50
        deleted = self.tracker.cleanup_old_data(hours=12)
        self.mock_repo.cleanup_old_data.assert_called_once_with(hours=12)
        assert deleted == 50

    def test_cleanup_handles_error(self):
        self.mock_repo.cleanup_old_data.side_effect = Exception('DB Error')
        deleted = self.tracker.cleanup_old_data()
        assert deleted == 0

class TestStats:

    def setup_method(self):
        self.mock_db = MagicMock(spec=DatabaseManager)
        self.mock_repo = MagicMock(spec=OIRepository)
        with patch('src.core.oi_tracker.OIRepository') as MockRepo:
            MockRepo.return_value = self.mock_repo
            self.tracker = OITracker(db=self.mock_db)

    def test_get_stats(self):
        self.tracker.add_to_watchlist('BTC_USDT')
        self.tracker.add_to_watchlist('ETH_USDT')
        self.mock_repo.get_record_count.return_value = 1000
        self.mock_repo.get_tracked_symbols.return_value = ['BTC_USDT', 'ETH_USDT', 'DOGE_USDT']
        stats = self.tracker.get_stats()
        assert stats['watchlist_size'] == 2
        assert stats['total_records'] == 1000
        assert stats['tracked_symbols'] == 3
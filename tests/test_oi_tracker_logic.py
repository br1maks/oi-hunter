from unittest.mock import MagicMock, patch

def test_oi_tracker():
    print('=' * 70)
    print('  OI TRACKER - LOGIC TEST')
    print('=' * 70)
    mock_db = MagicMock()
    mock_repo = MagicMock()
    with patch('src.core.oi_tracker.OIRepository') as MockRepo:
        MockRepo.return_value = mock_repo
        from src.core.oi_tracker import OITracker
        print('\n[TEST 1] Initialize OITracker')
        tracker = OITracker(db=mock_db, top_n=5)
        print(f'  top_n = {tracker._top_n}')
        print(f'  watchlist_size = {tracker.watchlist_size}')
        print(f'  [OK] Initialized with empty watchlist')
        print('\n[TEST 2] Record snapshots - sorting by anomaly_score')
        snapshots = [{'symbol': 'LOW_USDT', 'oi_usd': 100000, 'price': 1.0, 'anomaly_score': 2.0}, {'symbol': 'HIGH_USDT', 'oi_usd': 500000, 'price': 5.0, 'anomaly_score': 9.5}, {'symbol': 'MID1_USDT', 'oi_usd': 200000, 'price': 2.0, 'anomaly_score': 5.0}, {'symbol': 'MID2_USDT', 'oi_usd': 300000, 'price': 3.0, 'anomaly_score': 6.0}, {'symbol': 'MID3_USDT', 'oi_usd': 400000, 'price': 4.0, 'anomaly_score': 7.0}, {'symbol': 'EXTRA_USDT', 'oi_usd': 150000, 'price': 1.5, 'anomaly_score': 4.0}]
        mock_repo.save_snapshots_batch.return_value = 5
        result = tracker.record_snapshots(snapshots)
        print(f'  Input: 6 snapshots')
        print(f'  top_n: 5')
        print(f'  Watchlist: {tracker.watchlist}')
        expected_watchlist = {'HIGH_USDT', 'MID3_USDT', 'MID2_USDT', 'MID1_USDT', 'EXTRA_USDT'}
        assert tracker.watchlist == expected_watchlist, f'Expected {expected_watchlist}'
        assert 'LOW_USDT' not in tracker.watchlist, 'LOW_USDT should be filtered out'
        print(f'  [OK] Top-5 selected correctly (LOW_USDT filtered out)')
        call_args = mock_repo.save_snapshots_batch.call_args
        records = call_args[0][0]
        print(f'\n  Records passed to DB:')
        for r in records:
            print(f"    {r['symbol']}: ${r['oi_usd']:,}")
        print('\n[TEST 3] Skip snapshots without symbol')
        tracker2 = OITracker(db=mock_db, top_n=3)
        snapshots_with_missing = [{'oi_usd': 100, 'price': 1.0, 'anomaly_score': 10.0}, {'symbol': 'VALID1_USDT', 'oi_usd': 200, 'price': 2.0, 'anomaly_score': 8.0}, {'symbol': 'VALID2_USDT', 'oi_usd': 300, 'price': 3.0, 'anomaly_score': 6.0}]
        mock_repo.save_snapshots_batch.return_value = 2
        tracker2.record_snapshots(snapshots_with_missing)
        print(f'  Input: 3 snapshots (1 without symbol)')
        print(f'  Watchlist: {tracker2.watchlist}')
        assert 'VALID1_USDT' in tracker2.watchlist
        assert 'VALID2_USDT' in tracker2.watchlist
        assert len(tracker2.watchlist) == 2
        print(f'  [OK] Missing symbol handled correctly')
        print('\n[TEST 4] Skip zero/negative OI')
        tracker3 = OITracker(db=mock_db, top_n=5)
        snapshots_with_zero_oi = [{'symbol': 'ZERO_USDT', 'oi_usd': 0, 'price': 1.0, 'anomaly_score': 10.0}, {'symbol': 'NEG_USDT', 'oi_usd': -100, 'price': 1.0, 'anomaly_score': 9.0}, {'symbol': 'VALID_USDT', 'oi_usd': 500, 'price': 1.0, 'anomaly_score': 5.0}]
        mock_repo.save_snapshots_batch.return_value = 1
        tracker3.record_snapshots(snapshots_with_zero_oi)
        call_args = mock_repo.save_snapshots_batch.call_args
        records = call_args[0][0]
        print(f'  Input: 3 snapshots (1 zero OI, 1 negative OI)')
        print(f'  Records saved: {len(records)}')
        assert len(records) == 1
        assert records[0]['symbol'] == 'VALID_USDT'
        print(f'  [OK] Zero/negative OI filtered out')
        print('\n[TEST 5] Calculate OI from contracts if oi_usd not provided')
        tracker4 = OITracker(db=mock_db, top_n=5)
        snapshots_with_contracts = [{'symbol': 'CALC_USDT', 'oi_contracts': 1000, 'price': 2.5, 'contract_size': 10, 'anomaly_score': 9.0}]
        mock_repo.save_snapshots_batch.return_value = 1
        tracker4.record_snapshots(snapshots_with_contracts)
        call_args = mock_repo.save_snapshots_batch.call_args
        records = call_args[0][0]
        expected_oi = 1000 * 2.5 * 10
        print(f'  oi_contracts=1000, price=2.5, contract_size=10')
        print(f'  Expected OI: ${expected_oi:,}')
        print(f"  Calculated OI: ${records[0]['oi_usd']:,}")
        assert records[0]['oi_usd'] == expected_oi
        print(f'  [OK] OI calculated correctly from contracts')
        print('\n[TEST 6] Watchlist management')
        tracker5 = OITracker(db=mock_db, top_n=5)
        tracker5.add_to_watchlist('BTC_USDT')
        tracker5.add_to_watchlist('ETH_USDT')
        print(f'  Added BTC_USDT, ETH_USDT')
        print(f'  Watchlist: {tracker5.watchlist}')
        assert tracker5.is_tracking('BTC_USDT')
        assert tracker5.is_tracking('ETH_USDT')
        assert not tracker5.is_tracking('DOGE_USDT')
        tracker5.remove_from_watchlist('BTC_USDT')
        print(f'  Removed BTC_USDT')
        print(f'  Watchlist: {tracker5.watchlist}')
        assert not tracker5.is_tracking('BTC_USDT')
        assert tracker5.is_tracking('ETH_USDT')
        print(f'  [OK] Watchlist management works')
        print('\n[TEST 7] Cleanup old data')
        mock_repo.cleanup_old_data.return_value = 150
        deleted = tracker.cleanup_old_data(hours=12)
        print(f'  cleanup_old_data(hours=12) returned: {deleted}')
        mock_repo.cleanup_old_data.assert_called_with(hours=12)
        assert deleted == 150
        print(f'  [OK] Cleanup called with correct hours')
        print('\n[TEST 8] Get stats')
        mock_repo.get_record_count.return_value = 5000
        mock_repo.get_tracked_symbols.return_value = ['BTC_USDT', 'ETH_USDT', 'DOGE_USDT']
        stats = tracker.get_stats()
        print(f'  Stats: {stats}')
        assert 'watchlist_size' in stats
        assert 'total_records' in stats
        assert 'tracked_symbols' in stats
        print(f'  [OK] Stats returned correctly')
        print('\n[TEST 9] Record single symbol')
        tracker6 = OITracker(db=mock_db, top_n=5)
        result = tracker6.record_single(symbol='SINGLE_USDT', oi_usd=1000000, price=100.0, volume_24h=5000000)
        print(f"  record_single('SINGLE_USDT', 1000000, 100.0, 5000000)")
        print(f'  Result: {result}')
        print(f'  Watchlist: {tracker6.watchlist}')
        assert result is True
        assert 'SINGLE_USDT' in tracker6.watchlist
        mock_repo.save_snapshot.assert_called_once()
        print(f'  [OK] Single record saved and added to watchlist')
    print('\n' + '=' * 70)
    print('  ALL TESTS PASSED!')
    print('=' * 70)
if __name__ == '__main__':
    test_oi_tracker()
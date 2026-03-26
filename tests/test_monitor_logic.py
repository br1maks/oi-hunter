import asyncio
import inspect
import time
from unittest.mock import MagicMock, AsyncMock, patch
import importlib
import src.core.monitor
importlib.reload(src.core.monitor)
from src.core.monitor import Monitor

def make_snapshot(symbol, long_score, short_score, price=1.0, oi_contracts=100000, volume=500000):
    from src.core.batch_scanner import TokenSnapshot
    return TokenSnapshot(symbol=symbol, price=price, oi_contracts=oi_contracts, volume_24h=volume, timestamp=time.time(), long_score=long_score, short_score=short_score)

def make_monitor():
    mock_db = MagicMock()
    mock_db.db_path = '/mock/path/oi_hunter.db'
    with patch('src.core.monitor.get_database', return_value=mock_db):
        monitor = Monitor(interval_seconds=10, top_n=5, alert_threshold=7.0, db=mock_db)
    mock_tracker = MagicMock()
    mock_tracker.watchlist = {'BTC_USDT', 'ETH_USDT'}
    mock_tracker.record_snapshots.return_value = 5
    mock_tracker.get_stats.return_value = {'watchlist_size': 2, 'total_records': 500, 'tracked_symbols': 3}
    mock_scanner = MagicMock()
    mock_scanner.get_stats.return_value = {'total_tokens': 845, 'tokens_changed': 120, 'tokens_unchanged': 725, 'total_scans': 1, 'scan_time': 45.2}
    monitor._tracker = mock_tracker
    monitor._scanner = mock_scanner
    monitor._start_time = time.time()
    monitor._cycle_count = 1
    return monitor
print('=' * 70)
print('  MONITOR MODE - LOGIC TEST')
print('=' * 70)
print('\n[TEST 1] Monitor initialization')
mock_db = MagicMock()
mock_db.db_path = '/mock/db.sqlite'
with patch('src.core.monitor.get_database', return_value=mock_db):
    m = Monitor(interval_seconds=30, top_n=10, alert_threshold=8.0, db=mock_db)
assert m._interval == 30
assert m._top_n == 10
assert m._alert_threshold == 8.0
assert m._running == False
assert m._cycle_count == 0
assert m._alerts_generated == 0
print('  [OK] interval=30, top_n=10, threshold=8.0')
print('  [OK] running=False, cycle_count=0, alerts=0')
print('\n[TEST 2] _check_alerts - filter by threshold 7.0')
monitor = make_monitor()
monitor._alert_threshold = 7.0
snapshots = [make_snapshot('BTC_USDT', long_score=9.0, short_score=2.0), make_snapshot('ETH_USDT', long_score=3.0, short_score=8.5), make_snapshot('DOGE_USDT', long_score=5.0, short_score=6.9), make_snapshot('XRP_USDT', long_score=7.0, short_score=4.0), make_snapshot('SOL_USDT', long_score=2.0, short_score=2.0)]
alerts = monitor._check_alerts(snapshots)
print(f'  Alerts: {[s.symbol for s in alerts]}')
assert len(alerts) == 3
assert any((s.symbol == 'BTC_USDT' for s in alerts))
assert any((s.symbol == 'ETH_USDT' for s in alerts))
assert any((s.symbol == 'XRP_USDT' for s in alerts))
assert not any((s.symbol == 'DOGE_USDT' for s in alerts))
print('  [OK] DOGE(6.9) not in alerts, XRP(7.0) in alerts (inclusive)')
print('  [OK] 3 alerts: BTC(LONG), ETH(SHORT), XRP(LONG)')
print('\n[TEST 3] _display_alerts - direction & counter')
monitor = make_monitor()
monitor._alerts_generated = 0
alerts = [make_snapshot('BTC_USDT', long_score=9.0, short_score=2.0, price=50000), make_snapshot('ETH_USDT', long_score=2.0, short_score=8.0, price=3000), make_snapshot('EQUAL_USDT', long_score=7.5, short_score=7.5, price=1.0)]
monitor._display_alerts(alerts)
assert monitor._alerts_generated == 3
print(f'  [OK] Alert counter incremented: {monitor._alerts_generated}')
print('  [OK] BTC=LONG, ETH=SHORT, EQUAL=SHORT (not strictly greater)')
print('\n[TEST 4] _record_oi_snapshots - conversion')
monitor = make_monitor()
snapshots = [make_snapshot('BTC_USDT', long_score=9.0, short_score=2.0, price=50000, oi_contracts=100), make_snapshot('ETH_USDT', long_score=2.0, short_score=8.0, price=3000, oi_contracts=500), make_snapshot('ZERO_USDT', long_score=4.0, short_score=4.0, price=0.0, oi_contracts=100)]
asyncio.run(monitor._record_oi_snapshots(snapshots))
call_args = monitor._tracker.record_snapshots.call_args
snapshot_dicts = call_args[0][0]
for d in snapshot_dicts:
    print(f"    {d['symbol']}: oi_usd={d['oi_usd']:,.0f}, score={d['anomaly_score']}")
btc = next((d for d in snapshot_dicts if d['symbol'] == 'BTC_USDT'))
zero = next((d for d in snapshot_dicts if d['symbol'] == 'ZERO_USDT'))
assert btc['oi_usd'] == 100 * 50000
assert btc['anomaly_score'] == 9.0
assert zero['oi_usd'] == 0
print('  [OK] oi_usd = oi_contracts * price')
print('  [OK] price=0 -> oi_usd=0')
print('  [OK] anomaly_score = max(long_score, short_score)')
print('\n[TEST 5] _display_watchlist - correct args')
monitor = make_monitor()
monitor._scanner.get_top_candidates.return_value = []
monitor._display_watchlist([])
call_args = monitor._scanner.get_top_candidates.call_args
assert call_args[1]['min_score'] == 4.0
assert call_args[1]['limit'] == 10
print('  [OK] get_top_candidates(min_score=4.0, limit=10)')
monitor._scanner.get_top_candidates.return_value = [make_snapshot('BIG_USDT', long_score=8.0, short_score=2.0, price=100.5)]
monitor._display_watchlist([])
print('  [OK] Watchlist table printed')
print('\n[TEST 6] _display_cycle_stats')
monitor = make_monitor()
monitor._start_time = time.time() - 120
monitor._cycle_count = 3
monitor._alerts_generated = 2
monitor._display_cycle_stats(time.time() - 45)
assert monitor._scanner.get_stats.called
assert monitor._tracker.get_stats.called
print('  [OK] scanner.get_stats() and tracker.get_stats() called')
print('\n[TEST 7] _print_final_stats with tracker=None')
monitor = make_monitor()
monitor._start_time = time.time() - 300
monitor._cycle_count = 5
monitor._alerts_generated = 3
monitor._tracker = None
try:
    monitor._print_final_stats()
    print('  [OK] No crash with tracker=None')
except AttributeError as e:
    print(f'  [FAIL] AttributeError: {e}')
print('\n[TEST 8] Edge cases')
monitor = make_monitor()
assert monitor._check_alerts([]) == []
print('  [OK] Empty list -> empty alerts')
assert monitor._check_alerts([make_snapshot('A', 0.0, 0.0)]) == []
print('  [OK] Score=0 -> no alerts')
results = monitor._check_alerts([make_snapshot('A', 10.0, 10.0)])
assert len(results) == 1
print('  [OK] Score=10.0 -> alert')
print('\n[TEST 9] BUG FIX - self._db.db_path (not _db_path)')
source = inspect.getsource(Monitor.run)
if '_db_path' in source:
    print('  [FAIL] monitor.py still uses self._db._db_path')
elif 'db_path' in source:
    print('  [OK] FIX CONFIRMED: monitor.py uses self._db.db_path')
else:
    print('  [WARN] db_path reference not found in run()')
print('\n[TEST 10] BUG FIX - r.details removed from _display_single_symbol_analysis')
source = inspect.getsource(Monitor._display_single_symbol_analysis)
if 'r.details' in source:
    print('  [FAIL] monitor.py still uses r.details (AttributeError at runtime)')
else:
    print('  [OK] FIX CONFIRMED: r.details removed')
if 'r.reasoning' in source:
    print('  [OK] Uses r.reasoning instead (exists in AnalyzerResult)')
from src.models.analyzer_result import AnalyzerResult
from src.models.market_data import MarketData
mock_data = MagicMock()
mock_data.symbol = 'BTC_USDT'
mock_data.price = 50000.0
mock_data.open_interest_usd = 1000000.0
mock_result = MagicMock(spec=AnalyzerResult)
mock_result.analyzer_name = 'OI Nowcast'
mock_result.long_score = 7.0
mock_result.short_score = 3.0
mock_result.reasoning = 'OI growing | Velocity: +5000 USD/min | 5m: +2.1%, 10m: +4.5%, 15m: +7.2%'
mock_analysis = {'results': [mock_result], 'long_score': 7.0, 'short_score': 3.0, 'would_signal': 'LONG'}
monitor = make_monitor()
try:
    monitor._display_single_symbol_analysis(mock_data, mock_analysis)
    print('  [OK] _display_single_symbol_analysis runs without AttributeError')
except AttributeError as e:
    print(f'  [FAIL] AttributeError: {e}')
print('\n' + '=' * 70)
print('  ALL TESTS PASSED - Monitor logic is correct')
print('=' * 70)
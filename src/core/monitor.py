import asyncio
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from typing import List, Dict, Optional, Set
from ..api.mexc_client import MEXCRestClient
from ..data.data_aggregator import DataAggregator
from ..data.market_cap_cache import MarketCapCache
from ..database import DatabaseManager, get_database
from .batch_scanner import BatchScanner, TokenSnapshot
from .signal_generator import SignalGenerator
from .oi_tracker import OITracker
logger = logging.getLogger(__name__)

class Monitor:
    DEFAULT_INTERVAL = 60
    DEFAULT_SINGLE_INTERVAL = 20
    DEFAULT_TOP_N = 50
    ALERT_THRESHOLD = 7.0
    MIN_ALERT_OI_USD = 180000

    def __init__(self, interval_seconds: int=DEFAULT_INTERVAL, top_n: int=DEFAULT_TOP_N, alert_threshold: float=ALERT_THRESHOLD, db: Optional[DatabaseManager]=None, alerter=None):
        self._interval = interval_seconds
        self._top_n = top_n
        self._alert_threshold = alert_threshold
        self._db = db or get_database()
        self._alerter = alerter
        self._dead_symbols: Set[str] = set()
        self._scanner: Optional[BatchScanner] = None
        self._aggregator: Optional[DataAggregator] = None
        self._generator: Optional[SignalGenerator] = None
        self._tracker: Optional[OITracker] = None
        self._mc_cache: Optional[MarketCapCache] = None
        self._client: Optional[MEXCRestClient] = None
        self._running = False
        self._cycle_count = 0
        self._alerts_generated = 0
        self._start_time: Optional[float] = None
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):

        def handle_shutdown(signum, frame):
            print('\n\n[!] Shutdown signal received. Stopping monitor...')
            self._running = False
        if sys.platform == 'win32':
            signal.signal(signal.SIGINT, handle_shutdown)
            signal.signal(signal.SIGTERM, handle_shutdown)
        else:
            signal.signal(signal.SIGINT, handle_shutdown)
            signal.signal(signal.SIGTERM, handle_shutdown)

    async def run(self, single_symbol: Optional[str]=None):
        self._running = True
        self._start_time = time.time()
        if single_symbol and self._interval == self.DEFAULT_INTERVAL:
            self._interval = self.DEFAULT_SINGLE_INTERVAL
        print('=' * 70)
        print('  OI-HUNTER MONITOR MODE')
        print('=' * 70)
        print(f'  Interval:     {self._interval}s')
        print(f'  Top-N:        {self._top_n}')
        print(f'  Alert Score:  >= {self._alert_threshold}')
        print(f'  Database:     {self._db.db_path}')
        print('=' * 70)
        print('\n  Press Ctrl+C to stop\n')
        async with MEXCRestClient() as client:
            self._client = client
            async with MarketCapCache() as mc_cache:
                self._mc_cache = mc_cache
                print('  Loading market caps from CoinGecko...')
                loaded = await mc_cache.refresh(max_pages=4)
                print(f'  Loaded {loaded} market caps\n')
                async with DataAggregator(client, mc_cache) as aggregator:
                    self._aggregator = aggregator
                    self._generator = SignalGenerator()
                    self._scanner = BatchScanner(client, mc_cache)
                    self._tracker = OITracker(self._db, self._top_n)
                    self._generator.set_database(self._db)
                    if single_symbol:
                        await self._run_single_symbol_mode(single_symbol)
                    else:
                        await self._run_full_scan_mode()
        print('\n' + '=' * 70)
        print('  MONITOR STOPPED')
        print('=' * 70)
        self._print_final_stats()

    async def _run_full_scan_mode(self):
        while self._running:
            cycle_start = time.time()
            self._cycle_count += 1
            print(f"\n{'=' * 70}")
            print(f"  CYCLE #{self._cycle_count} - {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'=' * 70}\n")
            try:
                self._generator.begin_cycle()
                if self._cycle_count == 1:
                    print('  [INIT] First scan — loading all MEXC tokens, takes ~10 min...')
                snapshots = await self._scanner.scan_all(self._aggregator, self._generator, incremental=self._cycle_count > 1)
                print()
                await self._record_oi_snapshots(snapshots)
                alerts = self._check_alerts(snapshots)
                if alerts:
                    self._display_alerts(alerts)
                    if self._alerter:
                        await self._send_telegram_alerts(alerts)
                self._display_watchlist(snapshots)
                self._display_cycle_stats(cycle_start)
                if self._cycle_count % 10 == 0:
                    deleted = self._tracker.cleanup_old_data()
                    if deleted > 0:
                        print(f'\n  [DB] Cleaned up {deleted} old records')
            except Exception as e:
                logger.error(f'Error in monitoring cycle: {e}')
                print(f'\n  [ERROR] Cycle failed: {e}')
            elapsed = time.time() - cycle_start
            wait_time = max(0, self._interval - elapsed)
            if self._running and wait_time > 0:
                print(f'\n  Next scan in {wait_time:.0f}s...')
                await asyncio.sleep(wait_time)

    async def _run_single_symbol_mode(self, symbol: str):
        print(f'\n  [DEBUG MODE] Monitoring single symbol: {symbol}\n')
        while self._running:
            cycle_start = time.time()
            self._cycle_count += 1
            print(f"\n{'-' * 50}")
            print(f"  Cycle #{self._cycle_count} - {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'-' * 50}")
            try:
                self._generator.begin_cycle()
                market_data = await self._aggregator.aggregate(symbol)
                if market_data is None:
                    print(f'  [ERROR] Failed to fetch data for {symbol}')
                    await asyncio.sleep(self._interval)
                    continue
                from ..analyzers.oi_nowcast_analyzer import normalize_symbol
                db_symbol = normalize_symbol(symbol)
                self._tracker.record_single(symbol=db_symbol, oi_usd=market_data.open_interest_usd, price=market_data.price, volume_24h=market_data.volume_24h)
                market_data = self._enrich_oi_changes(market_data, db_symbol)
                analysis = self._generator.analyze_only(market_data)
                signal = self._generator.generate(market_data)
                if signal and self._alerter:
                    await self._alerter.send_signal_alert(signal, market_data)
                self._display_single_symbol_analysis(market_data, analysis, signal)
            except Exception as e:
                logger.error(f'Error analyzing {symbol}: {e}')
                print(f'  [ERROR] {e}')
            elapsed = time.time() - cycle_start
            wait_time = max(0, self._interval - elapsed)
            if self._running and wait_time > 0:
                print(f'\n  Next update in {wait_time:.0f}s...')
                await asyncio.sleep(wait_time)

    def _enrich_oi_changes(self, market_data, db_symbol: str):
        oi_change_1h = self._tracker.get_oi_change_pct(db_symbol, minutes=60)
        oi_change_5m = self._tracker.get_oi_change_pct(db_symbol, minutes=5)
        if oi_change_1h is not None or oi_change_5m is not None:
            market_data = market_data.model_copy(update={'oi_change_1h': oi_change_1h, 'oi_change_5m': oi_change_5m})
        return market_data

    async def _record_oi_snapshots(self, snapshots: List[TokenSnapshot]):
        snapshot_dicts = []
        for snap in snapshots:
            anomaly_score = max(snap.long_score, snap.short_score)
            oi_usd = snap.open_interest_usd
            if oi_usd <= 0:
                continue
            snapshot_dicts.append({'symbol': snap.symbol, 'oi_usd': oi_usd, 'price': snap.price, 'volume_24h': snap.volume_24h, 'anomaly_score': anomaly_score})
        saved = self._tracker.record_snapshots(snapshot_dicts, sort_key='anomaly_score')
        print(f'  [DB] Recorded {saved} OI snapshots')

    async def _send_telegram_alerts(self, alerts: List[TokenSnapshot]):
        from ..analyzers.oi_nowcast_analyzer import normalize_symbol
        from ..api.exceptions import MEXCNotFoundException, MEXCRateLimitException
        for snap in alerts:
            if snap.symbol in self._dead_symbols:
                continue
            if self._alerter.is_on_cooldown(snap.symbol):
                continue
            try:
                market_data = await self._aggregator.aggregate(snap.symbol)
                if market_data is None:
                    continue
                db_symbol = normalize_symbol(snap.symbol)
                market_data = self._enrich_oi_changes(market_data, db_symbol)
                signal = self._generator.generate(market_data)
                if signal:
                    await self._alerter.send_signal_alert(signal, market_data)
            except MEXCNotFoundException as e:
                logger.warning(f'Symbol unavailable, skipping permanently: {snap.symbol} ({e})')
                self._dead_symbols.add(snap.symbol)
            except MEXCRateLimitException as e:
                logger.warning(f'Rate limit hit for {snap.symbol}, will retry next cycle')
            except Exception as e:
                logger.error(f'Failed to send Telegram alert for {snap.symbol}: {e}')

    def _check_alerts(self, snapshots: List[TokenSnapshot]) -> List[TokenSnapshot]:
        fresh = self._scanner.fresh_symbols
        alerts = []
        for snap in snapshots:
            if snap.symbol not in fresh:
                continue
            if 0 < snap.open_interest_usd < self.MIN_ALERT_OI_USD:
                continue
            if snap.long_score >= self._alert_threshold or snap.short_score >= self._alert_threshold:
                alerts.append(snap)
        return alerts

    def _display_alerts(self, alerts: List[TokenSnapshot]):
        print('\n' + '!' * 70)
        print('  ALERTS!')
        print('!' * 70)
        for alert in alerts:
            direction = 'LONG' if alert.long_score > alert.short_score else 'SHORT'
            score = max(alert.long_score, alert.short_score)
            print(f'\n  [{direction}] {alert.symbol}')
            print(f'    Score: {score:.1f}/10')
            print(f'    Price: ${alert.price:,.6f}')
            print(f'    Volume 24h: ${alert.volume_24h:,.0f}')
            self._alerts_generated += 1
        print('\n' + '!' * 70)

    def _display_watchlist(self, snapshots: List[TokenSnapshot]):
        top = self._scanner.get_top_candidates(snapshots, min_score=4.0, limit=10)
        if not top:
            print('\n  [WATCHLIST] No tokens with score >= 4.0')
            return
        print('\n' + '-' * 70)
        print('  WATCHLIST (Top 10)')
        print('-' * 70)
        print(f"  {'Symbol':<15} {'Long':>8} {'Short':>8} {'Price':>12} {'Direction':<8}")
        print('  ' + '-' * 55)
        for snap in top:
            direction = 'LONG' if snap.long_score > snap.short_score else 'SHORT'
            if snap.long_score == snap.short_score:
                direction = 'NEUTRAL'
            print(f'  {snap.symbol:<15} {snap.long_score:>8.1f} {snap.short_score:>8.1f} ${snap.price:>10.4f} {direction:<8}')
        watchlist = self._tracker.watchlist
        print(f'\n  [OI TRACKING] {len(watchlist)} tokens in database')

    def _display_single_symbol_analysis(self, data, analysis: dict, signal=None):
        print(f'\n  Symbol: {data.symbol}')
        print(f'  Price:  ${data.price:,.6f}')
        print(f'  OI:     ${data.open_interest_usd:,.0f}')
        if data.market_cap_usd:
            print(f'  MC:     ${data.market_cap_usd:,.0f}')
            if data.oi_mc_ratio is not None:
                print(f'  OI/MC:  {data.oi_mc_ratio:.4f}')
        if data.funding_rate is not None:
            print(f'  FR:     {data.funding_rate * 100:.4f}%')
        print('\n  Analyzer Results:')
        for r in analysis['results']:
            status = ''
            if r.blocks_long:
                status = ' [BLOCKS LONG]'
            elif r.blocks_short:
                status = ' [BLOCKS SHORT]'
            print(f'    {r.analyzer_name:<25} L={r.long_score:.1f} S={r.short_score:.1f}{status}')
            if 'Nowcast' in r.analyzer_name:
                print(f'      -> {r.reasoning}')
        print(f'\n  Final Scores:')
        print(f"    Long:  {analysis['long_score']}/10")
        print(f"    Short: {analysis['short_score']}/10")
        if signal:
            print(f'    Signal: {signal.direction}  {signal.overall_score:.1f}/10')
            print(f'    Entry:     ${signal.entry_price:.6f}')
            print(f'    Stop Loss: ${signal.stop_loss:.6f}')
            if signal.targets and len(signal.targets) >= 3:
                print(f'    Target 1:  ${signal.targets[0].target_price:.6f}')
                print(f'    Target 2:  ${signal.targets[1].target_price:.6f}')
                print(f'    Target 3:  ${signal.targets[2].target_price:.6f}')
        else:
            print(f"    Signal: {analysis['would_signal']}")
        stats = self._tracker.get_stats()
        print(f"\n  [DB] Records: {stats['total_records']}, Tracked: {stats['tracked_symbols']}")

    def _display_cycle_stats(self, cycle_start: float):
        elapsed = time.time() - cycle_start
        uptime = time.time() - self._start_time
        scanner_stats = self._scanner.get_stats()
        tracker_stats = self._tracker.get_stats()
        print('\n' + '-' * 70)
        print('  STATS')
        print('-' * 70)
        print(f'  Cycle Time:     {elapsed:.1f}s')
        print(f'  Uptime:         {uptime / 60:.1f} min')
        print(f'  Cycles:         {self._cycle_count}')
        print(f'  Alerts:         {self._alerts_generated}')
        print(f"  Tokens Scanned: {scanner_stats['total_tokens']}")
        print(f"  Tokens Changed: {scanner_stats['tokens_changed']}")
        print(f"  DB Records:     {tracker_stats['total_records']}")
        print(f"  OI Tracked:     {tracker_stats['tracked_symbols']} symbols")
        if self._alerter:
            self._alerter.update_monitor_status(tracker_stats['tracked_symbols'])

    def _print_final_stats(self):
        if self._start_time:
            uptime = time.time() - self._start_time
            print(f'  Total Uptime:   {uptime / 60:.1f} minutes')
        print(f'  Total Cycles:   {self._cycle_count}')
        print(f'  Total Alerts:   {self._alerts_generated}')
        if self._tracker:
            stats = self._tracker.get_stats()
            print(f"  DB Records:     {stats['total_records']}")
        print('=' * 70)

async def run_monitor(interval: int=60, single_symbol: Optional[str]=None):
    monitor = Monitor(interval_seconds=interval)
    await monitor.run(single_symbol=single_symbol)
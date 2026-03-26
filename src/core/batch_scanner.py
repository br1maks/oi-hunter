import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, asdict
logger = logging.getLogger(__name__)
from ..api.mexc_client import MEXCRestClient
from ..api.config import MEXCConfig
from ..data.data_aggregator import DataAggregator
from ..data.market_cap_cache import MarketCapCache
from ..models.market_data import MarketData
from .signal_generator import SignalGenerator

@dataclass
class TokenSnapshot:
    symbol: str
    price: float
    oi_contracts: float
    volume_24h: float
    timestamp: float
    long_score: float
    short_score: float
    open_interest_usd: float = 0.0
    funding_rate: float = 0.0

    def has_changed(self, current: 'TokenSnapshot', threshold: Dict[str, float]) -> bool:
        if self.price > 0:
            price_change = abs(current.price - self.price) / self.price
            if price_change > threshold.get('price', 0.03):
                return True
        if self.oi_contracts > 0:
            oi_change = abs(current.oi_contracts - self.oi_contracts) / self.oi_contracts
            if oi_change > threshold.get('oi', 0.05):
                return True
        if self.volume_24h > 0:
            volume_change = abs(current.volume_24h - self.volume_24h) / self.volume_24h
            if volume_change > threshold.get('volume', 0.5):
                return True
        funding_change = abs(current.funding_rate - self.funding_rate)
        if funding_change > threshold.get('funding', 0.0005):
            return True
        return False

class BatchScanner:
    DEFAULT_THRESHOLDS = {'price': 0.03, 'oi': 0.05, 'volume': 0.5, 'funding': 0.0005}
    BATCH_SIZE = 20
    SNAPSHOT_BATCH = 20
    FORCE_RESCAN_SCORE = 6.5

    def __init__(self, mexc_client: Optional[MEXCRestClient]=None, mc_cache: Optional[MarketCapCache]=None, change_thresholds: Optional[Dict[str, float]]=None):
        self._mexc_client = mexc_client
        self._mc_cache = mc_cache
        self._thresholds = change_thresholds or self.DEFAULT_THRESHOLDS
        self._previous_snapshots: Dict[str, TokenSnapshot] = {}
        self._fresh_symbols: Set[str] = set()
        self._stats = {'total_scans': 0, 'total_tokens': 0, 'tokens_changed': 0, 'tokens_unchanged': 0, 'scan_time': 0.0}

    @property
    def fresh_symbols(self) -> Set[str]:
        return self._fresh_symbols

    async def get_all_mexc_futures(self) -> List[str]:
        if not self._mexc_client:
            raise RuntimeError('MEXC client not initialized')
        url = f'{MEXCConfig.FUTURES_BASE_URL}/api/v1/contract/detail'
        response = await self._mexc_client._request('GET', url)
        if not response.get('success'):
            raise RuntimeError('Failed to fetch MEXC futures list')
        contracts = response.get('data', [])
        usdt_futures = [c['symbol'] for c in contracts if c['symbol'].endswith('_USDT')]
        return usdt_futures

    async def create_snapshots(self, symbols: List[str]) -> Dict[str, TokenSnapshot]:
        snapshots = {}
        for i in range(0, len(symbols), self.SNAPSHOT_BATCH):
            batch = symbols[i:i + self.SNAPSHOT_BATCH]
            tasks = [self._fetch_ticker_snapshot(symbol) for symbol in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for symbol, result in zip(batch, results):
                if not isinstance(result, Exception) and result:
                    snapshots[symbol] = result
        return snapshots

    async def _fetch_ticker_snapshot(self, symbol: str) -> Optional[TokenSnapshot]:
        try:
            url = f'{MEXCConfig.FUTURES_BASE_URL}/api/v1/contract/ticker'
            response = await self._mexc_client._request('GET', url, {'symbol': symbol})
            if not response.get('success'):
                return None
            data = response.get('data', {})
            return TokenSnapshot(symbol=symbol, price=float(data.get('lastPrice') or 0), oi_contracts=float(data.get('holdVol') or 0), volume_24h=float(data.get('amount24') or 0), timestamp=time.time(), long_score=0.0, short_score=0.0, funding_rate=float(data.get('fundingRate') or 0))
        except Exception as e:
            logger.debug(f'Failed to fetch ticker snapshot for {symbol}: {e}')
            return None

    async def detect_changes(self, current_snapshots: Dict[str, TokenSnapshot]) -> Tuple[List[str], List[TokenSnapshot]]:
        changed = []
        unchanged = []
        for symbol, current in current_snapshots.items():
            previous = self._previous_snapshots.get(symbol)
            if previous is None:
                changed.append(symbol)
            elif previous.has_changed(current, self._thresholds):
                changed.append(symbol)
            else:
                unchanged.append(previous)
        return (changed, unchanged)

    async def scan_token(self, symbol: str, aggregator: DataAggregator, generator: SignalGenerator) -> Optional[TokenSnapshot]:
        try:
            market_data = await aggregator.aggregate(symbol)
            analysis = generator.analyze_only(market_data)
            return TokenSnapshot(symbol=symbol, price=market_data.price, oi_contracts=market_data.open_interest_usd / market_data.price if market_data.price > 0 else 0, volume_24h=market_data.volume_24h, timestamp=time.time(), long_score=analysis['long_score'], short_score=analysis['short_score'], open_interest_usd=market_data.open_interest_usd, funding_rate=market_data.funding_rate)
        except Exception as e:
            logger.warning(f'Error scanning {symbol}: {e}')
            return None

    async def scan_tokens_parallel(self, symbols: List[str], aggregator: DataAggregator, generator: SignalGenerator) -> List[TokenSnapshot]:
        results = []
        total = len(symbols)
        for i in range(0, total, self.BATCH_SIZE):
            batch = symbols[i:i + self.BATCH_SIZE]
            tasks = [self.scan_token(symbol, aggregator, generator) for symbol in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in batch_results:
                if isinstance(result, TokenSnapshot):
                    results.append(result)
            done = min(i + self.BATCH_SIZE, total)
            print(f'  Scanning... {done}/{total} tokens', end='\r', flush=True)
        return results

    async def scan_all(self, aggregator: DataAggregator, generator: SignalGenerator, incremental: bool=True) -> List[TokenSnapshot]:
        start_time = time.time()
        print('📊 Fetching MEXC futures list...')
        logger.info('Fetching MEXC futures list...')
        all_symbols = await self.get_all_mexc_futures()
        print(f'   Found {len(all_symbols)} USDT perpetual futures')
        logger.info(f'Found {len(all_symbols)} USDT perpetual futures')
        if incremental and self._previous_snapshots:
            print('📸 Creating snapshots (incremental)...')
            logger.info('Creating snapshots (incremental)...')
            current_snapshots = await self.create_snapshots(all_symbols)
            print(f'   Created {len(current_snapshots)} snapshots')
            print('🔍 Detecting changes...')
            changed_symbols, unchanged_snapshots = await self.detect_changes(current_snapshots)
            force_rescan = [sym for sym, snap in self._previous_snapshots.items() if max(snap.long_score, snap.short_score) >= self.FORCE_RESCAN_SCORE and sym not in changed_symbols]
            if force_rescan:
                print(f'   Force-rescanning {len(force_rescan)} high-score tokens...')
                logger.info(f'Force-rescanning {len(force_rescan)} high-score tokens: {force_rescan}')
                changed_symbols = changed_symbols + force_rescan
                force_rescan_set = set(force_rescan)
                unchanged_snapshots = [s for s in unchanged_snapshots if s.symbol not in force_rescan_set]
            print(f'   Changed: {len(changed_symbols)}, Unchanged: {len(unchanged_snapshots)}')
            logger.info(f'Changed: {len(changed_symbols)}, Unchanged: {len(unchanged_snapshots)}')
            print(f'⚡ Scanning {len(changed_symbols)} changed tokens...')
            new_results = await self.scan_tokens_parallel(changed_symbols, aggregator, generator)
            all_results = new_results + unchanged_snapshots
            self._fresh_symbols = {r.symbol for r in new_results}
            self._stats['tokens_changed'] = len(changed_symbols)
            self._stats['tokens_unchanged'] = len(unchanged_snapshots)
        else:
            print(f'🔄 Full scan of {len(all_symbols)} tokens...')
            logger.info(f'Full scan of {len(all_symbols)} tokens...')
            all_results = await self.scan_tokens_parallel(all_symbols, aggregator, generator)
            self._fresh_symbols = {r.symbol for r in all_results}
            self._stats['tokens_changed'] = len(all_symbols)
            self._stats['tokens_unchanged'] = 0
        self._previous_snapshots = {snapshot.symbol: snapshot for snapshot in all_results}
        elapsed = time.time() - start_time
        self._stats['total_scans'] += 1
        self._stats['total_tokens'] = len(all_results)
        self._stats['scan_time'] = elapsed
        print(f'\n✅ Scan completed in {elapsed:.1f}s')
        print(f'   Total tokens: {len(all_results)}')
        print(f"   Changed: {self._stats['tokens_changed']}")
        print(f"   Unchanged: {self._stats['tokens_unchanged']}")
        logger.info(f"Scan completed in {elapsed:.1f}s: {len(all_results)} tokens, {self._stats['tokens_changed']} changed")
        return all_results

    def get_top_candidates(self, snapshots: List[TokenSnapshot], min_score: float=5.0, limit: int=50) -> List[TokenSnapshot]:
        candidates = [s for s in snapshots if s.long_score >= min_score or s.short_score >= min_score]
        candidates.sort(key=lambda x: max(x.long_score, x.short_score), reverse=True)
        return candidates[:limit]

    def get_stats(self) -> Dict:
        return self._stats.copy()
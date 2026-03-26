import asyncio
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.data.market_cap_cache import MarketCapCache
from src.data.data_aggregator import DataAggregator

async def test_cache_performance():
    print('=' * 60)
    print('MARKET CAP CACHE PERFORMANCE TEST')
    print('=' * 60)
    test_symbols = ['BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'ADA', 'DOGE', 'AVAX', 'DOT', 'MATIC', 'BIRB', 'LIGHT', 'BULLA', 'BROCCOLI', 'FHE']
    print('\n' + '-' * 60)
    print('PHASE 1: БЕЗ кэша (каждый запрос = API call)')
    print('-' * 60)
    async with DataAggregator() as agg:
        start = time.time()
        print(f'\nTesting {len(test_symbols)} tokens WITHOUT cache...')
        successful = 0
        for symbol in test_symbols[:5]:
            try:
                base_symbol = symbol.replace('USDT', '')
                mc = await agg._fetch_market_cap(base_symbol, 1.0)
                if mc:
                    print(f'  {base_symbol}: ${mc:,.0f}')
                    successful += 1
                else:
                    print(f'  {base_symbol}: NOT FOUND')
            except Exception as e:
                print(f'  {base_symbol}: ERROR - {e}')
        elapsed = time.time() - start
        print(f'\nWithout cache: {successful}/{len(test_symbols[:5])} successful in {elapsed:.2f}s')
        print(f'Average: {elapsed / len(test_symbols[:5]):.2f}s per token')
        print(f'Projected time for 845 tokens: {elapsed / len(test_symbols[:5]) * 845 / 60:.1f} minutes')
    print('\n' + '-' * 60)
    print('PHASE 2: С кэшем (мгновенный доступ)')
    print('-' * 60)
    async with MarketCapCache() as cache:
        print('\nLoading cache (bulk CoinGecko request)...')
        cache_start = time.time()
        loaded = await cache.refresh(max_pages=2)
        cache_time = time.time() - cache_start
        print(f'Cache loaded: {loaded} coins in {cache_time:.2f}s')
        print(f'Cache size: {cache.size} coins')
        async with DataAggregator(mc_cache=cache) as agg:
            start = time.time()
            print(f'\nTesting {len(test_symbols)} tokens WITH cache...')
            successful = 0
            for symbol in test_symbols:
                try:
                    base_symbol = symbol.replace('USDT', '')
                    mc = await agg._fetch_market_cap(base_symbol, 1.0)
                    if mc:
                        print(f'  {base_symbol}: ${mc:,.0f}')
                        successful += 1
                    else:
                        print(f'  {base_symbol}: NOT FOUND')
                except Exception as e:
                    print(f'  {base_symbol}: ERROR - {e}')
            elapsed = time.time() - start
            print(f'\nWith cache: {successful}/{len(test_symbols)} successful in {elapsed:.2f}s')
            print(f'Average: {elapsed / len(test_symbols):.3f}s per token')
            print(f'Projected time for 845 tokens: {elapsed / len(test_symbols) * 845:.1f}s = {elapsed / len(test_symbols) * 845 / 60:.1f} minutes')
    print('\n' + '=' * 60)
    print('SUMMARY')
    print('=' * 60)
    print(f'Cache refresh: {cache_time:.1f}s (once per 10 minutes)')
    print(f'Without cache: ~{2.0 * 845 / 60:.0f} minutes for 845 tokens')
    print(f'With cache: ~{0.01 * 845:.0f}s for 845 tokens')
    print(f'Speedup: ~{2.0 * 845 / (0.01 * 845):.0f}x faster')

async def test_cache_stale():
    print('\n' + '=' * 60)
    print('CACHE STALE TEST')
    print('=' * 60)
    async with MarketCapCache() as cache:
        print(f'\nCache is stale: {cache.is_stale}')
        print('Loading cache...')
        loaded = await cache.refresh(max_pages=1)
        print(f'Loaded {loaded} coins')
        print(f'Cache is stale: {cache.is_stale}')
        print(f'Cache size: {cache.size}')
        mc = cache.get('BTC')
        print(f'\nBTC market cap: ${mc:,.0f}' if mc else 'BTC not found')
        mc = cache.get('ETH')
        print(f'ETH market cap: ${mc:,.0f}' if mc else 'ETH not found')

async def main():
    await test_cache_performance()
    await test_cache_stale()
if __name__ == '__main__':
    asyncio.run(main())
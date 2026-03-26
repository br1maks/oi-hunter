"""
Test Batch Scanner - демонстрирует incremental scanning

Показывает:
1. Первый полный скан (all tokens)
2. Второй incremental скан (only changed tokens)
3. Топ-50 кандидатов для Watch List
"""



import asyncio

import sys

from pathlib import Path



sys.path.insert(0, str(Path(__file__).parent.parent))



from src.api.mexc_client import MEXCRestClient

from src.data.data_aggregator import DataAggregator

from src.data.market_cap_cache import MarketCapCache

from src.core.signal_generator import SignalGenerator

from src.core.batch_scanner import BatchScanner





async def test_batch_scanner():

    """Тестирует Batch Scanner с incremental scanning."""

    print("="*60)

    print("BATCH SCANNER TEST - Incremental Scanning")

    print("="*60)



                   

    print("\nInitializing...")

    async with MEXCRestClient() as mexc_client,
               MarketCapCache() as mc_cache,
               DataAggregator(mexc_client=mexc_client, mc_cache=mc_cache) as aggregator:



                          

        print("Loading Market Cap cache...")

        loaded = await mc_cache.refresh(max_pages=4)

        print(f"  Loaded {loaded} coins in cache")



                         

        scanner = BatchScanner(

            mexc_client=mexc_client,

            mc_cache=mc_cache,

        )



        generator = SignalGenerator()



                            

        print("\n" + "="*60)

        print("SCAN #1: Full Scan (первый запуск)")

        print("="*60)



        snapshots_1 = await scanner.scan_all(

            aggregator=aggregator,

            generator=generator,

            incremental=True,                            

        )



                

        top_50_1 = scanner.get_top_candidates(snapshots_1, min_score=5.0, limit=50)



        print(f"\n{'─'*60}")

        print(f"TOP-50 CANDIDATES (SCAN #1):")

        print(f"{'─'*60}")

        for i, snapshot in enumerate(top_50_1[:10], 1):                     

            max_score = max(snapshot.long_score, snapshot.short_score)

            direction = "LONG" if snapshot.long_score > snapshot.short_score else "SHORT"

            print(f"{i:2}. {snapshot.symbol:15} | {direction:5} Score: {max_score:.1f} | "

                  f"Price: ${snapshot.price:.6f} | Vol: ${snapshot.volume_24h:,.0f}")



                               

        stats_1 = scanner.get_stats()

        print(f"\n{'─'*60}")

        print("STATS (SCAN #1):")

        print(f"{'─'*60}")

        print(f"Total tokens: {stats_1['total_tokens']}")

        print(f"Changed: {stats_1['tokens_changed']}")

        print(f"Unchanged: {stats_1['tokens_unchanged']}")

        print(f"Scan time: {stats_1['scan_time']:.1f}s")



                                                  

        print("\n" + "="*60)

        print("Waiting 10 seconds before next scan...")

        print("="*60)

        await asyncio.sleep(10)



                                   

        print("\n" + "="*60)

        print("SCAN #2: Incremental Scan (только изменившиеся)")

        print("="*60)



        snapshots_2 = await scanner.scan_all(

            aggregator=aggregator,

            generator=generator,

            incremental=True,                            

        )



                

        top_50_2 = scanner.get_top_candidates(snapshots_2, min_score=5.0, limit=50)



        print(f"\n{'─'*60}")

        print(f"TOP-50 CANDIDATES (SCAN #2):")

        print(f"{'─'*60}")

        for i, snapshot in enumerate(top_50_2[:10], 1):

            max_score = max(snapshot.long_score, snapshot.short_score)

            direction = "LONG" if snapshot.long_score > snapshot.short_score else "SHORT"

            print(f"{i:2}. {snapshot.symbol:15} | {direction:5} Score: {max_score:.1f} | "

                  f"Price: ${snapshot.price:.6f} | Vol: ${snapshot.volume_24h:,.0f}")



                               

        stats_2 = scanner.get_stats()

        print(f"\n{'─'*60}")

        print("STATS (SCAN #2):")

        print(f"{'─'*60}")

        print(f"Total tokens: {stats_2['total_tokens']}")

        print(f"Changed: {stats_2['tokens_changed']}")

        print(f"Unchanged: {stats_2['tokens_unchanged']}")

        print(f"Scan time: {stats_2['scan_time']:.1f}s")



                   

        print(f"\n{'='*60}")

        print("COMPARISON:")

        print(f"{'='*60}")

        print(f"Scan #1 (Full):        {stats_1['scan_time']:.1f}s")

        print(f"Scan #2 (Incremental): {stats_2['scan_time']:.1f}s")

        print(f"Speedup:               {stats_1['scan_time'] / stats_2['scan_time']:.1f}x faster")

        print(f"\nTokens rescanned: {stats_2['tokens_changed']} "

              f"({stats_2['tokens_changed'] / stats_2['total_tokens'] * 100:.1f}%)")



                                

        symbols_1 = {s.symbol for s in top_50_1}

        symbols_2 = {s.symbol for s in top_50_2}



        added = symbols_2 - symbols_1

        removed = symbols_1 - symbols_2



        print(f"\n{'─'*60}")

        print("WATCH LIST CHANGES:")

        print(f"{'─'*60}")

        print(f"Added tokens: {len(added)}")

        if added:

            print(f"  {', '.join(list(added)[:5])}")

        print(f"Removed tokens: {len(removed)}")

        if removed:

            print(f"  {', '.join(list(removed)[:5])}")





async def quick_test():

    """Быстрый тест на малом количестве токенов."""

    print("="*60)

    print("QUICK TEST - First 20 tokens")

    print("="*60)



    async with MEXCRestClient() as mexc_client,
               MarketCapCache() as mc_cache,
               DataAggregator(mexc_client=mexc_client, mc_cache=mc_cache) as aggregator:



                          

        print("Loading Market Cap cache...")

        await mc_cache.refresh(max_pages=2)



        scanner = BatchScanner(mexc_client=mexc_client, mc_cache=mc_cache)

        generator = SignalGenerator()



                                           

        all_symbols = await scanner.get_all_mexc_futures()

        test_symbols = all_symbols[:20]



        print(f"\nTesting with {len(test_symbols)} tokens...")

        print(f"Symbols: {', '.join(test_symbols[:5])}...")



                   

        snapshots = []

        for symbol in test_symbols:

            snapshot = await scanner.scan_token(symbol, aggregator, generator)

            if snapshot:

                snapshots.append(snapshot)

                max_score = max(snapshot.long_score, snapshot.short_score)

                direction = "LONG" if snapshot.long_score > snapshot.short_score else "SHORT"

                print(f"  {symbol:15} | {direction:5} | Score: {max_score:.1f}")



        print(f"\nScanned {len(snapshots)}/{len(test_symbols)} tokens successfully")





if __name__ == "__main__":

    import sys



    if len(sys.argv) > 1 and sys.argv[1] == "quick":

        asyncio.run(quick_test())

    else:

        asyncio.run(test_batch_scanner())


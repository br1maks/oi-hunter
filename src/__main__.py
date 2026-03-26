"""
OI-Hunter CLI - Command Line Interface

Usage:
    python -m src analyze BTCUSDT
    python -m src scan
    python -m src scan --top 20
    python -m src monitor
    python -m src monitor --interval 30
"""



import asyncio

import argparse

import sys

from pathlib import Path



                          

project_root = Path(__file__).parent.parent

sys.path.insert(0, str(project_root))



from dotenv import load_dotenv



from src.api.mexc_client import MEXCRestClient

from src.data.data_aggregator import DataAggregator

from src.data.market_cap_cache import MarketCapCache

from src.core.signal_generator import SignalGenerator

from src.core.batch_scanner import BatchScanner

from src.core.monitor import Monitor, run_monitor





def print_banner():

    """Печатает красивый banner"""

    print("=" * 70)

    print("  ___  ___       _   _             _            ")

    print(" / _ \\|_ _|     | | | |_   _ _ __ | |_ ___ _ __ ")

    print("| | | || |_____ | |_| | | | | '_ \\| __/ _ \\ '__|")

    print("| |_| || |_____|  _  | |_| | | | | ||  __/ |   ")

    print(" \\___/|___|     |_| |_|\\__,_|_| |_|\\__\\___|_|   ")

    print()

    print("  Open Interest Hunter - Smart Trading Signals")

    print("=" * 70)





async def cmd_analyze(args):

    """Анализирует один токен"""

    symbol = args.symbol.upper()



    print(f"\n[INFO] Analyzing {symbol}...")



    async with MEXCRestClient() as mexc_client,
               MarketCapCache() as mc_cache:



                                                                    

                                                                         

        print("[INFO] Loading market cap cache...")

        loaded = await mc_cache.refresh(max_pages=1)

        print(f"[OK] Cached {loaded} coins")



                                         

        async with DataAggregator(mexc_client=mexc_client, mc_cache=mc_cache) as aggregator:

            generator = SignalGenerator()



            try:

                              

                print(f"[INFO] Fetching data for {symbol}...")

                market_data = await aggregator.aggregate(symbol)



                                                                     

                analysis = generator.analyze_only(market_data)

                signal = generator.generate(market_data)



                               

                print("\n" + "=" * 70)

                print(f"ANALYSIS RESULTS: {symbol}")

                print("=" * 70)



                             

                print("\n[MARKET DATA]")

                print(f"  Price:            ${market_data.price:,.4f}")

                print(f"  Volume 24h:       ${market_data.volume_24h:,.0f}")

                print(f"  Open Interest:    ${market_data.open_interest_usd:,.0f}")



                if market_data.market_cap_usd:

                    print(f"  Market Cap:       ${market_data.market_cap_usd:,.0f}")

                    if market_data.oi_mc_ratio is not None:

                        print(f"  OI/MC Ratio:      {market_data.oi_mc_ratio:.4f}")

                else:

                    print(f"  Market Cap:       Not found")



                print(f"  Funding Rate:     {market_data.funding_rate * 100:.4f}%")



                if market_data.price_change_24h:

                    print(f"  Price Change 24h: {market_data.price_change_24h:+.2f}%")



                            

                if market_data.aggression_2h is not None:

                    print(f"  Aggression 2h:    {market_data.aggression_2h:.1f}% buy")

                if market_data.aggression_5m is not None:

                    print(f"  Aggression 5m:    {market_data.aggression_5m:.1f}% buy")



                                        

                print("\n[ANALYZERS]")

                for r in analysis['results']:

                    status = ""

                    if r.blocks_long:

                        status = " [BLOCKS LONG]"

                    elif r.blocks_short:

                        status = " [BLOCKS SHORT]"

                    print(f"  {r.analyzer_name:<28} L={r.long_score:.1f}  S={r.short_score:.1f}{status}")

                    if r.analyzer_name == "OI Nowcast" and r.reasoning:

                        print(f"    -> {r.reasoning}")



                        

                print("\n[SCORES]")

                print(f"  Long Score:  {analysis['long_score']:.1f}/10")

                print(f"  Short Score: {analysis['short_score']:.1f}/10")

                print(f"  Analyzers:   {analysis['analyzers_count']}")



                                

                if analysis['blocks_long']:

                    print(f"\n  [BLOCKED] LONGS BLOCKED")

                if analysis['blocks_short']:

                    print(f"\n  [CONFIRMS LONG] SHORTS BLOCKED")



                        

                print("\n[SIGNAL]")

                if signal:

                    direction = signal.direction

                    print(f"  Direction:  {direction}")

                    print(f"  Score:      {signal.overall_score:.1f}/10")

                    print(f"  Entry:      ${signal.entry_price:.6f}")

                    print(f"  Stop Loss:  ${signal.stop_loss:.6f}")

                    if signal.targets and len(signal.targets) >= 3:

                        print(f"  Target 1:   ${signal.targets[0].target_price:.6f}")

                        print(f"  Target 2:   ${signal.targets[1].target_price:.6f}")

                        print(f"  Target 3:   ${signal.targets[2].target_price:.6f}")

                else:

                    reason = ""

                    if analysis['blocks_long'] and analysis['long_score'] >= 7.0:

                        reason = " (LONGS BLOCKED)"

                    elif analysis['blocks_short'] and analysis['short_score'] >= 7.0:

                        reason = " (SHORTS BLOCKED)"

                    elif analysis['analyzers_count'] < 2:

                        reason = " (too few analyzers)"

                    print(f"  NO SIGNAL{reason}")



                print("\n" + "=" * 70)



            except ValueError as e:

                print(f"\n[ERROR] Failed to analyze {symbol}: {e}")

                return 1

            except Exception as e:

                print(f"\n[ERROR] Unexpected error: {e}")

                return 1



    return 0





async def cmd_scan(args):

    """Сканирует все токены MEXC"""

    top = args.top



    print(f"\n[INFO] Scanning all MEXC futures...")

    if top:

        print(f"[INFO] Will show top {top} candidates")



    async with MEXCRestClient() as mexc_client,
               MarketCapCache() as mc_cache:



                                                                          

        print("\n[INFO] Loading market cap cache...")

        loaded = await mc_cache.refresh(max_pages=5)

        print(f"[OK] Cached {loaded} coins")



                           

        scanner = BatchScanner(mexc_client=mexc_client, mc_cache=mc_cache)

        async with DataAggregator(mexc_client=mexc_client, mc_cache=mc_cache) as aggregator:

            generator = SignalGenerator()



            try:

                                 

                print("\n" + "=" * 70)

                results = await scanner.scan_all(aggregator, generator, incremental=False)

                print("=" * 70)



                                    

                candidates = scanner.get_top_candidates(

                    results,

                    min_score=5.0,

                    limit=top if top else 50

                )



                               

                print(f"\n[RESULTS] Found {len(candidates)} candidates")

                print("\n" + "=" * 70)

                print(f"{'Rank':<6} {'Symbol':<15} {'Long':<8} {'Short':<8} {'Max Score':<10}")

                print("=" * 70)



                for i, snapshot in enumerate(candidates, 1):

                    max_score = max(snapshot.long_score, snapshot.short_score)

                    print(f"{i:<6} {snapshot.symbol:<15} {snapshot.long_score:<8.1f} {snapshot.short_score:<8.1f} {max_score:<10.1f}")



                print("=" * 70)



                       

                stats = scanner.get_stats()

                print(f"\n[STATS]")

                print(f"  Total tokens scanned: {stats['total_tokens']}")

                print(f"  Scan time:            {stats['scan_time']:.1f}s")

                print(f"  Candidates found:     {len(candidates)}")



                                 

                if candidates:

                    print(f"\n[RECOMMENDATION]")

                    top3 = candidates[:3]

                    print(f"  Analyze these tokens:")

                    for snapshot in top3:

                        direction = "LONG" if snapshot.long_score > snapshot.short_score else "SHORT"

                        score = max(snapshot.long_score, snapshot.short_score)

                        print(f"    python -m src analyze {snapshot.symbol} (Score: {score:.1f}, {direction})")



                print()



            except Exception as e:

                print(f"\n[ERROR] Scan failed: {e}")

                return 1



    return 0





async def cmd_monitor(args):

    """Runs continuous 24/7 monitoring mode"""

    print("\n[INFO] Starting Monitor Mode...")

    print(f"[INFO] Interval: {args.interval}s")



    if args.symbol:

        print(f"[INFO] Debug mode: monitoring single symbol {args.symbol}")



    try:

        await run_monitor(

            interval=args.interval,

            single_symbol=args.symbol

        )

        return 0

    except KeyboardInterrupt:

        print("\n[INFO] Monitor stopped by user")

        return 0

    except Exception as e:

        print(f"\n[ERROR] Monitor failed: {e}")

        return 1





async def cmd_bot(args):

    """Запускает Telegram бот + монитор вместе."""

    load_dotenv()



    from src.bot.telegram_bot import create_bot_from_env

    from src.bot.alerter import Alerter



    print("\n[INFO] Loading .env...")

    bot = create_bot_from_env()

    alerter = Alerter(bot)



    try:

        print("[INFO] Starting Telegram bot...")

        await bot.start()

        print("[OK] Bot is running. Send /start to your bot to register chat_id.\n")



        monitor = Monitor(

            interval_seconds=args.interval,

            alerter=alerter,

        )

        monitor_task = asyncio.create_task(monitor.run(single_symbol=args.symbol))

        bot.set_monitor_status(running=True)



        try:

            await monitor_task

        except (asyncio.CancelledError, KeyboardInterrupt):

            pass



    finally:

        bot.set_monitor_status(running=False)

        await bot.stop()

        print("[INFO] Bot stopped.")



    return 0





def main():

    """Main CLI entry point"""

    parser = argparse.ArgumentParser(

        description="OI-Hunter - Smart Trading Signals based on Open Interest Analysis",

        formatter_class=argparse.RawDescriptionHelpFormatter,

        epilog="""
Examples:
  python -m src analyze BTCUSDT          Analyze a single token
  python -m src scan                     Scan all tokens
  python -m src scan --top 20            Show top 20 candidates
  python -m src monitor                  Run 24/7 monitoring mode
  python -m src monitor --interval 30    Monitor with 30s interval
  python -m src monitor --symbol BTC_USDT  Monitor single symbol (debug)
        """

    )



    subparsers = parser.add_subparsers(dest='command', help='Available commands')



                     

    analyze_parser = subparsers.add_parser('analyze', help='Analyze a single token')

    analyze_parser.add_argument('symbol', type=str, help='Token symbol (e.g., BTCUSDT)')



                  

    scan_parser = subparsers.add_parser('scan', help='Scan all MEXC tokens')

    scan_parser.add_argument('--top', type=int, default=None, help='Show top N candidates (default: 50)')



                     

    monitor_parser = subparsers.add_parser('monitor', help='Run continuous 24/7 monitoring')

    monitor_parser.add_argument('--interval', type=int, default=60, help='Seconds between scans (default: 60)')

    monitor_parser.add_argument('--symbol', type=str, default=None, help='Monitor single symbol (debug mode)')



                 

    bot_parser = subparsers.add_parser('bot', help='Run Telegram bot + monitor together')

    bot_parser.add_argument('--interval', type=int, default=60, help='Seconds between scans (default: 60)')

    bot_parser.add_argument('--symbol', type=str, default=None, help='Monitor single symbol (debug mode)')



    args = parser.parse_args()



                 

    print_banner()



                     

    if not args.command:

        parser.print_help()

        return 0



    if args.command == 'analyze':

        return asyncio.run(cmd_analyze(args))

    elif args.command == 'scan':

        return asyncio.run(cmd_scan(args))

    elif args.command == 'monitor':

        return asyncio.run(cmd_monitor(args))

    elif args.command == 'bot':

        return asyncio.run(cmd_bot(args))

    else:

        print(f"Unknown command: {args.command}")

        return 1





if __name__ == "__main__":

    sys.exit(main())


import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.data.data_aggregator import DataAggregator
from src.core.signal_generator import SignalGenerator

async def test_aggregator(symbol: str):
    print(f"\n{'=' * 60}")
    print(f'Testing DataAggregator for: {symbol}')
    print(f"{'=' * 60}\n")
    async with DataAggregator() as aggregator:
        try:
            print('Fetching data from APIs...')
            market_data = await aggregator.aggregate(symbol)
            print(f"\n{'-' * 40}")
            print('MARKET DATA COLLECTED:')
            print(f"{'-' * 40}")
            print(f'Symbol: {market_data.symbol}')
            print(f'Price: ${market_data.price:.6f}')
            print(f'Market Cap: ${market_data.market_cap_usd:,.0f}')
            print(f'Open Interest: ${market_data.open_interest_usd:,.0f}')
            print(f'OI/MC Ratio: {market_data.oi_mc_ratio:.4f}')
            print(f'Funding Rate: {market_data.funding_rate:.6f} ({market_data.funding_rate * 100:.4f}%)')
            print(f"\n{'-' * 40}")
            print('VOLUME DATA:')
            print(f"{'-' * 40}")
            print(f'Volume 24h: ${market_data.volume_24h:,.0f}')
            print(f'Volume 1h: ${market_data.volume_1h:,.0f}' if market_data.volume_1h else 'Volume 1h: N/A')
            print(f'Avg Volume 1h: ${market_data.avg_volume_1h:,.0f}' if market_data.avg_volume_1h else 'Avg Volume 1h: N/A')
            if market_data.volume_1h and market_data.avg_volume_1h and (market_data.avg_volume_1h > 0):
                ratio = market_data.volume_1h / market_data.avg_volume_1h
                print(f'Volume Ratio: {ratio:.2f}x')
            print(f"\n{'-' * 40}")
            print('PRICE CHANGES:')
            print(f"{'-' * 40}")
            print(f'Price Change 1h: {market_data.price_change_1h:+.2f}%' if market_data.price_change_1h else 'Price Change 1h: N/A')
            print(f'Price Change 4h: {market_data.price_change_4h:+.2f}%' if market_data.price_change_4h else 'Price Change 4h: N/A')
            print(f'Price Change 24h: {market_data.price_change_24h:+.2f}%' if market_data.price_change_24h else 'Price Change 24h: N/A')
            print(f'ATR: ${market_data.atr:.6f}' if market_data.atr else 'ATR: N/A')
            print(f"\n{'-' * 40}")
            print('AGGRESSION DATA:')
            print(f"{'-' * 40}")
            if market_data.aggression_2h is not None:
                print(f'Aggression 2h: {market_data.aggression_2h:.1f}%')
            else:
                print('Aggression 2h: N/A')
            if market_data.aggression_5m is not None:
                print(f'Aggression 5m: {market_data.aggression_5m:.1f}%')
            else:
                print('Aggression 5m: N/A')
            if market_data.buy_volume_2h and market_data.sell_volume_2h:
                print(f'Buy Volume 2h: ${market_data.buy_volume_2h:,.0f}')
                print(f'Sell Volume 2h: ${market_data.sell_volume_2h:,.0f}')
            print(f"\n{'-' * 40}")
            print('SIGNAL GENERATOR ANALYSIS:')
            print(f"{'-' * 40}")
            generator = SignalGenerator()
            analysis = generator.analyze_only(market_data)
            print(f"Analyzers with results: {analysis['analyzers_count']}")
            print(f"Long Score: {analysis['long_score']}/10")
            print(f"Short Score: {analysis['short_score']}/10")
            print(f"Blocks Long: {analysis['blocks_long']}")
            print(f"Blocks Short: {analysis['blocks_short']}")
            print(f"Signal: {analysis['would_signal']}")
            print(f"\n{'-' * 40}")
            print('ANALYZER RESULTS:')
            print(f"{'-' * 40}")
            for result in analysis['results']:
                print(f'\n{result.analyzer_name}:')
                print(f'  Long: {result.long_score:.1f} | Short: {result.short_score:.1f}')
                print(f'  Confidence: {result.confidence:.2f}')
                print(f'  Reasoning: {result.reasoning}')
                if result.blocks_long:
                    print(f'  WARNING: BLOCKS LONG')
                if result.blocks_short:
                    print(f'  WARNING: BLOCKS SHORT')
            signal = generator.generate(market_data)
            if signal:
                print(f"\n{'=' * 60}")
                print(f'SIGNAL GENERATED: {signal.direction}')
                print(f"{'=' * 60}")
                print(f'Entry: ${signal.entry_price:.6f}')
                print(f'Stop Loss: ${signal.stop_loss:.6f} ({signal.stop_loss_percent:.1f}%)')
                print(f'Targets:')
                for t in signal.targets:
                    print(f'  T{t.target_number}: ${t.target_price:.6f} (+{t.expected_gain_percent:.1f}%) - {t.percent_allocation:.0f}%')
                print(f'Reason: {signal.reason}')
            else:
                print(f"\n{'=' * 60}")
                print('NO SIGNAL GENERATED')
                print(f"{'=' * 60}")
            return market_data
        except Exception as e:
            print(f'\nERROR: {type(e).__name__}: {e}')
            import traceback
            traceback.print_exc()
            return None

async def main():
    tokens = ['BIRBUSDT']
    for token in tokens:
        await test_aggregator(token)
        print('\n')
if __name__ == '__main__':
    asyncio.run(main())
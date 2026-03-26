import asyncio
from src.core.signal_generator import SignalGenerator
from src.data.data_aggregator import DataAggregator
from src.api.mexc_client import MEXCRestClient

async def test_analysis():
    print('=' * 70)
    print('  TESTING SIGNAL GENERATOR WITH OI NOWCAST')
    print('=' * 70)
    sg = SignalGenerator()
    async with MEXCRestClient() as client:
        aggregator = DataAggregator(client)
        symbol = 'DOGEUSDT'
        print(f'\nFetching data for {symbol}...')
        data = await aggregator.aggregate(symbol)
        if data is None:
            print('Failed to fetch data')
            return
        print(f'Price: ${data.price:,.2f}')
        print(f'OI USD: ${data.open_interest_usd:,.0f}')
        print('\n' + '-' * 70)
        print('MARKET DATA (for debugging):')
        print('-' * 70)
        print(f'  market_cap_usd: {data.market_cap_usd}')
        print(f'  oi_mc_ratio: {data.oi_mc_ratio}')
        print(f'  aggression_2h: {data.aggression_2h}')
        print(f'  aggression_5m: {data.aggression_5m}')
        print(f'  volume_1h: {data.volume_1h}')
        print(f'  avg_volume_1h: {data.avg_volume_1h}')
        print(f'  price_change_4h: {data.price_change_4h}')
        print(f'  liquidation_detected: {data.liquidation_detected}')
        result = sg.analyze_only(data)
        print('\n' + '-' * 70)
        print('ANALYZER RESULTS:')
        print('-' * 70)
        for r in result['results']:
            reasoning = r.reasoning[:50] + '...' if len(r.reasoning) > 50 else r.reasoning
            print(f'  {r.analyzer_name:25} Long={r.long_score:.1f} Short={r.short_score:.1f}')
            print(f'    -> {reasoning}')
        print('\n' + '-' * 70)
        print('FINAL SCORES:')
        print('-' * 70)
        print(f"  Long Score:  {result['long_score']}/10 (confidence: {result['long_confidence']})")
        print(f"  Short Score: {result['short_score']}/10 (confidence: {result['short_confidence']})")
        print(f"  Blocks Long:  {result['blocks_long']}")
        print(f"  Blocks Short: {result['blocks_short']}")
        print(f"  Would Signal: {result['would_signal']}")
        print(f"  Analyzers:    {result['analyzers_count']}/7")
        oi_nowcast_results = [r for r in result['results'] if 'Nowcast' in r.analyzer_name]
        if oi_nowcast_results:
            print('\n' + '-' * 70)
            print('OI NOWCAST STATUS:')
            print('-' * 70)
            for r in oi_nowcast_results:
                print(f'  {r.reasoning}')
        else:
            print('\n' + '-' * 70)
            print('OI NOWCAST STATUS:')
            print('-' * 70)
            print('  Returned None (no database connected)')
            print('  This is expected - OI Nowcast needs history data from Monitor mode')
        print('=' * 70)
if __name__ == '__main__':
    asyncio.run(test_analysis())
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from datetime import datetime, timezone
from src.models.market_data import MarketData
from src.core.signal_generator import SignalGenerator

def create_test_data(scenario: str) -> MarketData:
    if scenario == 'STRONG_LONG':
        return MarketData(symbol='STRONGLONG_TEST', exchange='MEXC', timestamp=datetime.now(timezone.utc), price=1.0, volume_24h=1000000, open_interest_usd=110000, market_cap_usd=500000, funding_rate=-0.001, buy_volume_2h=75000, sell_volume_2h=25000, volume_1h=80000, avg_volume_1h=40000, price_change_1h=3.0, price_change_4h=8.0)
    elif scenario == 'STRONG_SHORT':
        return MarketData(symbol='STRONGSHORT_TEST', exchange='MEXC', timestamp=datetime.now(timezone.utc), price=1.0, volume_24h=1000000, open_interest_usd=325000, market_cap_usd=500000, funding_rate=0.002, buy_volume_2h=20000, sell_volume_2h=80000, volume_1h=100000, avg_volume_1h=40000, price_change_1h=-8.0, price_change_4h=-15.0, oi_change_1h=-12.0)
    elif scenario == 'BLOCKED_LONG':
        return MarketData(symbol='BLOCKEDLONG_TEST', exchange='MEXC', timestamp=datetime.now(timezone.utc), price=1.0, volume_24h=1000000, open_interest_usd=100000, market_cap_usd=500000, funding_rate=-0.0005, buy_volume_2h=60000, sell_volume_2h=40000, price_change_4h=80.0, price_change_24h=95.0)
    elif scenario == 'NO_SIGNAL':
        return MarketData(symbol='NOSIGNAL_TEST', exchange='MEXC', timestamp=datetime.now(timezone.utc), price=1.0, volume_24h=1000000, open_interest_usd=40000, market_cap_usd=500000, funding_rate=0.0001, buy_volume_2h=50000, sell_volume_2h=50000)
    elif scenario == 'BIRB_LIKE':
        return MarketData(symbol='BIRBLIKE_TEST', exchange='MEXC', timestamp=datetime.now(timezone.utc), price=1.0, volume_24h=1000000, open_interest_usd=50000, market_cap_usd=500000, funding_rate=-0.02, buy_volume_2h=35000, sell_volume_2h=65000, buy_volume_5m=2000, sell_volume_5m=8000, volume_1h=150000, avg_volume_1h=30000, price_change_1h=-12.0, price_change_4h=-24.0)
    else:
        return MarketData(symbol=f'TEST_{scenario}USDT', exchange='MEXC', timestamp=datetime.now(timezone.utc), price=1.0, volume_24h=1000000, open_interest_usd=100000, market_cap_usd=500000, funding_rate=0.0)

def print_results(scenario: str, analysis: dict):
    print(f"\n{'=' * 60}")
    print(f'SCENARIO: {scenario}')
    print(f"{'=' * 60}")
    print(f"Symbol: {analysis['symbol']}")
    print(f"Analyzers ran: {analysis['analyzers_count']}")
    print()
    print(f"LONG Score:  {analysis['long_score']}/10 (confidence: {analysis['long_confidence']})")
    print(f"SHORT Score: {analysis['short_score']}/10 (confidence: {analysis['short_confidence']})")
    print()
    if analysis['blocks_long']:
        print('[!]  LONG BLOCKED')
    if analysis['blocks_short']:
        print('[!]  SHORT BLOCKED')
    print(f"\n=> SIGNAL: {analysis['would_signal']}")
    print(f'\n--- Analyzer Results ---')
    for result in analysis['results']:
        status = ''
        if result.blocks_long:
            status = ' [BLOCKS LONG]'
        if result.blocks_short:
            status = ' [BLOCKS SHORT]'
        print(f'  {result.analyzer_name}:')
        print(f'    Long={result.long_score:.1f}, Short={result.short_score:.1f}, Conf={result.confidence:.2f}{status}')
        print(f'    {result.reasoning[:80]}...')

def main():
    generator = SignalGenerator()
    scenarios = ['STRONG_LONG', 'STRONG_SHORT', 'BLOCKED_LONG', 'NO_SIGNAL', 'BIRB_LIKE']
    print('\n' + '=' * 60)
    print('SIGNAL GENERATOR TEST')
    print('=' * 60)
    results_summary = []
    for scenario in scenarios:
        data = create_test_data(scenario)
        analysis = generator.analyze_only(data)
        print_results(scenario, analysis)
        signal = generator.generate(data)
        if signal:
            print(f'\n[OK] Signal generated: {signal.direction} @ {signal.entry_price}')
            print(f'   Score: {signal.overall_score}, Confidence: {signal.confidence}')
            print(f'   Stop: {signal.stop_loss} ({signal.stop_loss_percent}%)')
            print(f'   Targets: T1={signal.targets[0].target_price}, T2={signal.targets[1].target_price}, T3={signal.targets[2].target_price}')
        else:
            print(f'\n[X] No signal generated')
        results_summary.append({'scenario': scenario, 'signal': analysis['would_signal'], 'long': analysis['long_score'], 'short': analysis['short_score']})
    print('\n\n' + '=' * 60)
    print('SUMMARY')
    print('=' * 60)
    print(f"{'Scenario':<20} {'Signal':<12} {'Long':<8} {'Short':<8}")
    print('-' * 60)
    for r in results_summary:
        print(f"{r['scenario']:<20} {r['signal']:<12} {r['long']:<8.1f} {r['short']:<8.1f}")
    print('\n\n' + '=' * 60)
    print('VERIFICATION')
    print('=' * 60)
    expected = {'STRONG_LONG': 'LONG', 'STRONG_SHORT': 'SHORT', 'BLOCKED_LONG': 'NO SIGNAL', 'NO_SIGNAL': 'NO SIGNAL', 'BIRB_LIKE': 'NO SIGNAL'}
    all_pass = True
    for r in results_summary:
        exp = expected.get(r['scenario'], 'NO SIGNAL')
        actual = r['signal']
        status = '[OK] PASS' if actual == exp else '[X] FAIL'
        if actual != exp:
            all_pass = False
        print(f"{r['scenario']}: {status} (expected={exp}, got={actual})")
    print('\n' + ('[OK] ALL TESTS PASSED' if all_pass else '[X] SOME TESTS FAILED'))
if __name__ == '__main__':
    main()
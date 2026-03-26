import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from datetime import datetime, timezone
from src.models.market_data import MarketData
from src.core.signal_generator import SignalGenerator

def create_edge_case(name: str, **overrides) -> MarketData:
    base = {'symbol': f'EDGE_{name}', 'exchange': 'MEXC', 'timestamp': datetime.now(timezone.utc), 'price': 1.0, 'volume_24h': 100000, 'open_interest_usd': 50000, 'market_cap_usd': 500000, 'funding_rate': 0.0}
    base.update(overrides)
    return MarketData(**base)

def test_oi_mc_boundaries():
    print('\n' + '=' * 60)
    print('TEST: OI/MC Boundary Values')
    print('=' * 60)
    generator = SignalGenerator()
    test_cases = [(9999, 100000, '< 0.10 - Too low'), (10000, 100000, '= 0.10 - Low boundary'), (15999, 100000, '< 0.16 - Low'), (16000, 100000, '= 0.16 - Optimal start'), (25999, 100000, '< 0.26 - Optimal'), (26000, 100000, '= 0.26 - Optimal upper'), (39999, 100000, '< 0.40 - Elevated'), (40000, 100000, '= 0.40 - Short territory'), (54999, 100000, '< 0.55 - High'), (55000, 100000, '= 0.55 - Danger (blocks)'), (59999, 100000, '< 0.60 - Danger'), (60000, 100000, '= 0.60 - Extreme')]
    for oi, mc, desc in test_cases:
        data = create_edge_case(f'OI_MC_{oi}_{mc}', open_interest_usd=oi, market_cap_usd=mc, buy_volume_2h=50000, sell_volume_2h=50000)
        analysis = generator.analyze_only(data)
        ratio = oi / mc
        print(f'  OI/MC {ratio:.4f} ({desc})')
        print(f"    Long={analysis['long_score']:.1f}, Short={analysis['short_score']:.1f}")
        if analysis['blocks_long']:
            print(f'    [!] BLOCKS LONG')
        print()

def test_funding_boundaries():
    print('\n' + '=' * 60)
    print('TEST: Funding Rate Boundary Values')
    print('=' * 60)
    generator = SignalGenerator()
    test_cases = [(-0.006, '< -0.50% Ultra extreme negative'), (-0.005, '= -0.50% Extreme boundary'), (-0.001, '= -0.10% Strong negative'), (-0.0008, '= -0.08% Very negative'), (-0.0005, '= -0.05% Moderate negative'), (-0.0002, '= -0.02% Slight negative'), (0.0, '= 0.00% Neutral'), (0.0002, '= +0.02% Slight positive'), (0.0005, '= +0.05% Moderate positive'), (0.0008, '= +0.08% High positive'), (0.001, '= +0.10% Extreme (blocks long)'), (0.005, '= +0.50% Ultra extreme positive')]
    for rate, desc in test_cases:
        data = create_edge_case(f'FUNDING_{rate}', funding_rate=rate, buy_volume_2h=50000, sell_volume_2h=50000)
        analysis = generator.analyze_only(data)
        print(f'  Funding {rate * 100:+.4f}% ({desc})')
        print(f"    Long={analysis['long_score']:.1f}, Short={analysis['short_score']:.1f}")
        if analysis['blocks_long']:
            print(f'    [!] BLOCKS LONG')
        print()

def test_aggression_boundaries():
    print('\n' + '=' * 60)
    print('TEST: Aggression Boundary Values')
    print('=' * 60)
    generator = SignalGenerator()
    for agg in range(0, 101, 10):
        buy = agg * 1000
        sell = (100 - agg) * 1000
        data = create_edge_case(f'AGG_{agg}', buy_volume_2h=buy, sell_volume_2h=sell)
        analysis = generator.analyze_only(data)
        print(f'  Aggression {agg}% (buy={buy}, sell={sell})')
        print(f"    Long={analysis['long_score']:.1f}, Short={analysis['short_score']:.1f}")
        if analysis['blocks_long']:
            print(f'    [!] BLOCKS LONG')
        if analysis['blocks_short']:
            print(f'    [!] BLOCKS SHORT')
        print()

def test_volume_spike_boundaries():
    print('\n' + '=' * 60)
    print('TEST: Volume Spike Boundary Values')
    print('=' * 60)
    generator = SignalGenerator()
    test_cases = [(140, 100, -10.0, '1.4x - below threshold'), (150, 100, -10.0, '1.5x - minimum spike bearish'), (199, 100, -10.0, '1.99x - below blocking'), (200, 100, -10.0, '2.0x - blocks long bearish'), (300, 100, -10.0, '3.0x - strong bearish'), (500, 100, -10.0, '5.0x - extreme bearish'), (150, 100, -4.0, '1.5x - direction uncertain (-4%)'), (150, 100, 0.0, '1.5x - direction uncertain (0%)'), (150, 100, 4.0, '1.5x - direction uncertain (+4%)'), (150, 100, 10.0, '1.5x - bullish'), (200, 100, 10.0, '2.0x - blocks short bullish')]
    for vol_1h, avg_vol, price_chg, desc in test_cases:
        data = create_edge_case(f'VOL_{vol_1h}_{avg_vol}_{price_chg}', volume_1h=vol_1h, avg_volume_1h=avg_vol, price_change_1h=price_chg, buy_volume_2h=50000, sell_volume_2h=50000)
        analysis = generator.analyze_only(data)
        ratio = vol_1h / avg_vol
        print(f'  Volume {ratio:.1f}x, Price {price_chg:+.1f}% ({desc})')
        print(f"    Long={analysis['long_score']:.1f}, Short={analysis['short_score']:.1f}")
        if analysis['blocks_long']:
            print(f'    [!] BLOCKS LONG')
        if analysis['blocks_short']:
            print(f'    [!] BLOCKS SHORT')
        print()

def test_already_pumped_boundaries():
    print('\n' + '=' * 60)
    print('TEST: Already Pumped Boundary Values')
    print('=' * 60)
    generator = SignalGenerator()
    test_cases = [(14.0, '14% - below threshold'), (15.0, '15% - minimum pump'), (29.0, '29% - low pump'), (30.0, '30% - moderate pump'), (49.0, '49% - moderate pump'), (50.0, '50% - high pump (blocks long)'), (99.0, '99% - high pump'), (100.0, '100% - extreme pump'), (200.0, '200% - extreme pump'), (201.0, '201% - max pump')]
    for pump, desc in test_cases:
        data = create_edge_case(f'PUMP_{pump}', price_change_4h=pump, buy_volume_2h=50000, sell_volume_2h=50000)
        analysis = generator.analyze_only(data)
        print(f'  Pump +{pump:.0f}% ({desc})')
        print(f"    Long={analysis['long_score']:.1f}, Short={analysis['short_score']:.1f}")
        if analysis['blocks_long']:
            print(f'    [!] BLOCKS LONG')
        print()

def test_liquidation_detection():
    print('\n' + '=' * 60)
    print('TEST: Liquidation Detection')
    print('=' * 60)
    generator = SignalGenerator()
    test_cases = [(-4.0, -3.0, 1.0, 'No liquidation (OI -4%, small move)'), (-5.0, -3.0, 1.0, 'Weak liquidation (OI -5%)'), (-10.0, -3.0, 1.0, 'Significant (OI -10%, AFTER)'), (-10.0, -8.0, 2.5, 'DURING longs liquidated'), (-15.0, -12.0, 3.0, 'Strong DURING longs'), (-10.0, 8.0, 2.5, 'DURING shorts liquidated'), (-20.0, -15.0, 4.0, 'Extreme DURING longs')]
    for oi_chg, price_chg, vol_ratio, desc in test_cases:
        data = create_edge_case(f'LIQ_{oi_chg}_{price_chg}', oi_change_1h=oi_chg, price_change_1h=price_chg, volume_1h=vol_ratio * 100, avg_volume_1h=100, buy_volume_2h=50000, sell_volume_2h=50000)
        analysis = generator.analyze_only(data)
        liq_result = None
        for r in analysis['results']:
            if r.analyzer_name == 'Liquidation Analyzer':
                liq_result = r
                break
        print(f'  OI {oi_chg:+.0f}%, Price {price_chg:+.0f}%, Vol {vol_ratio:.1f}x ({desc})')
        if liq_result:
            print(f'    Long={liq_result.long_score:.1f}, Short={liq_result.short_score:.1f}')
            print(f'    {liq_result.reasoning}')
        else:
            print(f'    [No liquidation detected]')
        print()

def test_zero_and_none_values():
    print('\n' + '=' * 60)
    print('TEST: Zero and Edge Values')
    print('=' * 60)
    generator = SignalGenerator()
    test_cases = [('Zero volume', {'volume_24h': 0, 'volume_1h': 0, 'avg_volume_1h': 0}), ('Tiny OI', {'open_interest_usd': 1}), ('Huge OI/MC', {'open_interest_usd': 1000000, 'market_cap_usd': 100000}), ('Zero aggression', {'buy_volume_2h': 0, 'sell_volume_2h': 0}), ('100% buy', {'buy_volume_2h': 100000, 'sell_volume_2h': 0}), ('100% sell', {'buy_volume_2h': 0, 'sell_volume_2h': 100000})]
    for name, overrides in test_cases:
        try:
            data = create_edge_case(name.replace(' ', '_'), **overrides)
            analysis = generator.analyze_only(data)
            print(f'  {name}:')
            print(f"    Analyzers ran: {analysis['analyzers_count']}")
            print(f"    Long={analysis['long_score']:.1f}, Short={analysis['short_score']:.1f}")
            print(f"    Signal: {analysis['would_signal']}")
        except Exception as e:
            print(f'  {name}: ERROR - {e}')
        print()

def test_shift_detection():
    print('\n' + '=' * 60)
    print('TEST: Aggression Shift Detection')
    print('=' * 60)
    generator = SignalGenerator()
    test_cases = [(50, 50, 'No shift (50% -> 50%)'), (50, 60, 'Small shift +10pp (not significant)'), (50, 65, 'STRENGTHENING +15pp'), (50, 75, 'Strong STRENGTHENING +25pp'), (50, 90, 'Extreme STRENGTHENING +40pp'), (70, 55, 'WEAKENING -15pp'), (70, 45, 'Strong WEAKENING -25pp'), (80, 40, 'Extreme WEAKENING -40pp')]
    for agg_2h, agg_5m, desc in test_cases:
        buy_2h = agg_2h * 1000
        sell_2h = (100 - agg_2h) * 1000
        buy_5m = agg_5m * 100
        sell_5m = (100 - agg_5m) * 100
        data = create_edge_case(f'SHIFT_{agg_2h}_{agg_5m}', buy_volume_2h=buy_2h, sell_volume_2h=sell_2h, buy_volume_5m=buy_5m, sell_volume_5m=sell_5m)
        analysis = generator.analyze_only(data)
        agg_result = None
        for r in analysis['results']:
            if r.analyzer_name == 'Aggression Analyzer':
                agg_result = r
                break
        print(f'  2H: {agg_2h}% -> 5M: {agg_5m}% ({desc})')
        if agg_result:
            print(f'    Long={agg_result.long_score:.1f}, Short={agg_result.short_score:.1f}')
            print(f'    {agg_result.reasoning[:70]}...')
        print()

def main():
    print('\n' + '#' * 60)
    print('# EDGE CASE TESTS')
    print('#' * 60)
    test_oi_mc_boundaries()
    test_funding_boundaries()
    test_aggression_boundaries()
    test_volume_spike_boundaries()
    test_already_pumped_boundaries()
    test_liquidation_detection()
    test_zero_and_none_values()
    test_shift_detection()
    print('\n' + '#' * 60)
    print('# TESTS COMPLETE')
    print('#' * 60)
if __name__ == '__main__':
    main()
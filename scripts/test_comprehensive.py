import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from datetime import datetime, timezone
from src.models.market_data import MarketData
from src.core.signal_generator import SignalGenerator

def create_scenario(**kwargs) -> MarketData:
    defaults = {'symbol': 'TEST', 'exchange': 'MEXC', 'timestamp': datetime.now(timezone.utc), 'price': 1.0, 'volume_24h': 500000, 'open_interest_usd': 100000, 'market_cap_usd': 500000, 'funding_rate': 0.0}
    defaults.update(kwargs)
    return MarketData(**defaults)

def print_analysis(name: str, analysis: dict, expected_signal: str=None):
    signal = analysis['would_signal']
    long_s = analysis['long_score']
    short_s = analysis['short_score']
    if expected_signal:
        status = '[OK]' if signal == expected_signal else '[FAIL]'
    else:
        status = '   '
    blocks = []
    if analysis['blocks_long']:
        blocks.append('BL')
    if analysis['blocks_short']:
        blocks.append('BS')
    block_str = f"[{','.join(blocks)}]" if blocks else ''
    print(f'{status} {name:<40} L={long_s:.1f} S={short_s:.1f} => {signal:<10} {block_str}')

def test_oi_mc_funding_matrix():
    print('\n' + '=' * 80)
    print('TEST: OI/MC x Funding Matrix')
    print('=' * 80)
    generator = SignalGenerator()
    oi_mc_levels = [(0.1, 'low'), (0.25, 'optimal'), (0.45, 'high'), (0.6, 'extreme')]
    funding_levels = [(-0.002, 'strong_neg'), (-0.0005, 'slight_neg'), (0.0, 'neutral'), (0.0005, 'slight_pos'), (0.002, 'strong_pos')]
    print(f"\n{'Scenario':<45} {'Long':<6} {'Short':<6} {'Signal':<12} {'Block'}")
    print('-' * 80)
    for oi_mc, oi_label in oi_mc_levels:
        for funding, fund_label in funding_levels:
            oi = int(oi_mc * 500000)
            data = create_scenario(symbol=f'TEST_{oi_label}_{fund_label}', open_interest_usd=oi, funding_rate=funding, buy_volume_2h=50000, sell_volume_2h=50000)
            analysis = generator.analyze_only(data)
            name = f'OI/MC={oi_mc:.2f} + Fund={funding * 100:+.2f}%'
            print_analysis(name, analysis)

def test_aggression_volume_matrix():
    print('\n' + '=' * 80)
    print('TEST: Aggression x Volume Spike Matrix')
    print('=' * 80)
    generator = SignalGenerator()
    agg_levels = [20, 35, 50, 65, 80]
    volume_scenarios = [(1.0, 0, 'normal'), (2.5, -8, 'spike_bear'), (2.5, 8, 'spike_bull'), (5.0, -15, 'extreme_bear')]
    print(f"\n{'Scenario':<45} {'Long':<6} {'Short':<6} {'Signal':<12} {'Block'}")
    print('-' * 80)
    for agg in agg_levels:
        for vol_ratio, price_chg, vol_label in volume_scenarios:
            buy = agg * 1000
            sell = (100 - agg) * 1000
            vol_1h = vol_ratio * 50000
            data = create_scenario(symbol=f'AGG_{agg}_{vol_label}', buy_volume_2h=buy, sell_volume_2h=sell, volume_1h=vol_1h, avg_volume_1h=50000, price_change_1h=price_chg)
            analysis = generator.analyze_only(data)
            name = f'Agg={agg}% + Vol={vol_ratio:.1f}x ({vol_label})'
            print_analysis(name, analysis)

def test_liquidation_scenarios():
    print('\n' + '=' * 80)
    print('TEST: Liquidation Scenarios')
    print('=' * 80)
    generator = SignalGenerator()
    scenarios = [(-5, -2, 1.0, 'Minor OI drop, no confirm', 'NO SIGNAL'), (-10, -3, 1.0, 'OI -10%, weak price', 'NO SIGNAL'), (-10, -8, 2.5, 'OI -10%, DURING longs', 'NO SIGNAL'), (-15, -12, 3.0, 'OI -15%, clear DURING longs', 'NO SIGNAL'), (-20, -15, 4.0, 'OI -20%, extreme DURING', 'NO SIGNAL'), (-15, -2, 1.2, 'OI -15%, price stable (AFTER)', 'NO SIGNAL'), (-10, 8, 2.5, 'OI -10%, price UP = shorts liq', 'NO SIGNAL')]
    print(f"\n{'Scenario':<45} {'Long':<6} {'Short':<6} {'Signal':<12} {'Block'}")
    print('-' * 80)
    for oi_chg, price_chg, vol_r, name, expected in scenarios:
        data = create_scenario(symbol=f'LIQ_{name}', oi_change_1h=oi_chg, price_change_1h=price_chg, volume_1h=vol_r * 50000, avg_volume_1h=50000, buy_volume_2h=50000, sell_volume_2h=50000)
        analysis = generator.analyze_only(data)
        print_analysis(name, analysis, expected)

def test_real_world_scenarios():
    print('\n' + '=' * 80)
    print('TEST: Real-World Inspired Scenarios')
    print('=' * 80)
    generator = SignalGenerator()
    print(f"\n{'Scenario':<45} {'Long':<6} {'Short':<6} {'Signal':<12} {'Block'}")
    print('-' * 80)
    data = create_scenario(symbol='BULLA_PRE', open_interest_usd=50000, market_cap_usd=1000000, funding_rate=0.0001, buy_volume_2h=45000, sell_volume_2h=55000)
    analysis = generator.analyze_only(data)
    print_analysis('BULLA pre-pump (quiet)', analysis, 'NO SIGNAL')
    data = create_scenario(symbol='BULLA_PUMP', open_interest_usd=80000, market_cap_usd=1000000, funding_rate=-0.0003, buy_volume_2h=70000, sell_volume_2h=30000, volume_1h=200000, avg_volume_1h=40000, price_change_1h=15, price_change_4h=45)
    analysis = generator.analyze_only(data)
    print_analysis('BULLA pump (+45%, vol 5x)', analysis, 'NO SIGNAL')
    data = create_scenario(symbol='BULLA_DUMP', open_interest_usd=60000, market_cap_usd=800000, funding_rate=-0.001, buy_volume_2h=30000, sell_volume_2h=70000, volume_1h=180000, avg_volume_1h=50000, price_change_1h=-12, price_change_4h=-25, oi_change_1h=-8)
    analysis = generator.analyze_only(data)
    print_analysis('BULLA dump (-25%, vol 3.6x)', analysis)
    data = create_scenario(symbol='IDEAL_LONG', open_interest_usd=110000, market_cap_usd=500000, funding_rate=-0.0008, buy_volume_2h=75000, sell_volume_2h=25000, buy_volume_5m=8000, sell_volume_5m=2000, volume_1h=60000, avg_volume_1h=50000, price_change_1h=2, price_change_4h=5)
    analysis = generator.analyze_only(data)
    print_analysis('Ideal LONG (OI/MC optimal, agg 75%)', analysis, 'LONG')
    data = create_scenario(symbol='IDEAL_SHORT', open_interest_usd=300000, market_cap_usd=500000, funding_rate=0.0015, buy_volume_2h=25000, sell_volume_2h=75000, buy_volume_5m=1500, sell_volume_5m=8500, volume_1h=120000, avg_volume_1h=50000, price_change_1h=-10, price_change_4h=-18, oi_change_1h=-12)
    analysis = generator.analyze_only(data)
    print_analysis('Ideal SHORT (OI/MC 0.60, agg 25%)', analysis, 'SHORT')
    data = create_scenario(symbol='CONFLICT_1', open_interest_usd=75000, market_cap_usd=500000, funding_rate=-0.015, buy_volume_2h=35000, sell_volume_2h=65000, volume_1h=200000, avg_volume_1h=40000, price_change_1h=-15)
    analysis = generator.analyze_only(data)
    print_analysis('Conflict: Fund -1.5% but dump -15%', analysis, 'NO SIGNAL')
    data = create_scenario(symbol='CONFLICT_2', open_interest_usd=275000, market_cap_usd=500000, funding_rate=-0.001, buy_volume_2h=60000, sell_volume_2h=40000)
    analysis = generator.analyze_only(data)
    print_analysis('Conflict: OI/MC 0.55 but fund -0.10%', analysis, 'NO SIGNAL')
    data = create_scenario(symbol='LOW_OIMC_BULL', open_interest_usd=25000, market_cap_usd=500000, funding_rate=-0.001, buy_volume_2h=80000, sell_volume_2h=20000, volume_1h=100000, avg_volume_1h=50000, price_change_1h=8)
    analysis = generator.analyze_only(data)
    print_analysis('Low OI/MC 0.05 + all bullish', analysis)
    data = create_scenario(symbol='SQUEEZE_SETUP', open_interest_usd=150000, market_cap_usd=500000, funding_rate=-0.002, buy_volume_2h=55000, sell_volume_2h=45000, price_change_1h=0.5, price_change_4h=-2)
    analysis = generator.analyze_only(data)
    print_analysis('Squeeze setup: fund -0.20%, stable', analysis)
    data = create_scenario(symbol='POST_PUMP_CONSOL', open_interest_usd=100000, market_cap_usd=500000, funding_rate=0.0003, buy_volume_2h=48000, sell_volume_2h=52000, price_change_1h=-1, price_change_4h=35, price_change_24h=60)
    analysis = generator.analyze_only(data)
    print_analysis('Post-pump consolidation (+60% 24h)', analysis)

def test_signal_generation():
    print('\n' + '=' * 80)
    print('TEST: Full Signal Generation')
    print('=' * 80)
    generator = SignalGenerator()
    data = create_scenario(symbol='GEN_LONG', open_interest_usd=115000, market_cap_usd=500000, funding_rate=-0.001, buy_volume_2h=78000, sell_volume_2h=22000, buy_volume_5m=8500, sell_volume_5m=1500, price_change_4h=5)
    signal = generator.generate(data)
    if signal:
        print(f'\nLONG Signal Generated:')
        print(f'  Score: {signal.overall_score}/10, Confidence: {signal.confidence}')
        print(f'  Entry: ${signal.entry_price}, Stop: ${signal.stop_loss} ({signal.stop_loss_percent}%)')
        print(f'  T1: ${signal.targets[0].target_price} (+{signal.targets[0].expected_gain_percent}%)')
        print(f'  T2: ${signal.targets[1].target_price} (+{signal.targets[1].expected_gain_percent}%)')
        print(f'  T3: ${signal.targets[2].target_price} (+{signal.targets[2].expected_gain_percent}%)')
        print(f'  Risk/Reward: {signal.risk_reward_ratio:.2f}')
    else:
        print('\n[FAIL] Expected LONG signal but got None')
    data = create_scenario(symbol='GEN_SHORT', open_interest_usd=325000, market_cap_usd=500000, funding_rate=0.002, buy_volume_2h=20000, sell_volume_2h=80000, buy_volume_5m=1000, sell_volume_5m=9000, volume_1h=150000, avg_volume_1h=50000, price_change_1h=-10, price_change_4h=-20, oi_change_1h=-15)
    signal = generator.generate(data)
    if signal:
        print(f'\nSHORT Signal Generated:')
        print(f'  Score: {signal.overall_score}/10, Confidence: {signal.confidence}')
        print(f'  Entry: ${signal.entry_price}, Stop: ${signal.stop_loss} ({signal.stop_loss_percent}%)')
        print(f'  T1: ${signal.targets[0].target_price} (+{signal.targets[0].expected_gain_percent}%)')
        print(f'  T2: ${signal.targets[1].target_price} (+{signal.targets[1].expected_gain_percent}%)')
        print(f'  T3: ${signal.targets[2].target_price} (+{signal.targets[2].expected_gain_percent}%)')
        print(f'  Risk/Reward: {signal.risk_reward_ratio:.2f}')
    else:
        print('\n[FAIL] Expected SHORT signal but got None')

def test_edge_values():
    print('\n' + '=' * 80)
    print('TEST: Edge Values')
    print('=' * 80)
    generator = SignalGenerator()
    print(f"\n{'Scenario':<45} {'Long':<6} {'Short':<6} {'Signal':<12}")
    print('-' * 70)
    edge_cases = [('OI/MC = 1.0 (100%)', {'open_interest_usd': 500000, 'market_cap_usd': 500000}), ('OI/MC = 2.0 (200%)', {'open_interest_usd': 1000000, 'market_cap_usd': 500000}), ('Funding -5%', {'funding_rate': -0.05}), ('Funding +5%', {'funding_rate': 0.05}), ('Aggression 5%', {'buy_volume_2h': 5000, 'sell_volume_2h': 95000}), ('Aggression 95%', {'buy_volume_2h': 95000, 'sell_volume_2h': 5000}), ('Volume spike 20x', {'volume_1h': 1000000, 'avg_volume_1h': 50000, 'price_change_1h': -20}), ('Price change -50%', {'price_change_1h': -50, 'price_change_4h': -60}), ('Price change +200%', {'price_change_4h': 200, 'price_change_24h': 300}), ('OI change -50%', {'oi_change_1h': -50, 'price_change_1h': -30, 'volume_1h': 200000, 'avg_volume_1h': 50000})]
    for name, overrides in edge_cases:
        base = {'buy_volume_2h': 50000, 'sell_volume_2h': 50000}
        base.update(overrides)
        try:
            data = create_scenario(**base)
            analysis = generator.analyze_only(data)
            print_analysis(name, analysis)
        except Exception as e:
            print(f'[ERR] {name:<40} Error: {e}')

def main():
    print('\n' + '#' * 80)
    print('# COMPREHENSIVE TEST SUITE')
    print('#' * 80)
    test_oi_mc_funding_matrix()
    test_aggression_volume_matrix()
    test_liquidation_scenarios()
    test_real_world_scenarios()
    test_signal_generation()
    test_edge_values()
    print('\n' + '#' * 80)
    print('# TESTS COMPLETE')
    print('#' * 80)
if __name__ == '__main__':
    main()
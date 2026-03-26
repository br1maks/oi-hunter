from datetime import datetime, timedelta
from src.analyzers.oi_nowcast_analyzer import OINowcastAnalyzer, normalize_symbol

def print_header(title: str):
    print(f"\n{'=' * 70}")
    print(f'  {title}')
    print('=' * 70)

def test_velocity_calculation():
    print_header('TEST 1: Velocity Calculation (Linear Regression)')
    analyzer = OINowcastAnalyzer()
    now = datetime.utcnow()
    print('\n[Сценарий 1] OI растёт: $1M -> $1.1M за 10 минут')
    history_growth = [(now - timedelta(minutes=10), 1000000), (now - timedelta(minutes=8), 1020000), (now - timedelta(minutes=6), 1040000), (now - timedelta(minutes=4), 1060000), (now - timedelta(minutes=2), 1080000), (now, 1100000)]
    velocity = analyzer._calculate_velocity(history_growth)
    print(f"  История: {[f'${h[1]:,}' for h in history_growth]}")
    print(f'  Velocity: {velocity:+,.0f} USD/min')
    print(f'  Ожидаемо: ~+10,000 USD/min [OK]' if 9000 < velocity < 11000 else '  ОШИБКА!')
    print('\n[Сценарий 2] OI падает: $1M -> $850K за 10 минут')
    history_decline = [(now - timedelta(minutes=10), 1000000), (now - timedelta(minutes=8), 970000), (now - timedelta(minutes=6), 940000), (now - timedelta(minutes=4), 910000), (now - timedelta(minutes=2), 880000), (now, 850000)]
    velocity = analyzer._calculate_velocity(history_decline)
    print(f"  История: {[f'${h[1]:,}' for h in history_decline]}")
    print(f'  Velocity: {velocity:+,.0f} USD/min')
    print(f'  Ожидаемо: ~-15,000 USD/min [OK]' if -16000 < velocity < -14000 else '  ОШИБКА!')
    print('\n[Сценарий 3] OI стабильный: ~$1M')
    history_flat = [(now - timedelta(minutes=10), 1000000), (now - timedelta(minutes=8), 1002000), (now - timedelta(minutes=6), 998000), (now - timedelta(minutes=4), 1001000), (now - timedelta(minutes=2), 999000), (now, 1000000)]
    velocity = analyzer._calculate_velocity(history_flat)
    print(f'  Velocity: {velocity:+,.0f} USD/min')
    print(f'  Ожидаемо: ~0 USD/min [OK]' if abs(velocity) < 500 else '  ОШИБКА!')

def test_prediction():
    print_header('TEST 2: OI Prediction')
    analyzer = OINowcastAnalyzer()
    print('\n[Сценарий] OI = $1M, Velocity = +$10K/min, Acceleration = 0')
    result = analyzer._predict_oi(current_oi=1000000, velocity=10000, acceleration=0, minutes_ahead=10)
    print(f"  Prediction 10min: ${result['predicted_oi']:,.0f}")
    print(f"  Change: {result['predicted_change_pct']:+.1f}%")
    print(f"  Confidence: {result['confidence']:.2f}")
    print(f'  Ожидаемо: $1,100,000 (+10%) [OK]' if abs(result['predicted_change_pct'] - 10) < 1 else '  ОШИБКА!')
    print('\n[Сценарий] OI = $1M, Velocity = +$10K/min, Acceleration = +$2K')
    result = analyzer._predict_oi(current_oi=1000000, velocity=10000, acceleration=2000, minutes_ahead=10)
    print(f'  Формула: s = 1M + 10K*10 + 0.5*2K*100 = $1,200,000')
    print(f"  Prediction 10min: ${result['predicted_oi']:,.0f}")
    print(f"  Change: {result['predicted_change_pct']:+.1f}%")
    print(f'  Ожидаемо: $1,200,000 (+20%) [OK]' if abs(result['predicted_change_pct'] - 20) < 1 else '  ОШИБКА!')

def test_scoring():
    print_header('TEST 3: Scoring Based on Prediction')
    analyzer = OINowcastAnalyzer()
    scenarios = [(+15, 'SURGING', 9, 1), (+7, 'growing', 8, 2), (+3, 'stable growth', 6, 3), (0, 'neutral', 5, 5), (-3, 'weakening', 3, 6), (-7, 'COLLAPSING', 1, 8), (-12, 'CRASHING', 0, 10)]
    print('\n  Predicted Change -> (Long Score, Short Score, Interpretation)')
    print('  ' + '-' * 60)
    for pct, expected_msg, expected_long, expected_short in scenarios:
        long_score, short_score, msg = analyzer._score_prediction(pct)
        status = '[OK]' if long_score == expected_long and short_score == expected_short else '[FAIL]'
        print(f"  {pct:+5.0f}% -> Long={long_score:.0f}, Short={short_score:.0f}, '{msg}' {status}")

def test_full_scenario():
    print_header('TEST 4: Full Scenario Simulation')
    analyzer = OINowcastAnalyzer()
    now = datetime.utcnow()
    print('\n[Реалистичный сценарий]')
    print('  Монета PUMPUSDT, последние 20 минут OI растёт с ускорением')
    history = [(now - timedelta(minutes=20), 500000), (now - timedelta(minutes=18), 510000), (now - timedelta(minutes=16), 525000), (now - timedelta(minutes=14), 545000), (now - timedelta(minutes=12), 570000), (now - timedelta(minutes=10), 600000), (now - timedelta(minutes=8), 640000), (now - timedelta(minutes=6), 690000), (now - timedelta(minutes=4), 750000), (now - timedelta(minutes=2), 820000), (now, 900000)]
    print(f'\n  История OI (11 точек за 20 минут):')
    for ts, oi in history:
        mins_ago = (now - ts).total_seconds() / 60
        print(f'    -{mins_ago:4.0f}min: ${oi:>10,}')
    current_oi = history[-1][1]
    velocity = analyzer._calculate_velocity(history)
    acceleration = analyzer._calculate_acceleration(history)
    print(f'\n  Расчёты:')
    print(f'    Current OI:   ${current_oi:,}')
    print(f'    Velocity:     {velocity:+,.0f} USD/min')
    print(f'    Acceleration: {acceleration:+,.0f}')
    print(f'\n  Предсказания:')
    for minutes in [5, 10, 15]:
        pred = analyzer._predict_oi(current_oi, velocity, acceleration, minutes)
        print(f"    {minutes}min: ${pred['predicted_oi']:>12,.0f} ({pred['predicted_change_pct']:+6.1f}%) conf={pred['confidence']:.2f}")
    pred_10 = analyzer._predict_oi(current_oi, velocity, acceleration, 10)
    long_score, short_score, msg = analyzer._score_prediction(pred_10['predicted_change_pct'])
    print(f'\n  Результат (по 10min prediction):')
    print(f'    {msg}')
    print(f'    Long Score:  {long_score}/10')
    print(f'    Short Score: {short_score}/10')
    if pred_10['predicted_change_pct'] >= 10:
        print(f'    -> blocks_short=True (не шортить растущий OI!)')
    elif pred_10['predicted_change_pct'] <= -5:
        print(f'    -> blocks_long=True (не лонговать падающий OI!)')

def test_symbol_normalization():
    print_header('TEST 5: Symbol Normalization')
    tests = [('BTCUSDT', 'BTC_USDT'), ('BTC_USDT', 'BTC_USDT'), ('PIPPINUSDT', 'PIPPIN_USDT'), ('DOGEUSDT', 'DOGE_USDT')]
    print('\n  Input -> Output')
    print('  ' + '-' * 30)
    for input_sym, expected in tests:
        result = normalize_symbol(input_sym)
        status = '[OK]' if result == expected else '[FAIL]'
        print(f'  {input_sym:15} -> {result:15} {status}')
if __name__ == '__main__':
    print('\n' + '=' * 70)
    print('       OI NOWCAST ANALYZER - DEMO & VERIFICATION')
    print('=' * 70)
    test_symbol_normalization()
    test_velocity_calculation()
    test_prediction()
    test_scoring()
    test_full_scenario()
    print('\n' + '=' * 70)
    print('  DEMO COMPLETE')
    print('=' * 70 + '\n')
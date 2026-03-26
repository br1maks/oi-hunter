from src.analyzers.oi_nowcast_analyzer import OINowcastAnalyzer
a = OINowcastAnalyzer()
print('=== Phase Classification ===')
cases = [(8.0, 100, None, 'SURGING'), (8.0, -500, 'SURGING', 'OVERHEATED'), (8.0, -500, None, 'SURGING'), (8.0, -500, 'STABLE', 'SURGING'), (3.0, 0, None, 'GROWING'), (1.0, 0, None, 'STABLE'), (-3.0, 0, None, 'WEAKENING'), (-7.0, 0, None, 'COLLAPSING'), (-15.0, 0, None, 'COLLAPSING')]
all_ok = True
for pct, accel, prev, expected in cases:
    result = a._classify_phase(pct, accel, prev)
    status = 'OK' if result == expected else 'FAIL'
    if status == 'FAIL':
        all_ok = False
    print(f'  [{status}] pct={pct:+.0f}%, accel={accel}, prev={prev!r:10s} -> {result!r} (expected {expected!r})')
print('\n=== Transition Bonuses ===')
transitions = [('STABLE', 'SURGING', 2.0, 0.0, 'POSSIBLE PUMP'), ('STABLE', 'GROWING', 2.0, 0.0, 'POSSIBLE PUMP'), ('GROWING', 'SURGING', 1.5, 0.0, 'CONFIRMED PUMP'), ('SURGING', 'OVERHEATED', 0.0, 2.0, 'OVERHEATED - EXIT WARNING'), ('STABLE', 'WEAKENING', 0.0, 2.0, 'POSSIBLE DRAWDOWN'), ('STABLE', 'COLLAPSING', 0.0, 2.0, 'POSSIBLE DRAWDOWN'), ('GROWING', 'WEAKENING', 0.0, 2.0, 'CONFIRMED DRAWDOWN'), ('SURGING', 'COLLAPSING', 0.0, 3.0, 'REVERSAL SIGNAL!'), ('OVERHEATED', 'COLLAPSING', 0.0, 3.0, 'REVERSAL SIGNAL!'), ('WEAKENING', 'COLLAPSING', 0.0, 1.5, 'STRONG SELLOFF'), ('COLLAPSING', 'STABLE', 1.5, 0.0, 'REBOUND'), ('COLLAPSING', 'GROWING', 1.5, 0.0, 'REBOUND'), ('WEAKENING', 'STABLE', 1.5, 0.0, 'REBOUND'), ('STABLE', 'STABLE', 0.0, 0.0, ''), (None, 'SURGING', 0.0, 0.0, '')]
for prev, cur, exp_lb, exp_sb, exp_lbl in transitions:
    lb, sb, lbl = a._get_phase_transition_bonus(prev, cur)
    ok = lb == exp_lb and sb == exp_sb and (lbl == exp_lbl)
    status = 'OK' if ok else 'FAIL'
    if not ok:
        all_ok = False
    print(f'  [{status}] {prev!r:12s} -> {cur!r:12s}: long+{lb}, short+{sb}, {lbl!r}')
    if not ok:
        print(f'           EXPECTED:                         long+{exp_lb}, short+{exp_sb}, {exp_lbl!r}')
print('\n=== Reasoning Format ===')
prev_phase = 'STABLE'
current_phase = 'SURGING'
transition_label = 'POSSIBLE PUMP'
if prev_phase and prev_phase != current_phase:
    phase_prefix = f'[{prev_phase}->{current_phase}]'
    if transition_label:
        phase_prefix += f' {transition_label} |'
else:
    phase_prefix = f'[{current_phase}]'
r1 = f'{phase_prefix} OI SURGING - strong momentum! | Velocity: +5000 USD/min | 5m: +2.0%, 10m: +4.0%, 15m: +6.0%'
print(f'  Transition: {r1}')
prev_phase2 = 'SURGING'
current_phase2 = 'SURGING'
transition_label2 = ''
if prev_phase2 and prev_phase2 != current_phase2:
    phase_prefix2 = f'[{prev_phase2}->{current_phase2}]'
else:
    phase_prefix2 = f'[{current_phase2}]'
r2 = f'{phase_prefix2} OI SURGING - strong momentum! | Velocity: +5000 USD/min | 5m: +2.0%, 10m: +4.0%, 15m: +6.0%'
print(f'  Same phase: {r2}')
print()
print('=== SUMMARY ===')
print('ALL TESTS PASSED' if all_ok else 'SOME TESTS FAILED')
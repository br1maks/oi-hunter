import asyncio
import sys
sys.path.insert(0, 'D:/oi-hunter')
from src.api.mexc_client import MEXCRestClient

def score_oi_mc_long(ratio):
    if ratio < 0.1:
        return (2, 'Too low - insufficient fuel')
    elif ratio < 0.16:
        return (5, 'Low - building interest')
    elif ratio < 0.2:
        return (9, 'Optimal lower range')
    elif ratio < 0.26:
        return (10, 'Optimal sweet spot!')
    elif ratio < 0.3:
        return (9, 'Optimal upper range')
    elif ratio < 0.35:
        return (7, 'Elevated - caution starting')
    elif ratio < 0.4:
        return (6, 'Elevated - manageable')
    elif ratio < 0.45:
        return (4, 'High - significant caution')
    elif ratio < 0.5:
        return (3, 'High - profit-taking zone')
    elif ratio < 0.55:
        return (1, 'Danger - overleveraged')
    elif ratio < 0.6:
        return (0, 'Danger - exit longs')
    else:
        return (0, 'EXTREME DANGER - never long!')

def score_funding(rate):
    rate_pct = rate * 100
    if rate < -0.1:
        return (10, 'BULLISH', f'Extreme negative ({rate_pct:.4f}%) - strong squeeze!')
    elif rate < -0.08:
        return (9, 'BULLISH', f'Very negative ({rate_pct:.4f}%) - high squeeze potential')
    elif rate < -0.05:
        return (7, 'BULLISH', f'Negative ({rate_pct:.4f}%) - moderate squeeze')
    elif rate < -0.02:
        return (5, 'SLIGHTLY_BULLISH', f'Slightly negative ({rate_pct:.4f}%)')
    elif rate < 0:
        return (4, 'NEUTRAL', f'Near neutral negative ({rate_pct:.4f}%)')
    elif rate < 0.02:
        return (3, 'NEUTRAL', f'Near neutral positive ({rate_pct:.4f}%)')
    elif rate < 0.05:
        return (4, 'SLIGHTLY_BEARISH', f'Slightly positive ({rate_pct:.4f}%)')
    elif rate < 0.08:
        return (6, 'BEARISH', f'Positive ({rate_pct:.4f}%) - longs paying')
    elif rate < 0.1:
        return (8, 'BEARISH', f'High positive ({rate_pct:.4f}%) - longs overleveraged')
    else:
        return (10, 'VERY_BEARISH', f'Extreme positive ({rate_pct:.4f}%) - longs crushed!')

def score_aggression(agg_pct):
    if agg_pct >= 85:
        return (10, 'Extreme buying pressure!')
    elif agg_pct >= 80:
        return (9, 'Very strong buying')
    elif agg_pct >= 75:
        return (8, 'Strong buying')
    elif agg_pct >= 70:
        return (7, 'Good buying')
    elif agg_pct >= 65:
        return (6, 'Moderate buying')
    elif agg_pct >= 60:
        return (5, 'Slight buying bias')
    elif agg_pct >= 55:
        return (4, 'Balanced with slight buy bias')
    elif agg_pct >= 50:
        return (3, 'Balanced')
    elif agg_pct >= 45:
        return (2, 'Balanced with slight sell bias')
    elif agg_pct >= 40:
        return (1, 'Slight selling bias')
    else:
        return (0, 'Strong selling pressure!')

def score_volume_spike(current_vol, avg_vol):
    if avg_vol == 0:
        return (5, 'No average data')
    ratio = current_vol / avg_vol
    if ratio >= 5.0:
        return (10, f'Extreme spike ({ratio:.1f}x avg)')
    elif ratio >= 3.0:
        return (8, f'Strong spike ({ratio:.1f}x avg)')
    elif ratio >= 2.0:
        return (6, f'Moderate spike ({ratio:.1f}x avg)')
    elif ratio >= 1.5:
        return (4, f'Slight increase ({ratio:.1f}x avg)')
    elif ratio >= 0.8:
        return (3, f'Normal volume ({ratio:.1f}x avg)')
    else:
        return (1, f'Low volume ({ratio:.1f}x avg)')

def score_already_pumped(price_change_pct):
    if price_change_pct > 100:
        return (0, f'Already pumped +{price_change_pct:.0f}% - VERY HIGH RISK!')
    elif price_change_pct > 50:
        return (2, f'Already pumped +{price_change_pct:.0f}% - High risk')
    elif price_change_pct > 30:
        return (4, f'Pumped +{price_change_pct:.0f}% - Moderate risk')
    elif price_change_pct > 15:
        return (6, f'Some movement +{price_change_pct:.0f}% - Acceptable')
    elif price_change_pct > 5:
        return (8, f'Small move +{price_change_pct:.0f}% - Good entry')
    elif price_change_pct > 0:
        return (9, f'Fresh +{price_change_pct:.0f}% - Excellent entry')
    elif price_change_pct > -10:
        return (7, f'Slight dip {price_change_pct:.0f}% - Contrarian entry')
    else:
        return (3, f'Dumping {price_change_pct:.0f}% - Falling knife, caution')

async def full_analysis():
    symbol = 'BULLAUSDT'
    circulating_supply = 280000000
    print()
    print('=' * 70)
    print(f'  OI-HUNTER v2.0 | FULL ANALYSIS: {symbol}')
    print(f'  Circulating Supply: {circulating_supply:,} BULLA')
    print('=' * 70)
    results = {}
    async with MEXCRestClient() as client:
        print('\n--- 1. OI/MC RATIO (Weight: 20%) ---')
        try:
            oi_data = await client.get_open_interest(symbol)
            ticker = await client.get_ticker_24h(symbol)
            oi_value = float(oi_data['openInterestValue'])
            price = float(ticker['lastPrice'])
            market_cap = price * circulating_supply
            oi_mc_ratio = oi_value / market_cap if market_cap > 0 else 0
            score, interp = score_oi_mc_long(oi_mc_ratio)
            print(f'  Open Interest: ${oi_value:,.0f}')
            print(f'  Market Cap:    ${market_cap:,.0f}')
            print(f'  OI/MC Ratio:   {oi_mc_ratio:.4f} ({oi_mc_ratio * 100:.2f}%)')
            print(f'  Score:         {score}/10 - {interp}')
            results['oi_mc'] = {'score': score, 'weight': 0.2, 'ratio': oi_mc_ratio}
        except Exception as e:
            print(f'  [ERROR] {e}')
            results['oi_mc'] = {'score': 0, 'weight': 0.2}
        print('\n--- 2. FUNDING RATE (Weight: 15%) ---')
        try:
            fr_response = await client.get_funding_rate(symbol)
            fr_data = fr_response['data']
            funding_rate = float(fr_data['fundingRate'])
            score, direction, interp = score_funding(funding_rate)
            print(f'  Funding Rate:  {funding_rate * 100:.4f}%')
            print(f'  Direction:     {direction}')
            print(f'  Score:         {score}/10 - {interp}')
            results['funding'] = {'score': score, 'weight': 0.15, 'direction': direction}
        except Exception as e:
            print(f'  [ERROR] {e}')
            results['funding'] = {'score': 0, 'weight': 0.15}
        print('\n--- 3. BUY/SELL AGGRESSION (Weight: 15%) ---')
        try:
            trades = await client.get_recent_trades(symbol, limit=200)
            if trades:
                buy_vol = sum((float(t['qty']) for t in trades if not t['isBuyerMaker']))
                sell_vol = sum((float(t['qty']) for t in trades if t['isBuyerMaker']))
                total_vol = buy_vol + sell_vol
                agg_5m = buy_vol / total_vol * 100 if total_vol > 0 else 50
                score_5m, interp_5m = score_aggression(agg_5m)
                print(f'  [5M] Buy: {agg_5m:.1f}% | Sell: {100 - agg_5m:.1f}%')
                print(f'  [5M] Score: {score_5m}/10 - {interp_5m}')
                klines_60m = await client.get_klines(symbol, interval='60m', limit=2)
                agg_2h = 50
                score_2h = 3
                if klines_60m and len(klines_60m) >= 1 and all((len(k) >= 10 for k in klines_60m)):
                    total_vol_2h = sum((float(k[5]) for k in klines_60m))
                    total_taker_buy_2h = sum((float(k[9]) for k in klines_60m))
                    agg_2h = total_taker_buy_2h / total_vol_2h * 100 if total_vol_2h > 0 else 50
                    score_2h, interp_2h = score_aggression(agg_2h)
                    print(f'  [2H] Buy: {agg_2h:.1f}% | Sell: {100 - agg_2h:.1f}%')
                    print(f'  [2H] Score: {score_2h}/10 - {interp_2h}')
                else:
                    print(f'  [2H] Klines data incomplete, using default')
                shift = agg_5m - agg_2h
                shift_modifier = 0
                if abs(shift) > 15:
                    if shift > 0:
                        shift_modifier = 3
                        print(f'  [SHIFT] STRENGTHENING +{shift:.1f}% (5M > 2H) -> +3 bonus')
                    else:
                        shift_modifier = -3
                        print(f'  [SHIFT] WEAKENING {shift:.1f}% (5M < 2H) -> -3 penalty')
                combined_score = score_5m * 0.6 + score_2h * 0.4 + shift_modifier
                combined_score = max(0, min(10, combined_score))
                print(f'  Combined:      {combined_score:.1f}/10')
                results['aggression'] = {'score': combined_score, 'weight': 0.15, 'agg_5m': agg_5m, 'agg_2h': agg_2h}
            else:
                results['aggression'] = {'score': 0, 'weight': 0.15}
        except Exception as e:
            print(f'  [ERROR] {e}')
            results['aggression'] = {'score': 0, 'weight': 0.15}
        print('\n--- 4. OI NOWCAST (Weight: 15%) ---')
        print('  [N/A] Requires OI history (PostgreSQL)')
        print('  [N/A] Will be available after data collection starts')
        results['nowcast'] = {'score': 5, 'weight': 0.15, 'note': 'neutral default'}
        print('\n--- 5. WAVE ANALYZER (Weight: 10%) ---')
        try:
            klines_4h = await client.get_klines(symbol, interval='4h', limit=6)
            if klines_4h and len(klines_4h) >= 6:
                oldest_open = float(klines_4h[0][1])
                latest_close = float(klines_4h[-1][4])
                price_growth = (latest_close - oldest_open) / oldest_open * 100
                if price_growth > 80:
                    wave = 3
                    wave_score = 1
                    wave_interp = 'Wave 3 - Exhaustion, high risk!'
                elif price_growth > 30:
                    wave = 2
                    wave_score = 6
                    wave_interp = 'Wave 2 - Mid stage, caution'
                else:
                    wave = 1
                    wave_score = 9
                    wave_interp = 'Wave 1 - Early stage, good entry'
                print(f'  Price Growth (24h): {price_growth:+.1f}%')
                print(f'  Wave:          {wave}')
                print(f'  Score:         {wave_score}/10 - {wave_interp}')
                results['wave'] = {'score': wave_score, 'weight': 0.1, 'wave': wave}
            else:
                results['wave'] = {'score': 5, 'weight': 0.1}
        except Exception as e:
            print(f'  [ERROR] {e}')
            results['wave'] = {'score': 5, 'weight': 0.1}
        print('\n--- 6. LIQUIDATION ANALYZER (Weight: 10%) ---')
        try:
            all_trades = await client.get_recent_trades(symbol, limit=1000)
            if all_trades and len(all_trades) > 10:
                avg_size = sum((float(t['qty']) for t in all_trades)) / len(all_trades)
                large_trades = [t for t in all_trades if float(t['qty']) > avg_size * 3]
                large_buys = sum((float(t['qty']) for t in large_trades if not t['isBuyerMaker']))
                large_sells = sum((float(t['qty']) for t in large_trades if t['isBuyerMaker']))
                total_large = large_buys + large_sells
                if total_large > 0:
                    liq_buy_pct = large_buys / total_large * 100
                else:
                    liq_buy_pct = 50
                if liq_buy_pct > 70:
                    liq_score = 8
                    liq_interp = 'Large buys dominate - accumulation'
                elif liq_buy_pct > 55:
                    liq_score = 6
                    liq_interp = 'Slight buy dominance'
                elif liq_buy_pct > 45:
                    liq_score = 5
                    liq_interp = 'Balanced large trades'
                elif liq_buy_pct > 30:
                    liq_score = 3
                    liq_interp = 'Slight sell dominance'
                else:
                    liq_score = 1
                    liq_interp = 'Large sells dominate - distribution'
                print(f'  Large trades:  {len(large_trades)} (of {len(all_trades)})')
                print(f'  Large buys:    {liq_buy_pct:.1f}%')
                print(f'  Context:       N/A (need real-time liq data)')
                print(f'  Score:         {liq_score}/10 - {liq_interp}')
                results['liquidation'] = {'score': liq_score, 'weight': 0.1}
            else:
                results['liquidation'] = {'score': 5, 'weight': 0.1}
        except Exception as e:
            print(f'  [ERROR] {e}')
            results['liquidation'] = {'score': 5, 'weight': 0.1}
        print('\n--- 7. VOLUME SPIKE (Weight: 5%) ---')
        try:
            ticker_data = await client.get_ticker_24h(symbol)
            spot_vol_24h = float(ticker_data['quoteVolume'])
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as http:
                resp = await http.get('https://contract.mexc.com/api/v1/contract/ticker', params={'symbol': 'BULLA_USDT'})
                futures_data = resp.json()
                futures_vol = float(futures_data['data']['amount24'])
            total_vol = spot_vol_24h + futures_vol
            estimated_avg = 20000000
            vol_score, vol_interp = score_volume_spike(total_vol, estimated_avg)
            print(f'  Spot Volume:   ${spot_vol_24h:,.0f}')
            print(f'  Futures Volume:${futures_vol:,.0f}')
            print(f'  Total 24h:     ${total_vol:,.0f}')
            print(f'  Score:         {vol_score}/10 - {vol_interp}')
            results['volume'] = {'score': vol_score, 'weight': 0.05, 'total_vol': total_vol}
        except Exception as e:
            print(f'  [ERROR] {e}')
            results['volume'] = {'score': 5, 'weight': 0.05}
        print('\n--- 8. ALREADY PUMPED (Weight: 5%) ---')
        try:
            klines_4h = await client.get_klines(symbol, interval='4h', limit=6)
            if klines_4h and len(klines_4h) >= 6:
                oldest_open = float(klines_4h[0][1])
                latest_close = float(klines_4h[-1][4])
                price_change = (latest_close - oldest_open) / oldest_open * 100
                max_high = max((float(k[2]) for k in klines_4h))
                pullback = (max_high - latest_close) / max_high * 100
                pump_score, pump_interp = score_already_pumped(price_change)
                print(f'  24h Change:    {price_change:+.1f}%')
                print(f'  Pullback:      {pullback:.1f}% from high')
                print(f'  Score:         {pump_score}/10 - {pump_interp}')
                results['pumped'] = {'score': pump_score, 'weight': 0.05, 'change': price_change}
            else:
                results['pumped'] = {'score': 5, 'weight': 0.05}
        except Exception as e:
            print(f'  [ERROR] {e}')
            results['pumped'] = {'score': 5, 'weight': 0.05}
        print('\n--- 9. CONTEXT ANALYZER (Weight: 5%) ---')
        funding_dir = results.get('funding', {}).get('direction', 'NEUTRAL')
        agg_5m_val = results.get('aggression', {}).get('agg_5m', 50)
        conflicting = False
        if funding_dir in ['VERY_BEARISH', 'BEARISH'] and agg_5m_val > 65:
            conflicting = True
            ctx_score = 3
            ctx_interp = 'CONFLICTING: Funding bearish but buying strong'
        elif funding_dir in ['BULLISH'] and agg_5m_val < 45:
            conflicting = True
            ctx_score = 3
            ctx_interp = 'CONFLICTING: Funding bullish but selling dominates'
        else:
            ctx_score = 7
            ctx_interp = 'Signals aligned'
        print(f"  Conflicting:   {('YES' if conflicting else 'NO')}")
        print(f'  Score:         {ctx_score}/10 - {ctx_interp}')
        results['context'] = {'score': ctx_score, 'weight': 0.05}
    print()
    print('=' * 70)
    print('  FINAL WEIGHTED SCORE')
    print('=' * 70)
    total_score = 0
    print()
    print(f"  {'Analyzer':<25} {'Score':>6} {'Weight':>7} {'Weighted':>8}")
    print(f"  {'-' * 25} {'-' * 6} {'-' * 7} {'-' * 8}")
    analyzer_names = {'oi_mc': 'OI/MC Ratio', 'funding': 'Funding Rate', 'aggression': 'Aggression', 'nowcast': 'OI Nowcast', 'wave': 'Wave Analyzer', 'liquidation': 'Liquidation', 'volume': 'Volume Spike', 'pumped': 'Already Pumped', 'context': 'Context'}
    for key, name in analyzer_names.items():
        if key in results:
            s = results[key]['score']
            w = results[key]['weight']
            weighted = s * w
            total_score += weighted
            note = results[key].get('note', '')
            suffix = f' ({note})' if note else ''
            print(f'  {name:<25} {s:>5.1f} {w * 100:>6.0f}% {weighted:>7.2f}{suffix}')
    print(f"  {'-' * 25} {'-' * 6} {'-' * 7} {'-' * 8}")
    print(f"  {'TOTAL':<25} {'':>6} {'100%':>7} {total_score:>7.2f}")
    print()
    print('=' * 70)
    if total_score >= 7.5:
        signal = 'STRONG LONG'
        emoji_line = '[>>>] STRONG LONG SIGNAL'
    elif total_score >= 6.0:
        signal = 'MODERATE LONG'
        emoji_line = '[>>] MODERATE LONG SIGNAL'
    elif total_score >= 5.0:
        signal = 'WEAK LONG'
        emoji_line = '[>] WEAK LONG (caution)'
    elif total_score >= 4.0:
        signal = 'NEUTRAL'
        emoji_line = '[=] NEUTRAL - no clear signal'
    elif total_score >= 3.0:
        signal = 'WEAK SHORT'
        emoji_line = '[<] WEAK SHORT (caution)'
    else:
        signal = 'STRONG SHORT'
        emoji_line = '[<<<] STRONG SHORT SIGNAL'
    print(f'  SIGNAL: {emoji_line}')
    print(f'  SCORE:  {total_score:.2f}/10')
    print()
    print('  KEY FACTORS:')
    sorted_results = sorted(results.items(), key=lambda x: x[1]['score'] * x[1]['weight'], reverse=True)
    for key, data in sorted_results[:3]:
        name = analyzer_names.get(key, key)
        print(f"  [+] {name}: {data['score']:.1f}/10 (weight {data['weight'] * 100:.0f}%)")
    print()
    print('  WARNINGS:')
    if results.get('pumped', {}).get('change', 0) > 50:
        print(f"  [!] Already pumped +{results['pumped']['change']:.0f}% - HIGH correction risk")
    if results.get('funding', {}).get('direction', '') in ['VERY_BEARISH', 'BEARISH']:
        print(f'  [!] Funding Rate bearish - market expects downturn')
    if results.get('wave', {}).get('wave', 0) == 3:
        print(f'  [!] Wave 3 (exhaustion) - late stage, risky entry')
    if results.get('context', {}).get('score', 10) < 5:
        print(f'  [!] Conflicting signals detected')
    if results.get('oi_mc', {}).get('ratio', 0) < 0.1:
        print(f'  [!] OI/MC very low - insufficient leverage interest')
    print()
    print('=' * 70)
    print(f'  Disclaimer: Not financial advice. Use at your own risk.')
    print('=' * 70)
if __name__ == '__main__':
    asyncio.run(full_analysis())
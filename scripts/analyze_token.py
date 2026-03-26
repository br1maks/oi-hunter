import sys
import requests
from datetime import datetime, timezone, timedelta
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
MSK = timezone(timedelta(hours=3))
BASE = 'https://api.mexc.com'
TIMEOUT = 15

def api_get(url, params=None):
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
            return r
        except requests.exceptions.Timeout:
            print(f'  Timeout (attempt {attempt + 1}/3)')
            if attempt == 2:
                raise
    return None

def to_futures_symbol(symbol):
    s = symbol.upper().replace('/', '').replace('_', '')
    if s.endswith('USDT'):
        return s[:-4] + '_USDT'
    return s

def to_cg_query(symbol):
    s = symbol.upper().replace('/', '').replace('_', '')
    if s.endswith('USDT'):
        return s[:-4]
    return s

def score_oi_mc(ratio):
    if ratio < 0.1:
        return (2, 0, 'Too low')
    elif ratio < 0.16:
        return (5, 0, 'Low - building')
    elif ratio < 0.2:
        return (9, 0, 'Optimal lower')
    elif ratio < 0.26:
        return (10, 0, 'Optimal sweet spot')
    elif ratio < 0.3:
        return (9, 0, 'Optimal upper')
    elif ratio < 0.35:
        return (7, 2, 'Elevated')
    elif ratio < 0.4:
        return (6, 2, 'Elevated')
    elif ratio < 0.45:
        return (4, 4, 'High caution')
    elif ratio < 0.5:
        return (3, 6, 'High risk')
    elif ratio < 0.55:
        return (1, 8, 'Danger')
    elif ratio < 0.6:
        return (0, 9, 'Danger - exit longs')
    elif ratio < 0.65:
        return (0, 9, 'Extreme danger')
    elif ratio < 0.7:
        return (0, 10, 'Extreme')
    else:
        return (0, 10, 'CRITICAL')

def score_funding(rate):
    if rate < -0.005:
        return (10, 0, 'Ultra bearish squeeze')
    elif rate < -0.001:
        return (10, 0, 'Strong bearish squeeze')
    elif rate < -0.0008:
        return (9, 1, 'Bearish pressure')
    elif rate < -0.0005:
        return (7, 2, 'Moderate bearish')
    elif rate < -0.0002:
        return (5, 3, 'Slight bearish')
    elif rate < 0:
        return (4, 3, 'Neutral-bearish')
    elif rate < 0.0002:
        return (3, 4, 'Neutral')
    elif rate < 0.0005:
        return (3, 5, 'Neutral-bullish')
    elif rate < 0.0008:
        return (2, 6, 'Moderate bullish')
    elif rate < 0.001:
        return (1, 8, 'Bullish pressure')
    elif rate < 0.005:
        return (0, 10, 'Strong bullish')
    else:
        return (0, 10, 'Extreme bullish')

def score_agg(a):
    for t, s in [(85, 10), (80, 9), (75, 8), (70, 7), (65, 6), (60, 5), (55, 4), (50, 3), (45, 2), (40, 1)]:
        if a >= t:
            return s
    return 0

def main():
    if len(sys.argv) < 2:
        print('Usage: python scripts/analyze_token.py SYMBOL')
        print('Example: python scripts/analyze_token.py INUSDT')
        return
    raw_symbol = sys.argv[1].upper()
    futures_sym = to_futures_symbol(raw_symbol)
    cg_query = to_cg_query(raw_symbol)
    print('=' * 70)
    print(f'  {raw_symbol} — FULL ANALYSIS')
    print(f"  {datetime.now(MSK).strftime('%H:%M:%S %d.%m.%Y')} MSK")
    print(f'  Futures symbol: {futures_sym}')
    print('=' * 70)
    r = api_get(f'{BASE}/api/v1/contract/ticker', params={'symbol': futures_sym})
    resp = r.json()
    if not resp.get('success') or not resp.get('data'):
        print(f'\n  ERROR: Futures contract {futures_sym} not found!')
        print(f'  Response: {resp}')
        return
    ticker = resp['data']
    price = float(ticker['lastPrice'])
    hold_vol = float(ticker['holdVol'])
    vol24 = float(ticker['volume24'])
    amount24 = float(ticker['amount24'])
    high24 = float(ticker['high24Price'])
    low24 = float(ticker['lower24Price'])
    change24 = float(ticker['riseFallRate'])
    fair = float(ticker['fairPrice'])
    print(f'\n--- FUTURES TICKER ---')
    print(f'  Price:        ${price}')
    print(f'  Fair Price:   ${fair}')
    print(f'  24H High:     ${high24}')
    print(f'  24H Low:      ${low24}')
    print(f'  24H Change:   {change24 * 100:+.2f}%')
    print(f'  24H Volume:   {vol24:,.0f} contracts')
    print(f'  24H Amount:   ${amount24:,.0f}')
    print(f'  OI (contr):   {hold_vol:,.0f}')
    contract_size = 1
    try:
        r = api_get(f'{BASE}/api/v1/contract/detail', params={'symbol': futures_sym})
        detail = r.json().get('data', {})
        contract_size = float(detail.get('contractSize', 1))
        print(f'  Contract Size: {contract_size}')
    except:
        pass
    oi_usd = hold_vol * contract_size * price
    print(f'  OI (USD):     ${oi_usd:,.0f}')
    r = api_get(f'{BASE}/api/v1/contract/funding_rate/{futures_sym}')
    funding_data = r.json().get('data', {})
    funding_rate = float(funding_data.get('fundingRate', 0))
    next_settle = funding_data.get('nextSettleTime', 0)
    print(f'\n--- FUNDING RATE ---')
    print(f'  Rate:         {funding_rate * 100:+.4f}%')
    if next_settle:
        settle_dt = datetime.fromtimestamp(next_settle / 1000, tz=timezone.utc).astimezone(MSK)
        print(f"  Next settle:  {settle_dt.strftime('%H:%M MSK')}")
    r = api_get(f'{BASE}/api/v1/contract/deals/{futures_sym}', params={'limit': 100})
    deals = r.json().get('data', [])
    agg = 50.0
    buy_vol_usd = 0
    sell_vol_usd = 0
    if deals:
        for d in deals:
            vol_usd = float(d.get('v', 0)) * float(d.get('p', 0)) * contract_size
            if d.get('T') == 1:
                buy_vol_usd += vol_usd
            else:
                sell_vol_usd += vol_usd
        total = buy_vol_usd + sell_vol_usd
        agg = buy_vol_usd / total * 100 if total > 0 else 50
        first_ts = deals[-1]['t']
        last_ts = deals[0]['t']
        if first_ts > 1000000000000.0:
            first_ts /= 1000
            last_ts /= 1000
        first_t = datetime.fromtimestamp(first_ts, tz=timezone.utc).astimezone(MSK)
        last_t = datetime.fromtimestamp(last_ts, tz=timezone.utc).astimezone(MSK)
        print(f'\n--- AGGRESSION (futures deals) ---')
        print(f"  Period:       {first_t.strftime('%H:%M:%S')} - {last_t.strftime('%H:%M:%S')}")
        print(f'  Buy vol:      ${buy_vol_usd:,.0f}')
        print(f'  Sell vol:     ${sell_vol_usd:,.0f}')
        print(f'  Aggression:   {agg:.1f}% buy')
    print(f'\n--- MARKET CAP ---')
    mc = 0
    try:
        r = api_get('https://api.coingecko.com/api/v3/search', params={'query': cg_query})
        coins = r.json().get('coins', [])
        for c in coins[:5]:
            print(f"  CG: {c['name']} ({c['symbol']}) rank={c.get('market_cap_rank', 'N/A')}")
        best_coin = None
        for c in coins:
            if c['symbol'].upper() == cg_query.upper():
                best_coin = c
                break
        if not best_coin and coins:
            best_coin = coins[0]
        if best_coin:
            cg_id = best_coin['id']
            print(f"  Using: {best_coin['name']} ({cg_id})")
            r2 = api_get(f'https://api.coingecko.com/api/v3/coins/{cg_id}', params={'localization': 'false', 'tickers': 'false', 'community_data': 'false', 'developer_data': 'false'})
            md = r2.json().get('market_data', {})
            mc = md.get('market_cap', {}).get('usd', 0)
            circ = md.get('circulating_supply', 0)
            cg_price = md.get('current_price', {}).get('usd', 0)
            fdv = md.get('fully_diluted_valuation', {}).get('usd', 0)
            print(f'  CG Price:     ${cg_price}')
            print(f'  MC:           ${mc:,.0f}')
            print(f'  FDV:          ${fdv:,.0f}')
            print(f'  Circ Supply:  {circ:,.0f}')
            if cg_price and price:
                ratio = abs(cg_price - price) / max(cg_price, price)
                if ratio > 0.5:
                    print(f'  !! PRICE MISMATCH: CG ${cg_price} vs MEXC ${price} — likely wrong token!')
                    mc = 0
                else:
                    print(f'  Price match: {(1 - ratio) * 100:.0f}% — OK')
    except Exception as e:
        print(f'  Error: {e}')
    r = api_get(f'{BASE}/api/v1/contract/kline/{futures_sym}', params={'interval': 'Min15', 'limit': 40})
    klines = r.json().get('data', {})
    pump = 0
    dump = 0
    if klines and 'time' in klines:
        print(f'\n--- PRICE ACTION (15m futures) ---')
        times = klines['time']
        opens = klines['open']
        closes = klines['close']
        highs = klines['high']
        lows = klines['low']
        vols = klines['vol']
        print(f"{'Time':<10} {'Open':>10} {'Close':>10} {'High':>10} {'Low':>10} {'Vol':>10} {'Chg':>7}")
        print('-' * 70)
        peak_p = 0
        low_p = float('inf')
        start_p = float(opens[0])
        for i in range(len(times)):
            dt = datetime.fromtimestamp(times[i], tz=timezone.utc).astimezone(MSK)
            t = dt.strftime('%H:%M')
            o = float(opens[i])
            c = float(closes[i])
            h = float(highs[i])
            lo = float(lows[i])
            v = float(vols[i])
            chg = (c - o) / o * 100 if o > 0 else 0
            if h > peak_p:
                peak_p = h
            if lo < low_p:
                low_p = lo
            print(f'{t:<10} {o:>10.6f} {c:>10.6f} {h:>10.6f} {lo:>10.6f} {v:>10.0f} {chg:>+6.1f}%')
        pump = (peak_p - start_p) / start_p * 100 if start_p > 0 else 0
        dump = (price - peak_p) / peak_p * 100 if peak_p > 0 else 0
        range_pct = (peak_p - low_p) / low_p * 100 if low_p > 0 else 0
        print(f'\n  Start: ${start_p} | Peak: ${peak_p} | Low: ${low_p} | Now: ${price}')
        print(f'  Pump: {pump:+.1f}% | From peak: {dump:+.1f}% | Range: {range_pct:.1f}%')
    volume_spike_score = 0
    volume_spike_direction = None
    volume_ratio = 1.0
    price_change_1h = 0
    if klines and 'time' in klines and (len(klines['time']) >= 8):
        vols = [float(v) for v in klines['vol']]
        closes = [float(c) for c in klines['close']]
        opens = [float(o) for o in klines['open']]
        vol_1h = sum(vols[-4:])
        if len(vols) > 8:
            avg_vol_1h = sum(vols[:-4]) / (len(vols) - 4) * 4
        else:
            avg_vol_1h = sum(vols[:4]) / 4 * 4
        if avg_vol_1h > 0:
            volume_ratio = vol_1h / avg_vol_1h
        if len(closes) >= 4:
            price_4_ago = float(opens[-4])
            price_now = float(closes[-1])
            price_change_1h = (price_now - price_4_ago) / price_4_ago * 100 if price_4_ago > 0 else 0
        print(f'\n--- VOLUME SPIKE ---')
        print(f'  Vol 1H:       {vol_1h:,.0f} contracts')
        print(f'  Avg Vol 1H:   {avg_vol_1h:,.0f} contracts')
        print(f'  Ratio:        {volume_ratio:.1f}x')
        print(f'  Price chg 1H: {price_change_1h:+.1f}%')
        if volume_ratio >= 5.0:
            volume_spike_score = 10
        elif volume_ratio >= 3.0:
            volume_spike_score = 9
        elif volume_ratio >= 2.0:
            volume_spike_score = 7
        elif volume_ratio >= 1.5:
            volume_spike_score = 5
        else:
            volume_spike_score = 0
        if volume_spike_score > 0:
            if price_change_1h < -5:
                volume_spike_direction = 'BEARISH'
            elif price_change_1h > 5:
                volume_spike_direction = 'BULLISH'
            else:
                volume_spike_direction = 'UNCERTAIN'
            print(f'  Spike Score:  {volume_spike_score} | Direction: {volume_spike_direction}')
    print(f"\n{'=' * 70}")
    print(f'  SCORING')
    print(f"{'=' * 70}")
    total_long_w = 0
    total_short_w = 0
    total_weight = 0
    blocks_long = False
    blocks_short = False
    if mc and mc > 0:
        oi_mc = oi_usd / mc
        l, s, desc = score_oi_mc(oi_mc)
        print(f'\n  OI/MC: {oi_mc:.4f} — {desc}')
        print(f'    Long={l}, Short={s}' + (' BLOCKS LONG!' if oi_mc >= 0.55 else ''))
        total_long_w += l * 2.0
        total_short_w += s * 2.0
        total_weight += 2.0
        if oi_mc >= 0.55:
            blocks_long = True
    else:
        print(f'\n  OI/MC: N/A (OI=${oi_usd:,.0f}, MC unknown)')
    fl, fs, fdesc = score_funding(funding_rate)
    print(f'\n  FUNDING: {funding_rate * 100:+.4f}% — {fdesc}')
    print(f'    Long={fl}, Short={fs}' + (' BLOCKS LONG!' if funding_rate >= 0.001 else ''))
    total_long_w += fl * 1.0
    total_short_w += fs * 1.0
    total_weight += 1.0
    if funding_rate >= 0.001:
        blocks_long = True
    al = score_agg(agg)
    ash = score_agg(100 - agg)
    print(f'\n  AGGRESSION: {agg:.1f}%')
    print(f'    Long={al}, Short={ash}' + (' BLOCKS LONG!' if agg < 25 else '') + (' BLOCKS SHORT!' if agg > 75 else ''))
    total_long_w += al * 1.5
    total_short_w += ash * 1.5
    total_weight += 1.5
    if agg < 25:
        blocks_long = True
    if agg > 75:
        blocks_short = True
    if pump > 200:
        pl, ps = (0, 10)
        blocks_long = True
    elif pump > 100:
        pl, ps = (0, 9)
        blocks_long = True
    elif pump > 50:
        pl, ps = (1, 8)
    elif pump > 30:
        pl, ps = (3, 6)
    elif pump > 15:
        pl, ps = (5, 4)
    else:
        pl, ps = (6, 3)
    print(f'\n  ALREADY PUMPED: {pump:+.1f}%')
    print(f'    Long={pl}, Short={ps}' + (' BLOCKS LONG!' if pump > 100 else ''))
    total_long_w += pl * 0.5
    total_short_w += ps * 0.5
    total_weight += 0.5
    if volume_spike_score > 0 and volume_spike_direction != 'UNCERTAIN':
        if volume_spike_direction == 'BEARISH':
            vl, vs = (0, volume_spike_score)
            if volume_ratio >= 2.0:
                blocks_long = True
        else:
            vl, vs = (volume_spike_score, 0)
            if volume_ratio >= 2.0:
                blocks_short = True
        print(f'\n  VOLUME SPIKE: {volume_ratio:.1f}x {volume_spike_direction}')
        print(f'    Long={vl}, Short={vs}' + (' BLOCKS LONG!' if volume_spike_direction == 'BEARISH' and volume_ratio >= 2.0 else '') + (' BLOCKS SHORT!' if volume_spike_direction == 'BULLISH' and volume_ratio >= 2.0 else ''))
        total_long_w += vl * 1.0
        total_short_w += vs * 1.0
        total_weight += 1.0
    elif volume_spike_score > 0:
        print(f'\n  VOLUME SPIKE: {volume_ratio:.1f}x (direction UNCERTAIN - not scored)')
    if total_weight > 0:
        avg_long = total_long_w / total_weight
        avg_short = total_short_w / total_weight
    else:
        avg_long = avg_short = 0
    print(f"\n{'=' * 70}")
    print(f'  WEIGHTED SCORE (max 10)')
    print(f"{'=' * 70}")
    print(f'\n  LONG:  {avg_long:.1f}/10')
    print(f'  SHORT: {avg_short:.1f}/10')
    if blocks_long:
        print(f'\n  !! LONG BLOCKED !!')
    if blocks_short:
        print(f'\n  !! SHORT BLOCKED !!')
    print(f'\n--- VERDICT ---')
    if blocks_long and avg_short >= 7:
        print(f'  STRONG SHORT signal ({avg_short:.1f}/10)')
    elif blocks_long:
        print(f'  Long blocked. Short weak ({avg_short:.1f}/10) — SKIP')
    elif blocks_short and avg_long >= 7:
        print(f'  STRONG LONG signal ({avg_long:.1f}/10)')
    elif blocks_short:
        print(f'  Short blocked. Long weak ({avg_long:.1f}/10) — SKIP')
    elif avg_long >= 7 and avg_long > avg_short + 2:
        print(f'  LONG signal ({avg_long:.1f} vs {avg_short:.1f})')
    elif avg_short >= 7 and avg_short > avg_long + 2:
        print(f'  SHORT signal ({avg_short:.1f} vs {avg_long:.1f})')
    elif abs(avg_long - avg_short) < 1.5:
        print(f'  NO CLEAR SIGNAL (Long {avg_long:.1f} ~ Short {avg_short:.1f})')
    else:
        direction = 'LONG' if avg_long > avg_short else 'SHORT'
        score = max(avg_long, avg_short)
        print(f'  Weak {direction} lean ({score:.1f}/10) — not enough for entry')
if __name__ == '__main__':
    main()
import requests
from datetime import datetime, timezone, timedelta
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
MSK = timezone(timedelta(hours=3))
BASE = 'https://api.mexc.com'
SYMBOL = 'ECHELON_USDT'
TIMEOUT = 15

def api_get(url, params=None):
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
            return r
        except requests.exceptions.Timeout:
            print(f"  Timeout (attempt {attempt + 1}/3): {url.split('/')[-1]}")
            if attempt == 2:
                raise
    return None

def main():
    print('=' * 70)
    print(f'  ECHELONUSDT — FULL ANALYSIS')
    print(f"  {datetime.now(MSK).strftime('%H:%M:%S %d.%m.%Y')} MSK")
    print('=' * 70)
    r = api_get(f'{BASE}/api/v1/contract/ticker', params={'symbol': SYMBOL})
    ticker = r.json()['data']
    price = float(ticker['lastPrice'])
    hold_vol = float(ticker['holdVol'])
    vol24 = float(ticker['volume24'])
    amount24 = float(ticker['amount24'])
    high24 = float(ticker['high24Price'])
    low24 = float(ticker['lower24Price'])
    change24 = float(ticker['riseFallRate'])
    fair = float(ticker['fairPrice'])
    print(f'\n--- FUTURES TICKER ---')
    print(f'  Price:      ${price:.4f}')
    print(f'  Fair Price: ${fair:.4f}')
    print(f'  24H High:   ${high24:.4f}')
    print(f'  24H Low:    ${low24:.4f}')
    print(f'  24H Change: {change24 * 100:+.2f}%')
    print(f'  24H Volume: {vol24:,.0f} contracts')
    print(f'  24H Amount: ${amount24:,.0f}')
    print(f'  OI (contracts): {hold_vol:,.0f}')
    contract_size = 1
    try:
        r = api_get(f'{BASE}/api/v1/contract/detail', params={'symbol': SYMBOL})
        detail = r.json()['data']
        contract_size = float(detail.get('contractSize', 1))
        print(f'  Contract Size: {contract_size}')
    except:
        print(f'  Contract Size: {contract_size} (default)')
    oi_usd = hold_vol * contract_size * price
    print(f'  OI (USD):   ${oi_usd:,.0f}')
    r = api_get(f'{BASE}/api/v1/contract/funding_rate/{SYMBOL}')
    funding_data = r.json()['data']
    funding_rate = float(funding_data['fundingRate'])
    next_settle = funding_data.get('nextSettleTime', 0)
    print(f'\n--- FUNDING RATE ---')
    print(f'  Rate:       {funding_rate * 100:+.4f}%')
    if next_settle:
        settle_dt = datetime.fromtimestamp(next_settle / 1000, tz=timezone.utc).astimezone(MSK)
        print(f"  Next settle: {settle_dt.strftime('%H:%M MSK')}")
    r = api_get(f'{BASE}/api/v1/contract/deals/{SYMBOL}', params={'limit': 100})
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
        print(f'\n--- AGGRESSION (futures trades) ---')
        print(f"  Period:    {first_t.strftime('%H:%M:%S')} - {last_t.strftime('%H:%M:%S')}")
        print(f'  Buy vol:   ${buy_vol_usd:,.0f}')
        print(f'  Sell vol:  ${sell_vol_usd:,.0f}')
        print(f'  Aggression: {agg:.1f}%')
    print(f'\n--- MARKET CAP ---')
    mc = 0
    try:
        r = api_get('https://api.coingecko.com/api/v3/search', params={'query': 'echelon'})
        coins = r.json().get('coins', [])
        for c in coins[:3]:
            print(f"  CG found: {c['name']} ({c['symbol']}) rank={c.get('market_cap_rank', 'N/A')}")
        if coins:
            cg_id = coins[0]['id']
            r2 = api_get(f'https://api.coingecko.com/api/v3/coins/{cg_id}', params={'localization': 'false', 'tickers': 'false', 'community_data': 'false', 'developer_data': 'false'})
            md = r2.json().get('market_data', {})
            mc = md.get('market_cap', {}).get('usd', 0)
            circ = md.get('circulating_supply', 0)
            cg_price = md.get('current_price', {}).get('usd', 0)
            print(f'  CG Price:  ${cg_price}')
            print(f'  MC:        ${mc:,.0f}')
            print(f'  Circ:      {circ:,.0f}')
            if cg_price and price:
                ratio = abs(cg_price - price) / max(cg_price, price)
                if ratio > 0.5:
                    print(f'  !! WRONG TOKEN: CG ${cg_price} vs MEXC ${price:.4f}')
                    mc = 0
    except Exception as e:
        print(f'  Error: {e}')
    r = api_get(f'{BASE}/api/v1/contract/kline/{SYMBOL}', params={'interval': 'Min5', 'limit': 30})
    klines = r.json().get('data', {})
    pump = 0
    if klines and 'time' in klines:
        print(f'\n--- PRICE ACTION (5m futures) ---')
        times = klines['time']
        opens = klines['open']
        closes = klines['close']
        highs = klines['high']
        lows = klines['low']
        vols = klines['vol']
        fmt = '{:<10} {:>10} {:>10} {:>10} {:>10} {:>10} {:>7}'
        print(fmt.format('Time', 'Open', 'Close', 'High', 'Low', 'Vol', 'Chg'))
        print('-' * 70)
        peak_p = 0
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
            marker = ''
            if dt.hour == 17 and 10 <= dt.minute <= 14:
                marker = ' <<<'
            print(f'{t:<10} {o:>10.4f} {c:>10.4f} {h:>10.4f} {lo:>10.4f} {v:>10.0f} {chg:>+6.1f}%{marker}')
        pump = (peak_p - start_p) / start_p * 100 if start_p > 0 else 0
        dump = (price - peak_p) / peak_p * 100 if peak_p > 0 else 0
        print(f'\n  Start: ${start_p:.4f} | Peak: ${peak_p:.4f} | Now: ${price:.4f}')
        print(f'  Pump: {pump:+.0f}% | Dump from peak: {dump:+.0f}%')
    print(f"\n{'=' * 70}")
    print(f'  SCORING ALL ANALYZERS')
    print(f"{'=' * 70}")
    if mc and mc > 0:
        oi_mc = oi_usd / mc
        print(f'\n  OI/MC RATIO: {oi_mc:.4f}')
        if oi_mc < 0.1:
            l, s = (2, 0)
        elif oi_mc < 0.16:
            l, s = (5, 0)
        elif oi_mc < 0.2:
            l, s = (9, 0)
        elif oi_mc < 0.26:
            l, s = (10, 0)
        elif oi_mc < 0.3:
            l, s = (9, 0)
        elif oi_mc < 0.35:
            l, s = (7, 2)
        elif oi_mc < 0.4:
            l, s = (6, 2)
        elif oi_mc < 0.45:
            l, s = (4, 4)
        elif oi_mc < 0.5:
            l, s = (3, 6)
        elif oi_mc < 0.55:
            l, s = (1, 8)
        elif oi_mc < 0.6:
            l, s = (0, 9)
        elif oi_mc < 0.65:
            l, s = (0, 9)
        elif oi_mc < 0.7:
            l, s = (0, 10)
        else:
            l, s = (0, 10)
        blocks = 'BLOCKS LONG!' if oi_mc >= 0.55 else ''
        print(f'    Long={l}, Short={s} {blocks}')
    else:
        print(f'\n  OI/MC: Cannot calc (OI=${oi_usd:,.0f}, MC=unknown)')
    print(f'\n  FUNDING: {funding_rate * 100:+.4f}%')
    if funding_rate < -0.005:
        fl, fs = (10, 0)
    elif funding_rate < -0.001:
        fl, fs = (10, 0)
    elif funding_rate < -0.0008:
        fl, fs = (9, 1)
    elif funding_rate < -0.0005:
        fl, fs = (7, 2)
    elif funding_rate < -0.0002:
        fl, fs = (5, 3)
    elif funding_rate < 0:
        fl, fs = (4, 3)
    elif funding_rate < 0.0002:
        fl, fs = (3, 4)
    elif funding_rate < 0.0005:
        fl, fs = (3, 5)
    elif funding_rate < 0.0008:
        fl, fs = (2, 6)
    elif funding_rate < 0.001:
        fl, fs = (1, 8)
    elif funding_rate < 0.005:
        fl, fs = (0, 10)
    else:
        fl, fs = (0, 10)
    print(f'    Long={fl}, Short={fs}')

    def score_agg(a):
        for thresh, sc in [(85, 10), (80, 9), (75, 8), (70, 7), (65, 6), (60, 5), (55, 4), (50, 3), (45, 2), (40, 1)]:
            if a >= thresh:
                return sc
        return 0
    print(f'\n  AGGRESSION: {agg:.1f}%')
    al = score_agg(agg)
    ash = score_agg(100 - agg)
    print(f'    Long={al}, Short={ash}')
    print(f'\n  ALREADY PUMPED: {pump:+.0f}%')
    if pump > 200:
        print(f'    Long=0 BLOCKED | Short=10 - EXTREME')
    elif pump > 100:
        print(f'    Long=0 BLOCKED | Short=9')
    elif pump > 50:
        print(f'    Long=1 | Short=8')
    elif pump > 30:
        print(f'    Long=3 | Short=6')
    else:
        print(f'    Moderate, no blocking')
    print(f"\n{'=' * 70}")
    print(f'  VERDICT')
    print(f"{'=' * 70}")
    blocks_long = pump > 100
    if mc and mc > 0 and (oi_usd / mc >= 0.55):
        blocks_long = True
    if funding_rate >= 0.001:
        blocks_long = True
    if blocks_long:
        print(f'\n  >> LONG BLOCKED - do not open long positions')
    print(f'  >> This is a pump & dump token')
    print(f'  >> Peak +{pump:.0f}%, currently -{abs(dump):.0f}% from peak')
if __name__ == '__main__':
    main()
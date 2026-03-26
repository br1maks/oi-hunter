import asyncio
import sys
sys.path.insert(0, 'D:/oi-hunter')
import httpx
from src.api.mexc_client import MEXCRestClient
from src.models.market_data import MarketData
from src.analyzers.oi_mc_analyzer import OIMCAnalyzer
from src.analyzers.funding_rate_analyzer import FundingRateAnalyzer

async def analyze_token():
    symbol = 'CLAWNCHUSDT'
    print()
    print('=' * 70)
    print(f'  OI-HUNTER v2.0 | LIVE ANALYSIS: {symbol}')
    print('=' * 70)
    async with MEXCRestClient() as client:
        print('\n--- FETCHING DATA FROM MEXC ---')
        try:
            ticker = await client.get_ticker_24h(symbol)
            price = float(ticker['lastPrice'])
            volume_24h = float(ticker['quoteVolume'])
            price_change_24h = float(ticker.get('priceChangePercent', 0))
            print(f'  Price:        ${price}')
            print(f'  Volume 24h:   ${volume_24h:,.0f}')
            print(f'  Change 24h:   {price_change_24h:+.2f}%')
        except Exception as e:
            print(f'  [ERROR] Ticker: {e}')
            return
        oi_value = 0
        try:
            oi_data = await client.get_open_interest(symbol)
            oi_value = float(oi_data['openInterestValue'])
            contract_size = float(oi_data['contractSize'])
            hold_vol = float(oi_data['openInterest'])
            print(f'  OI (USD):     ${oi_value:,.0f}')
            print(f'  Contract Size: {contract_size}')
            print(f'  Hold Vol:     {hold_vol:,.0f}')
        except Exception as e:
            print(f'  [ERROR] OI: {e}')
        funding_rate = 0
        try:
            fr_response = await client.get_funding_rate(symbol)
            fr_data = fr_response['data']
            funding_rate = float(fr_data['fundingRate'])
            print(f'  Funding Rate: {funding_rate * 100:+.4f}%')
        except Exception as e:
            print(f'  [ERROR] Funding: {e}')
        futures_vol = 0
        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                futures_sym = 'CLAWNCH_USDT'
                resp = await http.get('https://contract.mexc.com/api/v1/contract/ticker', params={'symbol': futures_sym})
                ft = resp.json()
                if ft.get('success'):
                    ftd = ft['data']
                    futures_vol = float(ftd.get('amount24', 0))
                    print(f'  Futures Vol:  ${futures_vol:,.0f}')
        except Exception as e:
            print(f'  [ERROR] Futures ticker: {e}')
        agg_5m = 50.0
        buy_vol = 0.0
        sell_vol = 0.0
        try:
            trades = await client.get_recent_trades(symbol, limit=500)
            if trades:
                buy_vol = sum((float(t['qty']) * float(t['price']) for t in trades if not t['isBuyerMaker']))
                sell_vol = sum((float(t['qty']) * float(t['price']) for t in trades if t['isBuyerMaker']))
                total_vol = buy_vol + sell_vol
                agg_5m = buy_vol / total_vol * 100 if total_vol > 0 else 50
                print(f'  Aggression 5M: {agg_5m:.1f}% buy | {100 - agg_5m:.1f}% sell')
        except Exception as e:
            print(f'  [ERROR] Trades: {e}')
        agg_2h = 50.0
        try:
            klines = await client.get_klines(symbol, interval='60m', limit=2)
            if klines and len(klines) >= 1 and all((len(k) >= 10 for k in klines)):
                tv = sum((float(k[5]) for k in klines))
                tb = sum((float(k[9]) for k in klines))
                agg_2h = tb / tv * 100 if tv > 0 else 50
                print(f'  Aggression 2H: {agg_2h:.1f}% buy | {100 - agg_2h:.1f}% sell')
        except Exception as e:
            print(f'  [ERROR] Klines 2H: {e}')
        price_change_calc = 0
        try:
            klines_4h = await client.get_klines(symbol, interval='4h', limit=6)
            if klines_4h and len(klines_4h) >= 2:
                oldest = float(klines_4h[0][1])
                latest = float(klines_4h[-1][4])
                price_change_calc = (latest - oldest) / oldest * 100
                print(f'  Change ~24h:  {price_change_calc:+.1f}%')
        except Exception as e:
            pass
        print('\n--- MARKET CAP ---')
        mc_usd = 0
        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                resp = await http.get('https://api.coingecko.com/api/v3/search', params={'query': 'clawnch'})
                search = resp.json()
                coins = search.get('coins', [])
                if coins:
                    coin_id = coins[0]['id']
                    print(f'  CoinGecko ID: {coin_id}')
                    resp2 = await http.get(f'https://api.coingecko.com/api/v3/coins/{coin_id}', params={'localization': 'false', 'tickers': 'false', 'community_data': 'false', 'developer_data': 'false'})
                    coin_data = resp2.json()
                    mc_usd = coin_data.get('market_data', {}).get('market_cap', {}).get('usd', 0) or 0
                    circ = coin_data.get('market_data', {}).get('circulating_supply', 0) or 0
                    if mc_usd:
                        print(f'  Market Cap:   ${mc_usd:,.0f}')
                    if circ:
                        print(f'  Circ Supply:  {circ:,.0f}')
                else:
                    print('  CoinGecko: not found')
        except Exception as e:
            print(f'  CoinGecko error: {e}')
        if mc_usd == 0:
            mc_usd = volume_24h * 3
            print(f'  MC estimated: ${mc_usd:,.0f} (fallback: volume * 3)')
        oi_mc = oi_value / mc_usd if mc_usd > 0 else 0
        print(f'  OI/MC Ratio:  {oi_mc:.4f} ({oi_mc * 100:.2f}%)')
        print()
        print('=' * 70)
        print('  ANALYZER RESULTS')
        print('=' * 70)
        market_data = MarketData(symbol=symbol, price=price, volume_24h=volume_24h, open_interest_usd=oi_value, market_cap_usd=max(mc_usd, 1), funding_rate=funding_rate, price_change_24h=price_change_24h, buy_volume_5m=buy_vol, sell_volume_5m=sell_vol)
        oi_analyzer = OIMCAnalyzer(weight=2.0)
        r_oi = oi_analyzer.analyze(market_data)
        if r_oi:
            print(f'\n  1. {r_oi.analyzer_name} (weight: 20%)')
            print(f'     OI/MC:  {oi_mc:.4f}')
            print(f'     Long:   {r_oi.long_score}/10')
            print(f'     Short:  {r_oi.short_score}/10')
            print(f'     {r_oi.reasoning}')
            if r_oi.blocks_long:
                print(f'     >>> LONG BLOCKED <<<')
        fr_analyzer = FundingRateAnalyzer(weight=1.0)
        r_fr = fr_analyzer.analyze(market_data)
        if r_fr:
            print(f'\n  2. {r_fr.analyzer_name} (weight: 14%)')
            print(f'     Rate:   {funding_rate * 100:+.4f}%')
            print(f'     Long:   {r_fr.long_score}/10')
            print(f'     Short:  {r_fr.short_score}/10')
            print(f'     {r_fr.reasoning}')
            if r_fr.blocks_long:
                print(f'     >>> LONG BLOCKED <<<')
        print(f'\n  3. Aggression (manual scoring)')
        print(f'     5M: {agg_5m:.1f}% buy')
        print(f'     2H: {agg_2h:.1f}% buy')
        shift = agg_5m - agg_2h
        if abs(shift) > 15:
            direction = 'STRENGTHENING' if shift > 0 else 'WEAKENING'
            print(f'     SHIFT: {shift:+.1f}% ({direction})')
        else:
            print(f'     Shift: {shift:+.1f}% (no significant shift)')

        def score_agg(agg):
            if agg >= 85:
                return 10
            elif agg >= 80:
                return 9
            elif agg >= 75:
                return 8
            elif agg >= 70:
                return 7
            elif agg >= 65:
                return 6
            elif agg >= 60:
                return 5
            elif agg >= 55:
                return 4
            elif agg >= 50:
                return 3
            elif agg >= 45:
                return 2
            elif agg >= 40:
                return 1
            else:
                return 0
        s5 = score_agg(agg_5m)
        s2 = score_agg(agg_2h)
        shift_mod = 0
        if abs(shift) > 15:
            shift_mod = 3 if shift > 0 else -3
        combined_agg = max(0, min(10, s5 * 0.6 + s2 * 0.4 + shift_mod))
        print(f'     Score 5M: {s5}/10, Score 2H: {s2}/10')
        print(f'     Combined: {combined_agg:.1f}/10 (long)')
        print(f'\n  4. Already Pumped')
        print(f'     24h change: {price_change_24h:+.2f}%')
        if price_change_24h > 50:
            pump_score = 2
        elif price_change_24h > 30:
            pump_score = 4
        elif price_change_24h > 15:
            pump_score = 6
        elif price_change_24h > 5:
            pump_score = 8
        elif price_change_24h > 0:
            pump_score = 9
        elif price_change_24h > -10:
            pump_score = 7
        else:
            pump_score = 3
        print(f'     Score: {pump_score}/10 (long)')
        print(f'\n  5. Volume')
        print(f'     Total: ${volume_24h + futures_vol:,.0f}')
        print()
        print('=' * 70)
        print('  WEIGHTED SCORE (2 real analyzers + 2 manual)')
        print('=' * 70)
        weights = {'OI/MC': (r_oi.long_score if r_oi else 0, r_oi.short_score if r_oi else 0, 0.2), 'Funding': (r_fr.long_score if r_fr else 0, r_fr.short_score if r_fr else 0, 0.15), 'Aggression': (combined_agg, 10 - combined_agg, 0.15), 'Already Pumped': (pump_score, 10 - pump_score, 0.05)}
        total_w = sum((w[2] for w in weights.values()))
        long_total = sum((s[0] * s[2] for s in weights.values())) / total_w
        short_total = sum((s[1] * s[2] for s in weights.values())) / total_w
        print()
        print(f"  {'Analyzer':<20} {'Long':>6} {'Short':>6} {'Weight':>7}")
        print(f"  {'-' * 20} {'-' * 6} {'-' * 6} {'-' * 7}")
        for name, (ls, ss, w) in weights.items():
            print(f'  {name:<20} {ls:>5.1f} {ss:>5.1f} {w * 100:>6.0f}%')
        print(f"  {'-' * 20} {'-' * 6} {'-' * 6} {'-' * 7}")
        print(f"  {'WEIGHTED TOTAL':<20} {long_total:>5.1f} {short_total:>5.1f} {total_w * 100:>6.0f}%")
        blocked_long = r_oi and r_oi.blocks_long or (r_fr and r_fr.blocks_long)
        blocked_short = r_oi and r_oi.blocks_short or (r_fr and r_fr.blocks_short)
        print()
        if blocked_long:
            print('  >>> LONG BLOCKED by analyzer(s) <<<')
        if blocked_short:
            print('  >>> SHORT BLOCKED by analyzer(s) <<<')
        if long_total >= 7.0 and (not blocked_long):
            print(f'  SIGNAL: STRONG LONG ({long_total:.1f}/10)')
        elif long_total >= 5.5 and (not blocked_long):
            print(f'  SIGNAL: MODERATE LONG ({long_total:.1f}/10)')
        elif short_total >= 7.0 and (not blocked_short):
            print(f'  SIGNAL: STRONG SHORT ({short_total:.1f}/10)')
        elif short_total >= 5.5 and (not blocked_short):
            print(f'  SIGNAL: MODERATE SHORT ({short_total:.1f}/10)')
        else:
            print(f'  SIGNAL: NO CLEAR SIGNAL (Long: {long_total:.1f}, Short: {short_total:.1f})')
        print()
        print('  CONTEXT:')
        if r_fr and abs(funding_rate) >= 0.005:
            print(f'  [!] Ultra-extreme funding - need aggression confirmation')
        if oi_mc > 0.55:
            print(f'  [!] High OI/MC - overleveraged market')
        if agg_5m > 70:
            print(f'  [+] Strong buy aggression 5M')
        elif agg_5m < 40:
            print(f'  [-] Strong sell aggression 5M')
        if abs(shift) > 15:
            print(f'  [!] Momentum shift detected: {direction}')
        print()
if __name__ == '__main__':
    asyncio.run(analyze_token())
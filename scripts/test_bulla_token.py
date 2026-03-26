import asyncio
import sys
sys.path.insert(0, 'D:/oi-hunter')
from src.api.mexc_client import MEXCRestClient
from datetime import datetime

async def test_bulla_metrics():
    symbol = 'BULLAUSDT'
    print('\n' + '#' * 70)
    print(f'# TESTING TOKEN: {symbol}')
    print('#' * 70)
    async with MEXCRestClient() as client:
        print('\n' + '=' * 70)
        print('1. OPEN INTEREST (для OI/MC Ratio)')
        print('=' * 70)
        try:
            oi_data = await client.get_open_interest(symbol)
            oi_contracts = float(oi_data['openInterest'])
            oi_value_usd = float(oi_data['openInterestValue'])
            price = float(oi_data['lastPrice'])
            print(f"[OK] Symbol: {oi_data['symbol']}")
            print(f'[OK] Open Interest: {oi_contracts:,.0f} contracts')
            print(f'[OK] OI Value: ${oi_value_usd:,.2f} USD')
            print(f'[OK] Price: ${price}')
            print(f"[OK] Timestamp: {datetime.fromtimestamp(oi_data['timestamp'] / 1000)}")
            estimated_mc = price * 1000000000
            oi_mc_ratio = oi_value_usd / estimated_mc if estimated_mc > 0 else 0
            print(f'\n[ESTIMATE] Market Cap: ${estimated_mc:,.0f} (нужен CoinGecko)')
            print(f'[ESTIMATE] OI/MC Ratio: {oi_mc_ratio:.4f}')
            if oi_mc_ratio > 0.7:
                print(f'[WARNING] OI/MC > 0.70 - EXTREME DANGER ZONE!')
            elif oi_mc_ratio > 0.3:
                print(f'[WARNING] OI/MC > 0.30 - High risk')
            elif oi_mc_ratio >= 0.16:
                print(f'[OK] OI/MC in optimal zone (0.16-0.30)')
        except Exception as e:
            print(f'[ERROR] Open Interest: {type(e).__name__}: {e}')
        print('\n' + '=' * 70)
        print('2. FUNDING RATE')
        print('=' * 70)
        try:
            fr_response = await client.get_funding_rate(symbol)
            if fr_response.get('success'):
                fr_data = fr_response['data']
                funding_rate = float(fr_data['fundingRate'])
                funding_rate_pct = funding_rate * 100
                print(f"[OK] Symbol: {fr_data['symbol']}")
                print(f'[OK] Funding Rate: {funding_rate_pct:.4f}%')
                print(f'[OK] Annual Rate: {funding_rate_pct * 365 * 3:.2f}% (3x per day)')
                print(f"[OK] Next Settlement: {datetime.fromtimestamp(fr_data['nextSettleTime'] / 1000)}")
                if abs(funding_rate_pct) > 0.1:
                    print(f'[WARNING] Funding Rate > 0.1% - High leverage/speculation')
                elif abs(funding_rate_pct) < 0.01:
                    print(f'[OK] Funding Rate low - Balanced market')
            else:
                print(f'[ERROR] Funding Rate response: {fr_response}')
        except Exception as e:
            print(f'[ERROR] Funding Rate: {type(e).__name__}: {e}')
        print('\n' + '=' * 70)
        print('3. AGGRESSION 5M (Buy/Sell Pressure)')
        print('=' * 70)
        try:
            trades = await client.get_recent_trades(symbol, limit=100)
            if trades and len(trades) > 0:
                buy_volume = sum((float(t['qty']) for t in trades if not t['isBuyerMaker']))
                sell_volume = sum((float(t['qty']) for t in trades if t['isBuyerMaker']))
                total_volume = buy_volume + sell_volume
                buy_ratio = buy_volume / total_volume if total_volume > 0 else 0.5
                sell_ratio = sell_volume / total_volume if total_volume > 0 else 0.5
                print(f'[OK] Trades analyzed: {len(trades)}')
                print(f'[OK] Aggressor Buys: {buy_volume:.4f} ({buy_ratio * 100:.1f}%)')
                print(f'[OK] Aggressor Sells: {sell_volume:.4f} ({sell_ratio * 100:.1f}%)')
                print(f'[OK] Buy/Sell Ratio: {buy_volume / sell_volume:.2f}' if sell_volume > 0 else '[OK] Buy/Sell Ratio: inf')
                if buy_ratio > 0.65:
                    print(f'[SIGNAL] Strong BUY pressure! ({buy_ratio * 100:.1f}% buys)')
                elif sell_ratio > 0.65:
                    print(f'[WARNING] Strong SELL pressure! ({sell_ratio * 100:.1f}% sells)')
                else:
                    print(f'[OK] Balanced buy/sell pressure')
            else:
                print('[WARNING] No trades data')
        except Exception as e:
            print(f'[ERROR] Aggression 5M: {type(e).__name__}: {e}')
        print('\n' + '=' * 70)
        print('4. AGGRESSION 2H (2x 60m candles)')
        print('=' * 70)
        try:
            klines_60m = await client.get_klines(symbol, interval='60m', limit=2)
            if klines_60m and len(klines_60m) >= 2:
                if all((len(k) >= 10 for k in klines_60m)):
                    total_volume = sum((float(k[5]) for k in klines_60m))
                    total_taker_buy = sum((float(k[9]) for k in klines_60m))
                    total_taker_sell = total_volume - total_taker_buy
                    buy_ratio_2h = total_taker_buy / total_volume if total_volume > 0 else 0.5
                    print(f'[OK] 2H Volume: {total_volume:.4f}')
                    print(f'[OK] Taker Buys: {total_taker_buy:.4f} ({buy_ratio_2h * 100:.1f}%)')
                    print(f'[OK] Taker Sells: {total_taker_sell:.4f} ({(1 - buy_ratio_2h) * 100:.1f}%)')
                    if buy_ratio_2h > 0.6:
                        print(f'[SIGNAL] 2H Buy dominance - Sustained buying pressure')
                    elif buy_ratio_2h < 0.4:
                        print(f'[WARNING] 2H Sell dominance - Weak buying interest')
                else:
                    print('[WARNING] Klines data incomplete (missing fields)')
            else:
                print(f'[WARNING] Insufficient klines data (got {(len(klines_60m) if klines_60m else 0)}, need 2)')
        except Exception as e:
            print(f'[ERROR] Aggression 2H: {type(e).__name__}: {e}')
        print('\n' + '=' * 70)
        print('5. VOLUME SPIKE (24h volume analysis)')
        print('=' * 70)
        try:
            ticker = await client.get_ticker_24h(symbol)
            volume_24h = float(ticker['quoteVolume'])
            price_change_pct = float(ticker['priceChangePercent'])
            print(f"[OK] Symbol: {ticker['symbol']}")
            print(f'[OK] 24h Volume: ${volume_24h:,.2f} USDT')
            print(f'[OK] 24h Price Change: {price_change_pct:.2f}%')
            print(f"[OK] High: ${ticker['highPrice']}")
            print(f"[OK] Low: ${ticker['lowPrice']}")
            if volume_24h > 10000000:
                print(f'[SIGNAL] High 24h volume - Significant interest')
            elif volume_24h > 1000000:
                print(f'[OK] Moderate 24h volume')
            else:
                print(f'[WARNING] Low 24h volume - Limited liquidity')
        except Exception as e:
            print(f'[ERROR] Volume Spike: {type(e).__name__}: {e}')
        print('\n' + '=' * 70)
        print('6. ALREADY PUMPED (4h price movement)')
        print('=' * 70)
        try:
            klines_4h = await client.get_klines(symbol, interval='4h', limit=6)
            if klines_4h and len(klines_4h) >= 6:
                oldest_open = float(klines_4h[0][1])
                latest_close = float(klines_4h[-1][4])
                price_change = (latest_close - oldest_open) / oldest_open * 100
                max_high = max((float(k[2]) for k in klines_4h))
                pullback_from_high = (max_high - latest_close) / max_high * 100
                print(f'[OK] 24h Price Change (4h candles): {price_change:+.2f}%')
                print(f'[OK] Pullback from High: {pullback_from_high:.2f}%')
                print(f'[OK] Current Price: ${latest_close}')
                print(f'[OK] 24h High: ${max_high}')
                if price_change > 50:
                    print(f'[WARNING] Already pumped >50% - High risk of correction')
                elif price_change > 20:
                    print(f'[CAUTION] Pumped >20% - Monitor for continuation or reversal')
                elif price_change > 0:
                    print(f'[OK] Positive momentum ({price_change:.1f}%)')
                else:
                    print(f'[OK] No recent pump - Fresh entry opportunity')
            else:
                print('[WARNING] Insufficient 4h klines data')
        except Exception as e:
            print(f'[ERROR] Already Pumped: {type(e).__name__}: {e}')
        print('\n' + '=' * 70)
        print('7. LIQUIDATION SIGNALS (Large trades)')
        print('=' * 70)
        try:
            all_trades = await client.get_recent_trades(symbol, limit=1000)
            if all_trades and len(all_trades) > 0:
                avg_size = sum((float(t['qty']) for t in all_trades)) / len(all_trades)
                large_trades = [t for t in all_trades if float(t['qty']) > avg_size * 3]
                large_buys = sum((float(t['qty']) for t in large_trades if not t['isBuyerMaker']))
                large_sells = sum((float(t['qty']) for t in large_trades if t['isBuyerMaker']))
                print(f'[OK] Total trades analyzed: {len(all_trades)}')
                print(f'[OK] Average trade size: {avg_size:.4f}')
                print(f'[OK] Large trades (>3x avg): {len(large_trades)}')
                print(f'[OK] Large Buys: {large_buys:.4f}')
                print(f'[OK] Large Sells: {large_sells:.4f}')
                if large_sells > large_buys * 2:
                    print(f'[WARNING] Heavy large sells - Possible liquidations or whale dumping')
                elif large_buys > large_sells * 2:
                    print(f'[SIGNAL] Heavy large buys - Strong accumulation')
                else:
                    print(f'[OK] Balanced large trade activity')
            else:
                print('[WARNING] No trades data for liquidation analysis')
        except Exception as e:
            print(f'[ERROR] Liquidation Signals: {type(e).__name__}: {e}')
    print('\n' + '#' * 70)
    print('# SUMMARY: BULLA Token Analysis')
    print('#' * 70)
    print('\n[INFO] All 7 metrics tested for top-6 analyzers')
    print('[INFO] Next step: Implement analyzer classes with gradient scoring (0-10)')
    print('[INFO] Missing: CoinGecko API for accurate Market Cap data')
if __name__ == '__main__':
    asyncio.run(test_bulla_metrics())
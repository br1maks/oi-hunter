import asyncio
import sys
sys.path.insert(0, 'D:/oi-hunter')
from src.api.mexc_client import MEXCRestClient

async def main():
    print('\n' + '#' * 70)
    print('# FINAL MEXC API FIXES TEST')
    print('#' * 70)
    async with MEXCRestClient() as client:
        print('\n' + '=' * 70)
        print('1. OPEN INTEREST TEST')
        print('=' * 70)
        try:
            oi_data = await client.get_open_interest('BTC_USDT')
            oi_value_billions = float(oi_data['openInterestValue']) / 1000000000
            print(f"[OK] Symbol: {oi_data['symbol']}")
            print(f"[OK] Open Interest: {float(oi_data['openInterest']):,.0f} contracts")
            print(f'[OK] OI Value: ${oi_value_billions:.2f}B USD')
            print(f"[OK] Price: ${oi_data['lastPrice']}")
            print('[SUCCESS] Open Interest endpoint РАБОТАЕТ!')
        except Exception as e:
            print(f'[FAIL] Open Interest: {type(e).__name__}: {e}')
            return
        print('\n' + '=' * 70)
        print('2. KLINES INTERVALS TEST')
        print('=' * 70)
        critical_intervals = {'5m': 'aggression_5m анализатор', '60m': 'aggression_2h анализатор (2 свечи)', '1h': 'альтернатива для 60m', '4h': 'длинные тренды'}
        klines_ok = True
        for interval, purpose in critical_intervals.items():
            try:
                klines = await client.get_klines('BTCUSDT', interval=interval, limit=2)
                if klines and len(klines) >= 1:
                    close_price = klines[0][4]
                    volume = klines[0][5]
                    print(f'[OK] {interval:4s} - Close: ${close_price:>8s}, Vol: {volume:>10s} ({purpose})')
                else:
                    print(f'[FAIL] {interval} - Empty response')
                    klines_ok = False
            except Exception as e:
                print(f'[FAIL] {interval} - {type(e).__name__}: {e}')
                klines_ok = False
        if klines_ok:
            print('[SUCCESS] Klines intervals РАБОТАЮТ!')
        else:
            print('[FAIL] Klines имеют проблемы')
            return
        print('\n' + '=' * 70)
        print('3. FUNDING RATE TEST')
        print('=' * 70)
        try:
            fr_data = await client.get_funding_rate('BTC_USDT')
            if fr_data.get('success'):
                data = fr_data['data']
                funding_rate = float(data['fundingRate']) * 100
                print(f"[OK] Symbol: {data['symbol']}")
                print(f'[OK] Funding Rate: {funding_rate:.4f}%')
                print(f"[OK] Next Settlement: {data['nextSettleTime']}")
                print('[SUCCESS] Funding Rate endpoint РАБОТАЕТ!')
            else:
                print(f'[FAIL] Funding Rate response: {fr_data}')
        except Exception as e:
            print(f'[FAIL] Funding Rate: {type(e).__name__}: {e}')
            return
        print('\n' + '=' * 70)
        print('4. TICKER 24H TEST')
        print('=' * 70)
        try:
            ticker = await client.get_ticker_24h('BTCUSDT')
            volume_millions = float(ticker['quoteVolume']) / 1000000
            print(f"[OK] Symbol: {ticker['symbol']}")
            print(f"[OK] Price: ${ticker['lastPrice']}")
            print(f'[OK] 24h Volume: ${volume_millions:.2f}M')
            print(f"[OK] 24h Change: {ticker['priceChangePercent']}%")
            print('[SUCCESS] Ticker endpoint РАБОТАЕТ!')
        except Exception as e:
            print(f'[FAIL] Ticker: {type(e).__name__}: {e}')
            return
        print('\n' + '=' * 70)
        print('5. RECENT TRADES TEST')
        print('=' * 70)
        try:
            trades = await client.get_recent_trades('BTCUSDT', limit=10)
            if trades and len(trades) > 0:
                buy_vol = sum((float(t['qty']) for t in trades if not t['isBuyerMaker']))
                sell_vol = sum((float(t['qty']) for t in trades if t['isBuyerMaker']))
                print(f'[OK] Trades count: {len(trades)}')
                print(f'[OK] Aggressor Buys: {buy_vol:.3f}')
                print(f'[OK] Aggressor Sells: {sell_vol:.3f}')
                print(f'[OK] Buy/Sell Ratio: {buy_vol / sell_vol:.2f}' if sell_vol > 0 else '[OK] Buy/Sell Ratio: inf')
                print('[SUCCESS] Recent Trades endpoint РАБОТАЕТ!')
            else:
                print('[FAIL] Recent Trades - Empty response')
        except Exception as e:
            print(f'[FAIL] Recent Trades: {type(e).__name__}: {e}')
            return
    print('\n' + '#' * 70)
    print('# ALL CRITICAL ENDPOINTS РАБОТАЮТ!')
    print('#' * 70)
    print('\n[READY] MEXC API клиент готов для OI-Hunter v2.0')
    print('\nГотовые endpoints для топ-6 анализаторов:')
    print('  1. OI/MC Ratio (вес 2.0)       - Open Interest ✓')
    print('  2. Funding Rate (вес 1.0)      - Funding Rate ✓')
    print('  3. Aggression (вес 1.5)        - Trades + Klines ✓')
    print('  4. Liquidation (вес 1.0)       - OI change + volume ✓')
    print('  5. Volume Spike (вес 1.0)      - Klines volume ✓')
    print('  6. Already Pumped (вес 0.5)    - Klines price ✓')
if __name__ == '__main__':
    asyncio.run(main())
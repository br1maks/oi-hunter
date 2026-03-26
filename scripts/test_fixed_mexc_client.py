import asyncio
import sys
sys.path.insert(0, 'D:/oi-hunter')
from src.api.mexc_client import MEXCRestClient

async def test_open_interest():
    print('\n' + '=' * 60)
    print('TEST: get_open_interest() - FIXED')
    print('=' * 60)
    async with MEXCRestClient() as client:
        symbols = ['BTCUSDT', 'BTC_USDT', 'ETHUSDT', 'ETH/USDT']
        for symbol in symbols:
            print(f'\n[TEST] Symbol: {symbol}')
            try:
                result = await client.get_open_interest(symbol)
                print(f"  [OK] Symbol: {result['symbol']}")
                print(f"  [OK] Open Interest: {result['openInterest']} contracts")
                print(f"  [OK] OI Value (USD): ${float(result['openInterestValue']):,.2f}")
                print(f"  [OK] Last Price: ${result['lastPrice']}")
                print(f"  [OK] Timestamp: {result['timestamp']}")
            except Exception as e:
                print(f'  [ERROR] {type(e).__name__}: {e}')

async def test_klines():
    print('\n' + '=' * 60)
    print('TEST: get_klines() - FIXED')
    print('=' * 60)
    async with MEXCRestClient() as client:
        symbol = 'BTCUSDT'
        intervals = ['1m', '5m', '15m', '1h', '4h']
        for interval in intervals:
            print(f'\n[TEST] Interval: {interval}')
            try:
                result = await client.get_klines(symbol, interval=interval, limit=2)
                print(f'  [OK] Got {len(result)} candles')
                if result:
                    candle = result[0]
                    print(f'  [OK] First candle:')
                    print(f'       Open: {candle[1]}, High: {candle[2]}, Low: {candle[3]}, Close: {candle[4]}')
            except Exception as e:
                print(f'  [ERROR] {type(e).__name__}: {e}')

async def test_ticker():
    print('\n' + '=' * 60)
    print('TEST: get_ticker_24h() - для сравнения')
    print('=' * 60)
    async with MEXCRestClient() as client:
        symbol = 'BTCUSDT'
        print(f'\n[TEST] Symbol: {symbol}')
        try:
            result = await client.get_ticker_24h(symbol)
            print(f"  [OK] Symbol: {result['symbol']}")
            print(f"  [OK] Last Price: ${result['lastPrice']}")
            print(f"  [OK] 24h Volume: ${float(result['quoteVolume']):,.2f}")
            print(f"  [OK] Price Change 24h: {result['priceChangePercent']}%")
        except Exception as e:
            print(f'  [ERROR] {type(e).__name__}: {e}')

async def test_funding_rate():
    print('\n' + '=' * 60)
    print('TEST: get_funding_rate()')
    print('=' * 60)
    async with MEXCRestClient() as client:
        symbols = ['BTCUSDT', 'ETHUSDT']
        for symbol in symbols:
            print(f'\n[TEST] Symbol: {symbol}')
            try:
                result = await client.get_funding_rate(symbol)
                print(f'  [OK] Response: {result}')
            except Exception as e:
                print(f'  [ERROR] {type(e).__name__}: {e}')

async def main():
    print('\n' + '#' * 60)
    print('# FIXED MEXC CLIENT TEST')
    print('#' * 60)
    await test_open_interest()
    await test_klines()
    await test_ticker()
    await test_funding_rate()
    print('\n' + '#' * 60)
    print('# ALL TESTS COMPLETE')
    print('#' * 60)
if __name__ == '__main__':
    asyncio.run(main())
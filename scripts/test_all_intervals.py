import asyncio
import sys
sys.path.insert(0, 'D:/oi-hunter')
from src.api.mexc_client import MEXCRestClient

async def test_all_intervals():
    print('\n' + '=' * 60)
    print('TEST: All intervals with FIXED mapping')
    print('=' * 60)
    async with MEXCRestClient() as client:
        symbol = 'BTCUSDT'
        intervals = ['1m', '5m', '15m', '30m', '1h', '2h', '4h', '1d']
        for interval in intervals:
            print(f'\n[TEST] Interval: {interval}')
            try:
                result = await client.get_klines(symbol, interval=interval, limit=1)
                if result:
                    candle = result[0]
                    print(f'  [OK] Got candle - Close: ${candle[4]}, Volume: {candle[5]}')
                else:
                    print(f'  [WARNING] Empty result')
            except Exception as e:
                print(f'  [ERROR] {type(e).__name__}: {e}')
if __name__ == '__main__':
    asyncio.run(test_all_intervals())
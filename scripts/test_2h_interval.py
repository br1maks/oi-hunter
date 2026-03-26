import asyncio
import httpx

async def test_2h_formats():
    base_url = 'https://api.mexc.com'
    endpoint = '/api/v3/klines'
    symbol = 'BTCUSDT'
    intervals = ['2h', '2H', '120m', '2Hour', 'Hour2']
    async with httpx.AsyncClient(timeout=10.0) as client:
        for interval in intervals:
            try:
                params = {'symbol': symbol, 'interval': interval, 'limit': 1}
                response = await client.get(f'{base_url}{endpoint}', params=params)
                if response.status_code == 200:
                    print(f"[SUCCESS] '{interval}' works!")
                else:
                    print(f"[FAIL] '{interval}' - {response.text[:80]}")
            except Exception as e:
                print(f"[ERROR] '{interval}' - {e}")
if __name__ == '__main__':
    asyncio.run(test_2h_formats())
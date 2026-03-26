import asyncio
import httpx

async def test_4h_formats():
    base_url = 'https://api.mexc.com'
    endpoint = '/api/v3/klines'
    symbol = 'BTCUSDT'
    intervals = ['4h', '4H', '240m', '4Hour', 'Hour4', 'Min240']
    async with httpx.AsyncClient(timeout=10.0) as client:
        for interval in intervals:
            try:
                url = f'{base_url}{endpoint}'
                params = {'symbol': symbol, 'interval': interval, 'limit': 1}
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    print(f"[SUCCESS] '{interval}' works! Got {len(data)} candles")
                else:
                    print(f"[FAIL] '{interval}' - {response.text[:100]}")
            except Exception as e:
                print(f"[ERROR] '{interval}' - {e}")
if __name__ == '__main__':
    asyncio.run(test_4h_formats())
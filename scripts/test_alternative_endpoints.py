import asyncio
import httpx
import json

async def test_contract_ticker():
    print('\n' + '=' * 60)
    print('TEST: /api/v1/contract/ticker')
    print('=' * 60)
    base_url = 'https://contract.mexc.com'
    endpoint = '/api/v1/contract/ticker'
    symbols = ['BTC_USDT', 'BTCUSDT', 'ETH_USDT']
    async with httpx.AsyncClient(timeout=10.0) as client:
        for symbol in symbols:
            print(f'\n[TEST] Symbol: {symbol}')
            try:
                url = f'{base_url}{endpoint}'
                params = {'symbol': symbol}
                response = await client.get(url, params=params)
                print(f'  URL: {response.url}')
                print(f'  Status: {response.status_code}')
                if response.status_code == 200:
                    data = response.json()
                    print(f'  Response keys: {list(data.keys())}')
                    print(f'  Full response:')
                    print(f'    {json.dumps(data, indent=4)}')
                    if 'openInterest' in str(data):
                        print(f"  [SUCCESS] Found 'openInterest' in response!")
                else:
                    print(f'  Error: {response.text[:200]}')
            except Exception as e:
                print(f'  Exception: {e}')

async def test_contract_detail():
    print('\n' + '=' * 60)
    print('TEST: /api/v1/contract/detail')
    print('=' * 60)
    base_url = 'https://contract.mexc.com'
    endpoint = '/api/v1/contract/detail'
    symbols = ['BTC_USDT', 'BTCUSDT']
    async with httpx.AsyncClient(timeout=10.0) as client:
        for symbol in symbols:
            print(f'\n[TEST] With query param, symbol: {symbol}')
            try:
                url = f'{base_url}{endpoint}'
                params = {'symbol': symbol}
                response = await client.get(url, params=params)
                print(f'  URL: {response.url}')
                print(f'  Status: {response.status_code}')
                if response.status_code == 200:
                    data = response.json()
                    print(f"  Response keys: {(list(data.keys()) if isinstance(data, dict) else 'list')}")
                    print(f'  Full response:')
                    print(f'    {json.dumps(data, indent=4)[:500]}')
                    if 'openInterest' in str(data):
                        print(f"  [SUCCESS] Found 'openInterest' in response!")
                else:
                    print(f'  Error: {response.text[:200]}')
            except Exception as e:
                print(f'  Exception: {e}')
        for symbol in symbols:
            print(f'\n[TEST] With path param, symbol: {symbol}')
            try:
                url = f'{base_url}{endpoint}/{symbol}'
                response = await client.get(url)
                print(f'  URL: {url}')
                print(f'  Status: {response.status_code}')
                if response.status_code == 200:
                    data = response.json()
                    print(f"  Response keys: {(list(data.keys()) if isinstance(data, dict) else 'list')}")
                    print(f'  Full response:')
                    print(f'    {json.dumps(data, indent=4)[:500]}')
                    if 'openInterest' in str(data):
                        print(f"  [SUCCESS] Found 'openInterest' in response!")
                else:
                    print(f'  Error: {response.text[:200]}')
            except Exception as e:
                print(f'  Exception: {e}')

async def test_klines_intervals():
    print('\n' + '=' * 60)
    print('TEST: Klines interval formats')
    print('=' * 60)
    base_url = 'https://api.mexc.com'
    endpoint = '/api/v3/klines'
    symbol = 'BTCUSDT'
    intervals = ['1h', '1H', '60m', 'Min60', 'Hour1']
    async with httpx.AsyncClient(timeout=10.0) as client:
        for interval in intervals:
            print(f'\n[TEST] Interval: {interval}')
            try:
                url = f'{base_url}{endpoint}'
                params = {'symbol': symbol, 'interval': interval, 'limit': 2}
                response = await client.get(url, params=params)
                print(f'  URL: {response.url}')
                print(f'  Status: {response.status_code}')
                if response.status_code == 200:
                    data = response.json()
                    print(f"  [SUCCESS] Interval '{interval}' works!")
                    print(f'  Response length: {len(data)}')
                    if data:
                        print(f'  First candle: {data[0][:6]}')
                else:
                    print(f'  Error: {response.text[:200]}')
            except Exception as e:
                print(f'  Exception: {e}')

async def main():
    print('\n' + '#' * 60)
    print('# MEXC ALTERNATIVE ENDPOINTS TEST')
    print('#' * 60)
    await test_contract_ticker()
    await test_contract_detail()
    await test_klines_intervals()
    print('\n' + '#' * 60)
    print('# TEST COMPLETE')
    print('#' * 60)
if __name__ == '__main__':
    asyncio.run(main())
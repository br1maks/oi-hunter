import asyncio
import httpx
import time

async def test_mexc_all_tickers():
    print('\n' + '=' * 70)
    print('TEST 1: MEXC All Tickers (single request)')
    print('=' * 70)
    async with httpx.AsyncClient(timeout=15.0) as client:
        start = time.time()
        response = await client.get('https://contract.mexc.com/api/v1/contract/ticker')
        elapsed = time.time() - start
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                tickers = data.get('data', [])
                if isinstance(tickers, list):
                    print(f'[OK] Got {len(tickers)} tickers in {elapsed:.2f}s (1 request!)')
                    for t in tickers[:5]:
                        symbol = t.get('symbol', '?')
                        hold_vol = t.get('holdVol', 0)
                        last_price = t.get('lastPrice', 0)
                        volume24 = t.get('amount24', 0)
                        print(f'  {symbol:15s} | HoldVol: {hold_vol:>15,} | Price: ${last_price} | Vol24: ${volume24:,.0f}')
                    print(f'  ...')
                    print(f'  Total: {len(tickers)} futures contracts')
                    with_oi = [t for t in tickers if t.get('holdVol', 0) > 0]
                    print(f'  With OI > 0: {len(with_oi)} tokens')
                elif isinstance(tickers, dict):
                    print(f'[OK] Got single ticker (dict)')
                    print(f"  {tickers.get('symbol', '?')}")
            else:
                print(f'[ERROR] {data}')
        else:
            print(f'[ERROR] HTTP {response.status_code}')

async def test_coinalyze_batch():
    print('\n' + '=' * 70)
    print('TEST 2: Coinalyze batch (multiple symbols)')
    print('=' * 70)
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get('https://api.coinalyze.net/v1/open-interest', params={'symbols': 'BTCUSDT_PERP.A,ETHUSDT_PERP.A,DOGEUSDT_PERP.A'})
            print(f'  Status: {response.status_code}')
            print(f'  Response: {response.text[:300]}')
            if response.status_code == 401:
                print(f'  [INFO] Need API key (401 = unauthorized)')
                print(f'  [INFO] But batch format confirmed if 200')
        except Exception as e:
            print(f'  [ERROR] {e}')

async def test_binance_oi_speed():
    print('\n' + '=' * 70)
    print('TEST 3: Binance Futures OI speed test')
    print('=' * 70)
    symbols = ['BTCUSDT', 'ETHUSDT', 'DOGEUSDT', 'PEPEUSDT', 'WIFUSDT', 'BONKUSDT', 'SHIBUSDT', 'XRPUSDT', 'SOLUSDT', 'ADAUSDT']
    async with httpx.AsyncClient(timeout=10.0) as client:
        start = time.time()
        results = []
        for sym in symbols:
            try:
                resp = await client.get('https://fapi.binance.com/fapi/v1/openInterest', params={'symbol': sym})
                if resp.status_code == 200:
                    data = resp.json()
                    results.append(data)
            except:
                pass
        elapsed = time.time() - start
        per_request = elapsed / len(symbols) if symbols else 0
        print(f'[OK] {len(results)} symbols in {elapsed:.2f}s ({per_request:.3f}s per request)')
        print(f'[OK] Estimated 600 symbols: {per_request * 600:.1f}s ({per_request * 600 / 60:.1f} min)')
        for r in results[:3]:
            oi_usd = float(r['openInterest']) * 100000
            print(f"  {r['symbol']:12s} | OI: {r['openInterest']}")

async def main():
    print('#' * 70)
    print('# BATCH OI APPROACHES TEST')
    print('#' * 70)
    await test_mexc_all_tickers()
    await test_coinalyze_batch()
    await test_binance_oi_speed()
    print('\n' + '#' * 70)
    print('# COMPLETE')
    print('#' * 70)
if __name__ == '__main__':
    asyncio.run(main())
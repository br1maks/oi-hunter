import asyncio
import httpx

async def test_token_exists(symbol: str):
    if not symbol.endswith('USDT'):
        symbol = f'{symbol}USDT'
    base_url_spot = 'https://api.mexc.com'
    base_url_futures = 'https://contract.mexc.com'
    result = {'symbol': symbol, 'spot': False, 'futures': False}
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f'{base_url_spot}/api/v3/ticker/24hr', params={'symbol': symbol})
            if response.status_code == 200:
                result['spot'] = True
        except:
            pass
        futures_symbol = symbol[:-4] + '_USDT'
        try:
            response = await client.get(f'{base_url_futures}/api/v1/contract/ticker', params={'symbol': futures_symbol})
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    result['futures'] = True
        except:
            pass
    return result

async def main():
    print('\n' + '=' * 70)
    print('TESTING LOW-CAP TOKENS ON MEXC')
    print('=' * 70)
    test_tokens = ['BULLA', 'PEPE', 'FLOKI', 'SHIB', 'DOGE', 'WIF', 'BONK', 'MEME', 'POPCAT', 'MOG', 'BRETT', 'TURBO', 'MYRO']
    print('\nТестирую токены на доступность...\n')
    available_both = []
    available_spot_only = []
    for token in test_tokens:
        result = await test_token_exists(token)
        spot_mark = '[OK]' if result['spot'] else '[--]'
        futures_mark = '[OK]' if result['futures'] else '[--]'
        print(f"{result['symbol']:12s} | Spot: {spot_mark} | Futures: {futures_mark}")
        if result['spot'] and result['futures']:
            available_both.append(result['symbol'])
        elif result['spot']:
            available_spot_only.append(result['symbol'])
        await asyncio.sleep(0.2)
    print('\n' + '=' * 70)
    print('SUMMARY')
    print('=' * 70)
    if available_both:
        print(f'\n[BEST] Tokens with SPOT + FUTURES (полный анализ):')
        for symbol in available_both:
            print(f'  - {symbol}')
    if available_spot_only:
        print(f'\n[LIMITED] Tokens with SPOT only (без OI данных):')
        for symbol in available_spot_only:
            print(f'  - {symbol}')
    if available_both:
        print(f"\n[RECOMMENDATION] Use '{available_both[0]}' for testing")
    elif available_spot_only:
        print(f"\n[RECOMMENDATION] Use '{available_spot_only[0]}' for limited testing (no OI)")
    else:
        print('\n[ERROR] No tokens found - try BTC, ETH instead')
if __name__ == '__main__':
    asyncio.run(main())
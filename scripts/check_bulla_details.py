import asyncio
import httpx

async def check_contract_details():
    print('\n' + '=' * 70)
    print('1. CONTRACT DETAILS (для правильного OI расчета)')
    print('=' * 70)
    base_url = 'https://contract.mexc.com'
    symbol = 'BULLA_USDT'
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f'{base_url}/api/v1/contract/detail', params={'symbol': symbol})
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    contract = data['data']
                    print(f"[OK] Symbol: {contract.get('symbol')}")
                    print(f"[OK] Contract Size: {contract.get('contractSize')}")
                    print(f"[OK] Min Leverage: {contract.get('minLeverage')}")
                    print(f"[OK] Max Leverage: {contract.get('maxLeverage')}")
                    print(f"[OK] Base Coin: {contract.get('baseCoin')}")
                    print(f"[OK] Quote Coin: {contract.get('quoteCoin')}")
                    return contract.get('contractSize')
                else:
                    print(f'[ERROR] Contract detail failed: {data}')
            else:
                print(f'[ERROR] HTTP {response.status_code}: {response.text[:200]}')
        except Exception as e:
            print(f'[ERROR] {type(e).__name__}: {e}')
    return None

async def check_volumes():
    print('\n' + '=' * 70)
    print('2. VOLUME COMPARISON (Spot vs Futures)')
    print('=' * 70)
    async with httpx.AsyncClient(timeout=10.0) as client:
        print('\n[SPOT VOLUME]')
        try:
            response = await client.get('https://api.mexc.com/api/v3/ticker/24hr', params={'symbol': 'BULLAUSDT'})
            if response.status_code == 200:
                data = response.json()
                volume_base = float(data['volume'])
                volume_quote = float(data['quoteVolume'])
                print(f'  Volume (BULLA): {volume_base:,.2f} tokens')
                print(f'  Volume (USDT): ${volume_quote:,.2f}')
                print(f"  Last Price: ${data['lastPrice']}")
                print(f"  Price Change 24h: {data['priceChangePercent']}%")
            else:
                print(f'  [ERROR] HTTP {response.status_code}')
        except Exception as e:
            print(f'  [ERROR] {type(e).__name__}: {e}')
        print('\n[FUTURES VOLUME]')
        try:
            response = await client.get('https://contract.mexc.com/api/v1/contract/ticker', params={'symbol': 'BULLA_USDT'})
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    ticker = data['data']
                    volume24 = ticker.get('volume24')
                    amount24 = ticker.get('amount24')
                    print(f'  Volume24 (contracts): {volume24:,}')
                    print(f'  Amount24 (USDT): ${amount24:,.2f}')
                    print(f"  Last Price: ${ticker.get('lastPrice')}")
                    print(f"  Hold Vol (OI): {ticker.get('holdVol'):,} contracts")
                else:
                    print(f'  [ERROR] {data}')
            else:
                print(f'  [ERROR] HTTP {response.status_code}')
        except Exception as e:
            print(f'  [ERROR] {type(e).__name__}: {e}')

async def recalculate_oi(contract_size: float):
    print('\n' + '=' * 70)
    print('3. RECALCULATED OPEN INTEREST')
    print('=' * 70)
    if not contract_size:
        print('[ERROR] No contract size available')
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get('https://contract.mexc.com/api/v1/contract/ticker', params={'symbol': 'BULLA_USDT'})
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    ticker = data['data']
                    hold_vol = float(ticker.get('holdVol', 0))
                    last_price = float(ticker.get('lastPrice', 0))
                    oi_value_correct = hold_vol * contract_size * last_price
                    oi_value_old = hold_vol * 0.0001 * last_price
                    print(f'[DATA] Hold Vol: {hold_vol:,.0f} contracts')
                    print(f'[DATA] Last Price: ${last_price}')
                    print(f'[DATA] Contract Size: {contract_size}')
                    print()
                    print(f'[OLD CALC] OI Value (contract_size=0.0001): ${oi_value_old:,.2f}')
                    print(f'[NEW CALC] OI Value (contract_size={contract_size}): ${oi_value_correct:,.2f}')
                    print()
                    if oi_value_correct > oi_value_old * 10:
                        print(f'[FIXED] Правильный OI в {oi_value_correct / oi_value_old:.0f}x раз больше!')
        except Exception as e:
            print(f'[ERROR] {type(e).__name__}: {e}')

async def main():
    print('\n' + '#' * 70)
    print('# BULLA CONTRACT DETAILS & VOLUME CHECK')
    print('#' * 70)
    contract_size = await check_contract_details()
    await check_volumes()
    if contract_size:
        await recalculate_oi(contract_size)
    print('\n' + '#' * 70)
    print('# COMPLETE')
    print('#' * 70)
if __name__ == '__main__':
    asyncio.run(main())
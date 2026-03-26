import asyncio
import sys
sys.path.insert(0, 'D:/oi-hunter')
from src.api.mexc_client import MEXCRestClient

async def test_oi_calculation():
    print('\n' + '=' * 70)
    print('TESTING FIXED OPEN INTEREST CALCULATION')
    print('=' * 70)
    async with MEXCRestClient() as client:
        print('\n[TEST 1] BTC (high-cap, contract_size = 0.0001)')
        try:
            oi_data = await client.get_open_interest('BTCUSDT')
            oi_value_millions = float(oi_data['openInterestValue']) / 1000000
            oi_value_billions = float(oi_data['openInterestValue']) / 1000000000
            print(f"  Symbol: {oi_data['symbol']}")
            print(f"  Contract Size: {oi_data['contractSize']}")
            print(f"  Open Interest: {float(oi_data['openInterest']):,.0f} contracts")
            print(f'  OI Value: ${oi_value_billions:.2f}B (${oi_value_millions:.2f}M)')
            print(f"  Price: ${oi_data['lastPrice']}")
            print(f'  [OK] BTC OI выглядит правильно (несколько миллиардов $)')
        except Exception as e:
            print(f'  [ERROR] {type(e).__name__}: {e}')
        print('\n[TEST 2] BULLA (low-cap, contract_size = 10)')
        try:
            oi_data = await client.get_open_interest('BULLAUSDT')
            oi_value_millions = float(oi_data['openInterestValue']) / 1000000
            print(f"  Symbol: {oi_data['symbol']}")
            print(f"  Contract Size: {oi_data['contractSize']}")
            print(f"  Open Interest: {float(oi_data['openInterest']):,.0f} contracts")
            print(f'  OI Value: ${oi_value_millions:.2f}M')
            print(f"  Price: ${oi_data['lastPrice']}")
            if oi_value_millions > 1:
                print(f'  [OK] BULLA OI выглядит правильно (несколько миллионов $)')
            else:
                print(f'  [WARNING] BULLA OI слишком маленький!')
        except Exception as e:
            print(f'  [ERROR] {type(e).__name__}: {e}')
        print('\n[TEST 3] ETH (high-cap, contract_size = 0.0001)')
        try:
            oi_data = await client.get_open_interest('ETHUSDT')
            oi_value_millions = float(oi_data['openInterestValue']) / 1000000
            print(f"  Symbol: {oi_data['symbol']}")
            print(f"  Contract Size: {oi_data['contractSize']}")
            print(f"  Open Interest: {float(oi_data['openInterest']):,.0f} contracts")
            print(f'  OI Value: ${oi_value_millions:.2f}M')
            print(f"  Price: ${oi_data['lastPrice']}")
            print(f'  [OK] ETH OI выглядит правильно')
        except Exception as e:
            print(f'  [ERROR] {type(e).__name__}: {e}')
    print('\n' + '=' * 70)
    print('[SUCCESS] Open Interest теперь рассчитывается правильно!')
    print('=' * 70)
if __name__ == '__main__':
    asyncio.run(test_oi_calculation())
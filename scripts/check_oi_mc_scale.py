import asyncio
import sys
sys.path.insert(0, 'D:/oi-hunter')
from src.api.mexc_client import MEXCRestClient
TOKEN_DATA = {'BTCUSDT': {'supply': 19800000, 'name': 'Bitcoin'}, 'ETHUSDT': {'supply': 120000000, 'name': 'Ethereum'}, 'DOGEUSDT': {'supply': 147000000000, 'name': 'Dogecoin'}, 'PEPEUSDT': {'supply': 420690000000000, 'name': 'Pepe'}, 'BULLAUSDT': {'supply': 280000000, 'name': 'Bulla'}, 'WIFUSDT': {'supply': 998900000, 'name': 'WIF'}, 'BONKUSDT': {'supply': 76700000000000, 'name': 'Bonk'}}

async def check_scale():
    print('\n' + '=' * 80)
    print('  OI/MC RATIO SCALE CHECK (MEXC only)')
    print('=' * 80)
    async with MEXCRestClient() as client:
        print(f"\n  {'Token':<12} {'OI (USD)':>15} {'MC (USD)':>18} {'OI/MC':>10} {'Zone':>15}")
        print(f"  {'-' * 12} {'-' * 15} {'-' * 18} {'-' * 10} {'-' * 15}")
        for symbol, info in TOKEN_DATA.items():
            try:
                oi_data = await client.get_open_interest(symbol)
                ticker = await client.get_ticker_24h(symbol)
                oi_value = float(oi_data['openInterestValue'])
                price = float(ticker['lastPrice'])
                mc = price * info['supply']
                ratio = oi_value / mc if mc > 0 else 0
                if ratio >= 0.16:
                    zone = 'OPTIMAL'
                elif ratio >= 0.05:
                    zone = 'Low'
                else:
                    zone = 'Very low'
                print(f"  {info['name']:<12} ${oi_value:>13,.0f} ${mc:>16,.0f} {ratio:>9.4f} {zone:>15}")
            except Exception as e:
                print(f"  {info['name']:<12} ERROR: {type(e).__name__}: {str(e)[:40]}")
            await asyncio.sleep(0.3)
    print()
    print('  NOTE: OI/MC zones from documentation (0.16-0.30 optimal)')
    print('  are likely based on AGGREGATED OI from ALL exchanges')
    print('  (Binance + Bybit + OKX + MEXC + etc.)')
    print()
    print('  MEXC alone = fraction of total futures market.')
    print('  Need to check if thresholds need adjustment for MEXC-only data.')
if __name__ == '__main__':
    asyncio.run(check_scale())
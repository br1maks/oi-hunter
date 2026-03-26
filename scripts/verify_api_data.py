import asyncio
import sys
from pathlib import Path
import json
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
from src.api.mexc_client import MEXCRestClient
from src.data.data_aggregator import DataAggregator
from src.data.market_cap_cache import MarketCapCache

async def verify_mexc_data(symbol: str):
    print('\n' + '=' * 70)
    print(f'MEXC API VERIFICATION: {symbol}')
    print('=' * 70)
    async with MEXCRestClient() as client:
        print('\n[1] TICKER DATA')
        print('-' * 70)
        from src.api.config import MEXCConfig
        ticker_url = f'{MEXCConfig.FUTURES_BASE_URL}/api/v1/contract/ticker/{symbol}'
        ticker = await client._request('GET', ticker_url)
        print(f'Raw response keys: {list(ticker.keys())}')
        print(f'\nImportant fields:')
        print(f"  symbol:           {ticker.get('symbol')}")
        print(f"  lastPrice:        {ticker.get('lastPrice')}")
        print(f"  holdVol:          {ticker.get('holdVol')}")
        print(f"  volume24:         {ticker.get('volume24')}")
        print(f"  riseFallRate:     {ticker.get('riseFallRate')}")
        print('\n[2] CONTRACT DETAIL')
        print('-' * 70)
        from src.api.config import MEXCConfig
        detail_url = f'{MEXCConfig.FUTURES_BASE_URL}/api/v1/contract/detail?symbol={symbol}'
        detail = await client._request('GET', detail_url)
        if detail and 'data' in detail:
            contract = detail['data']
            print(f"  contractSize:     {contract.get('contractSize')}")
            print(f"  quoteCoin:        {contract.get('quoteCoin')}")
            print(f"  baseCoin:         {contract.get('baseCoin')}")
        else:
            print(f'  ERROR: {detail}')
        print('\n[3] FUNDING RATE')
        print('-' * 70)
        funding = await client.get_funding_rate(symbol)
        print(f"  fundingRate:      {funding.get('fundingRate')}")
        print('\n[4] OI CALCULATION')
        print('-' * 70)
        price = float(ticker.get('lastPrice', 0))
        hold_vol = float(ticker.get('holdVol', 0))
        contract_size = float(contract.get('contractSize', 1)) if contract else 1.0
        oi_usd = hold_vol * contract_size * price
        print(f'  Formula: OI = holdVol × contractSize × price')
        print(f'  holdVol:          {hold_vol:,.0f} contracts')
        print(f'  contractSize:     {contract_size}')
        print(f'  price:            ${price:,.4f}')
        print(f'  ────────────────────────────────')
        print(f'  OI (USD):         ${oi_usd:,.0f}')
        return {'price': price, 'oi_usd': oi_usd, 'hold_vol': hold_vol, 'contract_size': contract_size, 'volume_24h': float(ticker.get('volume24', 0)), 'funding_rate': float(funding.get('fundingRate', 0))}

async def verify_coingecko_data(symbol: str):
    print('\n' + '=' * 70)
    print(f'COINGECKO API VERIFICATION: {symbol}')
    print('=' * 70)
    coin_symbol = symbol.replace('USDT', '').replace('PERP', '')
    async with MarketCapCache() as cache:
        print(f'\n[1] SEARCHING FOR: {coin_symbol}')
        print('-' * 70)
        from src.api.mexc_client import MEXCRestClient
        async with MEXCRestClient() as mexc_client:
            aggregator = DataAggregator(mexc_client=mexc_client, mc_cache=cache)
            ticker = await mexc_client.get(f'/api/v1/contract/ticker/{symbol}')
            current_price = float(ticker.get('lastPrice', 0))
            print(f'  Current price (MEXC): ${current_price:,.4f}')
            mc_data = await aggregator._fetch_market_cap(coin_symbol, current_price)
            if mc_data:
                print(f'\n[2] COINGECKO RESPONSE')
                print('-' * 70)
                print(f'  Market Cap (USD): ${mc_data:,.0f}')
                print(f'\n[3] MANUAL VERIFICATION')
                print('-' * 70)
                print(f'  Check on CoinGecko:')
                print(f'  https://www.coingecko.com/en/coins/{coin_symbol.lower()}')
                return mc_data
            else:
                print(f'\n  [X] Market cap NOT FOUND on CoinGecko')
                print(f'  This might be normal for:')
                print(f'    - Very new tokens')
                print(f'    - Tokens not listed on CoinGecko')
                print(f'    - Tokens with different symbols')
                return None

async def verify_final_calculations(symbol: str):
    print('\n' + '=' * 70)
    print(f'FINAL CALCULATIONS: {symbol}')
    print('=' * 70)
    mexc_data = await verify_mexc_data(symbol)
    mc = await verify_coingecko_data(symbol)
    print('\n' + '=' * 70)
    print('OI/MC RATIO CALCULATION')
    print('=' * 70)
    if mc and mc > 0:
        oi_mc_ratio = mexc_data['oi_usd'] / mc
        print(f'\n  Formula: OI/MC = OI_USD / Market_Cap')
        print(f"  OI (USD):         ${mexc_data['oi_usd']:,.0f}")
        print(f'  Market Cap (USD): ${mc:,.0f}')
        print(f'  ────────────────────────────────')
        print(f'  OI/MC Ratio:      {oi_mc_ratio:.6f} ({oi_mc_ratio * 100:.4f}%)')
        print(f'\n  INTERPRETATION:')
        if oi_mc_ratio < 0.1:
            print(f'    [X] TOO LOW ({oi_mc_ratio * 100:.2f}% < 10%) - insufficient fuel')
        elif 0.1 <= oi_mc_ratio < 0.16:
            print(f'    [!]  LOW ({oi_mc_ratio * 100:.2f}%) - building interest')
        elif 0.16 <= oi_mc_ratio < 0.3:
            print(f'    [OK] OPTIMAL ({oi_mc_ratio * 100:.2f}%) - target zone!')
        elif 0.3 <= oi_mc_ratio < 0.55:
            print(f'    [!]  ELEVATED ({oi_mc_ratio * 100:.2f}%) - caution')
        elif 0.55 <= oi_mc_ratio < 0.7:
            print(f'    [!!] DANGER ({oi_mc_ratio * 100:.2f}%) - high risk')
        else:
            print(f'    [!!!] EXTREME DANGER ({oi_mc_ratio * 100:.2f}% > 70%) - NEVER LONG!')
    else:
        print(f'\n  [X] Cannot calculate OI/MC - Market Cap not found')
    print('\n' + '=' * 70)

async def verify_data_aggregator(symbol: str):
    print('\n' + '=' * 70)
    print(f'DATA AGGREGATOR OUTPUT: {symbol}')
    print('=' * 70)
    async with MEXCRestClient() as mexc_client, MarketCapCache() as mc_cache:
        async with DataAggregator(mexc_client=mexc_client, mc_cache=mc_cache) as aggregator:
            market_data = await aggregator.aggregate(symbol)
            print(f'\n  price:            ${market_data.price:,.4f}')
            print(f'  volume_24h:       ${market_data.volume_24h:,.0f}')
            print(f'  open_interest:    ${market_data.open_interest_usd:,.0f}')
            print(f'  market_cap:       ${market_data.market_cap_usd:,.0f}' if market_data.market_cap_usd else '  market_cap:       None')
            print(f'  oi_mc_ratio:      {market_data.oi_mc_ratio:.6f}' if market_data.oi_mc_ratio else '  oi_mc_ratio:      None')
            print(f'  funding_rate:     {market_data.funding_rate:.6f}%')
            if market_data.aggression_2h:
                print(f'  aggression_2h:    {market_data.aggression_2h:.1f}% buy')
            if market_data.aggression_5m:
                print(f'  aggression_5m:    {market_data.aggression_5m:.1f}% buy')

async def main():
    print('=' * 70)
    print('API DATA VERIFICATION SUITE')
    print('=' * 70)
    test_tokens = [('DOGEUSDT', 'Large cap - should have MC'), ('BTCUSDT', 'Largest cap - definitely has MC')]
    for symbol, description in test_tokens:
        print(f"\n\n{'#' * 70}")
        print(f'# TESTING: {symbol} ({description})')
        print(f"{'#' * 70}")
        try:
            await verify_final_calculations(symbol)
            await verify_data_aggregator(symbol)
        except Exception as e:
            print(f'\n[X] ERROR: {e}')
            import traceback
            traceback.print_exc()
    print('\n' + '=' * 70)
    print('VERIFICATION COMPLETE')
    print('=' * 70)
    print('\nREVIEW:')
    print('  1. Check if OI calculations match MEXC web interface')
    print('  2. Check if Market Caps match CoinGecko website')
    print('  3. Check if OI/MC ratios make sense')
    print('  4. Check if DataAggregator output matches manual calculations')
if __name__ == '__main__':
    asyncio.run(main())
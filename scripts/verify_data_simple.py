import asyncio
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
from src.api.mexc_client import MEXCRestClient
from src.data.data_aggregator import DataAggregator
from src.data.market_cap_cache import MarketCapCache

async def verify_token(symbol: str):
    print('\n' + '=' * 70)
    print(f'VERIFYING: {symbol}')
    print('=' * 70)
    async with MEXCRestClient() as mexc_client, MarketCapCache() as mc_cache:
        async with DataAggregator(mexc_client=mexc_client, mc_cache=mc_cache) as aggregator:
            print('\n[1] Fetching data from MEXC and CoinGecko...')
            market_data = await aggregator.aggregate(symbol)
            print('\n[2] RAW DATA:')
            print('-' * 70)
            print(f'  Symbol:              {market_data.symbol}')
            print(f'  Price:               ${market_data.price:,.4f}')
            print(f'  Volume 24h:          ${market_data.volume_24h:,.0f}')
            print(f'  Open Interest USD:   ${market_data.open_interest_usd:,.0f}')
            print(f'  Market Cap USD:      ${market_data.market_cap_usd:,.0f}' if market_data.market_cap_usd else '  Market Cap USD:      None')
            print(f'  Funding Rate:        {market_data.funding_rate:.6f}%')
            if market_data.price_change_24h:
                print(f'  Price Change 24h:    {market_data.price_change_24h:+.2f}%')
            if market_data.price_change_4h:
                print(f'  Price Change 4h:     {market_data.price_change_4h:+.2f}%')
            if market_data.price_change_1h:
                print(f'  Price Change 1h:     {market_data.price_change_1h:+.2f}%')
            if market_data.aggression_2h:
                print(f'  Aggression 2h:       {market_data.aggression_2h:.1f}% buy')
            if market_data.aggression_5m:
                print(f'  Aggression 5m:       {market_data.aggression_5m:.1f}% buy')
            print('\n[3] OI/MC CALCULATION:')
            print('-' * 70)
            if market_data.market_cap_usd and market_data.market_cap_usd > 0:
                oi_mc = market_data.oi_mc_ratio
                print(f'  Formula:  OI / MC')
                print(f'  OI:       ${market_data.open_interest_usd:,.0f}')
                print(f'  MC:       ${market_data.market_cap_usd:,.0f}')
                print(f'  ---')
                print(f'  Ratio:    {oi_mc:.6f}  ({oi_mc * 100:.4f}%)')
                print(f'\n[4] INTERPRETATION:')
                print('-' * 70)
                if oi_mc < 0.1:
                    zone = 'TOO LOW'
                    desc = '< 10% - insufficient fuel for squeeze'
                elif 0.1 <= oi_mc < 0.16:
                    zone = 'LOW'
                    desc = '10-16% - building interest'
                elif 0.16 <= oi_mc < 0.3:
                    zone = 'OPTIMAL'
                    desc = '16-30% - TARGET ZONE for strategy!'
                elif 0.3 <= oi_mc < 0.55:
                    zone = 'ELEVATED'
                    desc = '30-55% - caution required'
                elif 0.55 <= oi_mc < 0.7:
                    zone = 'DANGER'
                    desc = '55-70% - high risk'
                else:
                    zone = 'EXTREME DANGER'
                    desc = '>70% - NEVER LONG!'
                print(f'  Zone:     {zone}')
                print(f'  Meaning:  {desc}')
                print(f'\n[5] SUITABILITY FOR OUR STRATEGY:')
                print('-' * 70)
                if oi_mc < 0.1:
                    print(f'  Status:   NOT SUITABLE')
                    print(f'  Reason:   OI/MC too low - token too big/stable')
                    print(f'  Example:  BTC, ETH, DOGE - market cap too large')
                elif 0.16 <= oi_mc <= 0.3:
                    print(f'  Status:   PERFECT CANDIDATE!')
                    print(f'  Reason:   OI/MC in optimal range for squeeze detection')
                    print(f'  Type:     Small/mid cap altcoin with leverage')
                elif oi_mc > 0.55:
                    print(f'  Status:   HIGH RISK')
                    print(f'  Reason:   OI/MC extremely high - potential cascade')
                    print(f'  Type:     Short candidate if other signals align')
                else:
                    print(f'  Status:   BORDERLINE')
                    print(f'  Reason:   Need other analyzers to confirm direction')
            else:
                print(f'  [X] Cannot calculate - Market Cap not found on CoinGecko')
                print(f'\n[4] INTERPRETATION:')
                print('-' * 70)
                print(f'  Without MC, we skip OI/MC analyzer')
                print(f'  Bot will use other 5 analyzers (Funding, Aggression, etc.)')
            print(f'\n[6] SANITY CHECKS:')
            print('-' * 70)
            checks_passed = 0
            checks_total = 0
            checks_total += 1
            if market_data.price > 0:
                print(f'  [OK] Price > 0: ${market_data.price:,.4f}')
                checks_passed += 1
            else:
                print(f'  [X] Price <= 0: INVALID!')
            checks_total += 1
            if market_data.open_interest_usd >= 0:
                print(f'  [OK] OI >= 0: ${market_data.open_interest_usd:,.0f}')
                checks_passed += 1
            else:
                print(f'  [X] OI < 0: INVALID!')
            checks_total += 1
            if market_data.volume_24h >= 0:
                print(f'  [OK] Volume >= 0: ${market_data.volume_24h:,.0f}')
                checks_passed += 1
            else:
                print(f'  [X] Volume < 0: INVALID!')
            checks_total += 1
            if market_data.market_cap_usd is None:
                print(f'  [SKIP] MC not found (OK for unlisted tokens)')
                checks_passed += 1
            elif market_data.market_cap_usd > 0:
                print(f'  [OK] MC > 0: ${market_data.market_cap_usd:,.0f}')
                checks_passed += 1
            else:
                print(f'  [X] MC <= 0: INVALID!')
            checks_total += 1
            if -5.0 <= market_data.funding_rate <= 5.0:
                print(f'  [OK] Funding rate in range: {market_data.funding_rate:.6f}%')
                checks_passed += 1
            else:
                print(f'  [!] Funding rate extreme: {market_data.funding_rate:.6f}%')
            if market_data.aggression_2h is not None:
                checks_total += 1
                if 0 <= market_data.aggression_2h <= 100:
                    print(f'  [OK] Aggression 2h valid: {market_data.aggression_2h:.1f}%')
                    checks_passed += 1
                else:
                    print(f'  [X] Aggression 2h invalid: {market_data.aggression_2h:.1f}%')
            print(f'\n  PASSED: {checks_passed}/{checks_total}')
            if checks_passed == checks_total:
                print(f'  [OK] All checks passed - data is VALID!')
            else:
                print(f'  [X] Some checks failed - review data!')

async def main():
    print('=' * 70)
    print('DATA VERIFICATION - SIMPLE VERSION')
    print('=' * 70)
    print('\nThis script verifies:')
    print('  1. Data from MEXC API is correct')
    print('  2. Market cap from CoinGecko is correct')
    print('  3. OI/MC calculations are correct')
    print('  4. Data passes sanity checks')
    tokens = [('BTCUSDT', 'Largest cap - should have very low OI/MC'), ('DOGEUSDT', 'Large cap - should have low OI/MC'), ('ETHUSDT', 'Large cap - should have low OI/MC')]
    for symbol, desc in tokens:
        print(f"\n{'#' * 70}")
        print(f'# {symbol} - {desc}')
        print(f"{'#' * 70}")
        try:
            await verify_token(symbol)
        except Exception as e:
            print(f'\n[X] ERROR: {e}')
            import traceback
            traceback.print_exc()
    print('\n' + '=' * 70)
    print('VERIFICATION COMPLETE')
    print('=' * 70)
    print('\nNext steps:')
    print('  1. Verify OI/MC values match manual calculations')
    print('  2. Check Market Caps on coingecko.com')
    print('  3. Compare OI with MEXC web interface')
if __name__ == '__main__':
    asyncio.run(main())
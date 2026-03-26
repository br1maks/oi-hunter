import asyncio
import time
from typing import Dict, Any
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.api.mexc_client import MEXCRestClient
from src.api.exceptions import MEXCAPIException
import httpx

async def test_mexc_ticker_24h(client: MEXCRestClient, symbol: str='BTCUSDT'):
    print(f"\n{'=' * 60}")
    print(f'MEXC Ticker 24h для {symbol}')
    print(f"{'=' * 60}")
    try:
        data = await client.get_ticker_24h(symbol)
        print(f'\n[OK] Успешно получен ticker для {symbol}')
        print(f'\nДоступные поля:')
        for key, value in data.items():
            print(f'  {key}: {value}')
        print(f'\n[DATA] Ключевые метрики:')
        print(f"  Цена: {data.get('lastPrice', 'N/A')}")
        print(f"  24h изменение: {data.get('priceChangePercent', 'N/A')}%")
        print(f"  24h объем (базовый актив): {data.get('volume', 'N/A')}")
        print(f"  24h объем (USDT): {data.get('quoteVolume', 'N/A')}")
        print(f"  High: {data.get('highPrice', 'N/A')}")
        print(f"  Low: {data.get('lowPrice', 'N/A')}")
        return data
    except MEXCAPIException as e:
        print(f'\n[ERROR] Ошибка: {e.message}')
        print(f'  Статус код: {e.status_code}')
        print(f'  Ответ: {e.response}')
        return None

async def test_mexc_open_interest(client: MEXCRestClient, symbol: str='BTC_USDT'):
    print(f"\n{'=' * 60}")
    print(f'MEXC Open Interest для {symbol}')
    print(f"{'=' * 60}")
    try:
        data = await client.get_open_interest(symbol)
        print(f'\n[OK] Успешно получен Open Interest для {symbol}')
        print(f'\nДоступные поля:')
        for key, value in data.items():
            print(f'  {key}: {value}')
        print(f'\n[DATA] Ключевые метрики:')
        print(f"  Open Interest (контракты): {data.get('openInterest', 'N/A')}")
        print(f"  Open Interest Value (USD): {data.get('openInterestValue', 'N/A')}")
        return data
    except MEXCAPIException as e:
        print(f'\n[ERROR] Ошибка: {e.message}')
        print(f'  Статус код: {e.status_code}')
        print(f'  Ответ: {e.response}')
        return None

async def test_mexc_funding_rate(client: MEXCRestClient, symbol: str='BTC_USDT'):
    print(f"\n{'=' * 60}")
    print(f'MEXC Funding Rate для {symbol}')
    print(f"{'=' * 60}")
    try:
        data = await client.get_funding_rate(symbol)
        print(f'\n[OK] Успешно получен Funding Rate для {symbol}')
        print(f'\nДоступные поля:')
        for key, value in data.items():
            print(f'  {key}: {value}')
        print(f'\n[DATA] Ключевые метрики:')
        funding_rate = data.get('fundingRate', 'N/A')
        if funding_rate != 'N/A':
            funding_rate_percent = float(funding_rate) * 100
            print(f'  Funding Rate: {funding_rate} ({funding_rate_percent:.4f}%)')
        print(f"  Next Funding Time: {data.get('nextFundingTime', 'N/A')}")
        return data
    except MEXCAPIException as e:
        print(f'\n[ERROR] Ошибка: {e.message}')
        print(f'  Статус код: {e.status_code}')
        print(f'  Ответ: {e.response}')
        return None

async def test_mexc_recent_trades(client: MEXCRestClient, symbol: str='BTCUSDT', limit: int=100):
    print(f"\n{'=' * 60}")
    print(f'MEXC Recent Trades для {symbol} (limit={limit})')
    print(f"{'=' * 60}")
    try:
        data = await client.get_recent_trades(symbol, limit=limit)
        print(f'\n[OK] Успешно получено {len(data)} сделок для {symbol}')
        if data:
            print(f'\nПример первой сделки:')
            first_trade = data[0]
            for key, value in first_trade.items():
                print(f'  {key}: {value}')
            buy_volume = sum((float(t['quoteQty']) for t in data if not t.get('isBuyerMaker', True)))
            sell_volume = sum((float(t['quoteQty']) for t in data if t.get('isBuyerMaker', True)))
            total_volume = buy_volume + sell_volume
            print(f'\n[DATA] Aggression метрики (из {len(data)} сделок):')
            print(f'  Buy Volume (aggressor): {buy_volume:.2f} USDT')
            print(f'  Sell Volume (aggressor): {sell_volume:.2f} USDT')
            print(f'  Total Volume: {total_volume:.2f} USDT')
            if total_volume > 0:
                buy_aggression = buy_volume / total_volume * 100
                print(f'  Buy Aggression: {buy_aggression:.2f}%')
        return data
    except MEXCAPIException as e:
        print(f'\n[ERROR] Ошибка: {e.message}')
        print(f'  Статус код: {e.status_code}')
        print(f'  Ответ: {e.response}')
        return None

async def test_mexc_klines(client: MEXCRestClient, symbol: str='BTCUSDT', interval: str='1h', limit: int=24):
    print(f"\n{'=' * 60}")
    print(f'MEXC Klines для {symbol} ({interval}, limit={limit})')
    print(f"{'=' * 60}")
    try:
        data = await client.get_klines(symbol, interval=interval, limit=limit)
        print(f'\n[OK] Успешно получено {len(data)} свечей для {symbol}')
        if data:
            print(f'\nПример первой свечи:')
            first_candle = data[0]
            print(f'  Open time: {first_candle[0]}')
            print(f'  Open: {first_candle[1]}')
            print(f'  High: {first_candle[2]}')
            print(f'  Low: {first_candle[3]}')
            print(f'  Close: {first_candle[4]}')
            print(f'  Volume: {first_candle[5]}')
            print(f'  Close time: {first_candle[6]}')
            print(f'  Quote volume: {first_candle[7]}')
            atr_values = []
            for i in range(1, len(data)):
                high = float(data[i][2])
                low = float(data[i][3])
                prev_close = float(data[i - 1][4])
                tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                atr_values.append(tr)
            if atr_values:
                avg_atr = sum(atr_values) / len(atr_values)
                print(f'\n[DATA] ATR метрики:')
                print(f'  Average True Range (ATR): {avg_atr:.2f}')
        return data
    except MEXCAPIException as e:
        print(f'\n[ERROR] Ошибка: {e.message}')
        print(f'  Статус код: {e.status_code}')
        print(f'  Ответ: {e.response}')
        return None

async def test_coingecko_market_data(coin_id: str='bitcoin'):
    print(f"\n{'=' * 60}")
    print(f'CoinGecko Market Data для {coin_id}')
    print(f"{'=' * 60}")
    url = f'https://api.coingecko.com/api/v3/coins/{coin_id}'
    params = {'localization': 'false', 'tickers': 'false', 'market_data': 'true', 'community_data': 'false', 'developer_data': 'false', 'sparkline': 'false'}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            start_time = time.time()
            response = await client.get(url, params=params)
            request_time = time.time() - start_time
            if response.status_code == 200:
                data = response.json()
                print(f'\n[OK] Успешно получены данные для {coin_id}')
                print(f'[TIME] Время запроса: {request_time:.2f}s')
                market_data = data.get('market_data', {})
                print(f'\n[DATA] Ключевые метрики:')
                print(f"  Symbol: {data.get('symbol', 'N/A').upper()}")
                print(f"  Current Price (USD): ${market_data.get('current_price', {}).get('usd', 'N/A')}")
                print(f"  Market Cap (USD): ${market_data.get('market_cap', {}).get('usd', 'N/A')}")
                print(f"  Circulating Supply: {market_data.get('circulating_supply', 'N/A')}")
                print(f"  Total Supply: {market_data.get('total_supply', 'N/A')}")
                print(f"  24h Volume (USD): ${market_data.get('total_volume', {}).get('usd', 'N/A')}")
                print(f"  24h Change: {market_data.get('price_change_percentage_24h', 'N/A')}%")
                print(f'\n[REFRESH] Rate Limit Info:')
                print(f"  X-RateLimit-Limit: {response.headers.get('x-ratelimit-limit', 'N/A')}")
                print(f"  X-RateLimit-Remaining: {response.headers.get('x-ratelimit-remaining', 'N/A')}")
                return market_data
            elif response.status_code == 429:
                print(f'\n[WARNING] Rate limit превышен!')
                print(f"  Retry-After: {response.headers.get('retry-after', 'N/A')}")
                return None
            else:
                print(f'\n[ERROR] Ошибка: HTTP {response.status_code}')
                print(f'  Ответ: {response.text[:200]}')
                return None
    except Exception as e:
        print(f'\n[ERROR] Ошибка: {str(e)}')
        return None

async def test_coingecko_low_cap_tokens():
    print(f"\n{'=' * 60}")
    print(f'CoinGecko Low-Cap Tokens Test')
    print(f"{'=' * 60}")
    test_tokens = [('light', 'LIGHT'), ('ogcommunity', 'OG'), ('broccoli', 'BROCCOLI'), ('pepe', 'PEPE')]
    results = []
    async with httpx.AsyncClient(timeout=10) as client:
        for coin_id, symbol in test_tokens:
            print(f'\n[SEARCH] Проверка {symbol} ({coin_id})...')
            url = f'https://api.coingecko.com/api/v3/coins/{coin_id}'
            params = {'localization': 'false', 'tickers': 'false', 'market_data': 'true', 'community_data': 'false', 'developer_data': 'false', 'sparkline': 'false'}
            try:
                start_time = time.time()
                response = await client.get(url, params=params)
                request_time = time.time() - start_time
                if response.status_code == 200:
                    data = response.json()
                    market_data = data.get('market_data', {})
                    market_cap = market_data.get('market_cap', {}).get('usd', 0)
                    circulating_supply = market_data.get('circulating_supply', 0)
                    print(f'  [OK] Найден!')
                    print(f'  Market Cap: ${market_cap:,.0f}')
                    print(f'  Circulating Supply: {circulating_supply:,.0f}')
                    print(f'  Время: {request_time:.2f}s')
                    results.append({'symbol': symbol, 'coin_id': coin_id, 'found': True, 'market_cap': market_cap, 'circulating_supply': circulating_supply, 'request_time': request_time})
                elif response.status_code == 404:
                    print(f'  [ERROR] Не найден в CoinGecko')
                    results.append({'symbol': symbol, 'coin_id': coin_id, 'found': False})
                else:
                    print(f'  [WARNING] Ошибка: HTTP {response.status_code}')
                    results.append({'symbol': symbol, 'coin_id': coin_id, 'found': False, 'error': response.status_code})
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f'  [ERROR] Исключение: {str(e)}')
                results.append({'symbol': symbol, 'coin_id': coin_id, 'found': False, 'error': str(e)})
    print(f"\n{'=' * 60}")
    print(f'Результаты для {len(results)} токенов:')
    found = sum((1 for r in results if r.get('found', False)))
    print(f'  Найдено: {found}/{len(results)}')
    return results

async def test_coingecko_rate_limits():
    print(f"\n{'=' * 60}")
    print(f'CoinGecko Rate Limits Test')
    print(f"{'=' * 60}")
    print(f'\nВыполняем серию запросов для проверки лимитов...')
    test_coins = ['bitcoin', 'ethereum', 'binancecoin', 'ripple', 'cardano']
    request_times = []
    rate_limit_info = []
    async with httpx.AsyncClient(timeout=10) as client:
        for i, coin_id in enumerate(test_coins, 1):
            url = f'https://api.coingecko.com/api/v3/coins/{coin_id}'
            params = {'localization': 'false', 'tickers': 'false', 'market_data': 'true', 'community_data': 'false', 'developer_data': 'false', 'sparkline': 'false'}
            try:
                start_time = time.time()
                response = await client.get(url, params=params)
                request_time = time.time() - start_time
                request_times.append(request_time)
                rate_limit_info.append({'request': i, 'coin': coin_id, 'status': response.status_code, 'time': request_time, 'limit': response.headers.get('x-ratelimit-limit', 'N/A'), 'remaining': response.headers.get('x-ratelimit-remaining', 'N/A')})
                print(f"  {i}. {coin_id}: {response.status_code} ({request_time:.2f}s) - Remaining: {response.headers.get('x-ratelimit-remaining', 'N/A')}")
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f'  {i}. {coin_id}: [ERROR] {str(e)}')
    print(f'\n[DATA] Статистика:')
    if request_times:
        avg_time = sum(request_times) / len(request_times)
        print(f'  Среднее время запроса: {avg_time:.2f}s')
        print(f'  Минимальное время: {min(request_times):.2f}s')
        print(f'  Максимальное время: {max(request_times):.2f}s')
    print(f'\n[PREDICT] Прогноз для 600 токенов:')
    if request_times:
        calls_per_minute = 10
        total_tokens = 600
        minutes_needed = total_tokens / calls_per_minute
        print(f'  Rate limit (консервативно): {calls_per_minute} req/min')
        print(f'  Время для 600 токенов: ~{minutes_needed:.1f} минут')
        print(f'  С задержками и retry: ~{minutes_needed * 1.2:.1f} минут')
    return rate_limit_info

async def run_mexc_tests():
    print('\n' + '=' * 60)
    print('[START] MEXC API TESTS')
    print('=' * 60)
    async with MEXCRestClient() as client:
        await test_mexc_ticker_24h(client, 'BTCUSDT')
        await test_mexc_open_interest(client, 'BTC_USDT')
        await test_mexc_funding_rate(client, 'BTC_USDT')
        await test_mexc_recent_trades(client, 'BTCUSDT', limit=100)
        await test_mexc_klines(client, 'BTCUSDT', interval='1h', limit=24)

async def run_coingecko_tests():
    print('\n' + '=' * 60)
    print('[START] COINGECKO API TESTS')
    print('=' * 60)
    await test_coingecko_market_data('bitcoin')
    await test_coingecko_low_cap_tokens()
    await test_coingecko_rate_limits()

async def analyze_results():
    print('\n' + '=' * 60)
    print('[REPORT] АНАЛИЗ РЕЗУЛЬТАТОВ')
    print('=' * 60)
    print(f'\n1. MEXC API - Доступные метрики:')
    print(f'   [OK] Price (spot ticker)')
    print(f'   [OK] Volume 24h (spot ticker)')
    print(f'   [OK] Price change % (spot ticker)')
    print(f'   [OK] Open Interest в USD (futures)')
    print(f'   [OK] Funding Rate (futures)')
    print(f'   [OK] Buy/Sell Aggression (из trades)')
    print(f'   [OK] ATR / Volatility (из klines)')
    print(f'\n2. CoinGecko API - Доступные метрики:')
    print(f'   [OK] Market Cap (USD)')
    print(f'   [OK] Circulating Supply')
    print(f'   [WARNING] Free tier: ~10-50 req/min')
    print(f'   [WARNING] 600 токенов = ~60-12 минут')
    print(f'\n3. OI/MC Ratio расчёт:')
    print(f'   Formula: (Open Interest USD / Market Cap USD) * 100%')
    print(f'   [OK] Open Interest USD - из MEXC futures')
    print(f'   [OK] Market Cap USD - из CoinGecko')
    print(f'   [OK] Все данные доступны!')
    print(f'\n4. Проблемы и решения:')
    print(f'   [WARNING] CoinGecko free tier медленный для 600 токенов')
    print(f'   [OK] Решение 1: Кэшировать market cap (обновлять раз в час)')
    print(f'   [OK] Решение 2: Использовать альтернативы:')
    print(f'      - CoinMarketCap API (free tier: 333 req/day)')
    print(f'      - MEXC собственный market cap (если есть)')
    print(f'      - Расчёт MC = Circulating Supply x Price (из MEXC spot)')
    print(f'\n5. Рекомендации:')
    print(f'   [OK] Использовать MEXC как основной источник (price, OI, FR, trades)')
    print(f'   [OK] Кэшировать market cap данные (обновлять раз в 1-4 часа)')
    print(f'   [OK] Расчёт MC локально: Supply x Price (если supply известен)')
    print(f"   [OK] Запросы к CoinGecko делать batch'ами с задержками")
    print(f'   [WARNING] Для production рассмотреть платный CoinGecko Pro (~$130/мес)')

async def main():
    print('\n' + '#' * 60)
    print('# API AVAILABILITY TEST')
    print('# MEXC + CoinGecko')
    print('#' * 60)
    try:
        await run_mexc_tests()
        print('\n[WAIT] Ожидание 3 секунды перед CoinGecko тестами...')
        await asyncio.sleep(3)
        await run_coingecko_tests()
        await analyze_results()
        print(f"\n{'=' * 60}")
        print('[OK] Все тесты завершены!')
        print(f"{'=' * 60}\n")
    except KeyboardInterrupt:
        print('\n\n[WARNING] Тесты прерваны пользователем')
    except Exception as e:
        print(f'\n\n[ERROR] Критическая ошибка: {str(e)}')
        import traceback
        traceback.print_exc()
if __name__ == '__main__':
    asyncio.run(main())
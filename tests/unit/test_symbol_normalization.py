import pytest
from src.api.config import MEXCConfig
from src.api.exceptions import MEXCInvalidSymbolException

class TestSymbolNormalization:

    @pytest.mark.parametrize('input_symbol, expected', [('BTCUSDT', 'BTCUSDT'), ('BTC/USDT', 'BTCUSDT'), ('BTC-USDT', 'BTCUSDT'), ('BTC_USDT', 'BTCUSDT'), ('btcusdt', 'BTCUSDT'), ('btc/usdt', 'BTCUSDT'), ('ETHUSDT', 'ETHUSDT'), ('eth_usdt', 'ETHUSDT'), ('SOLUSDT', 'SOLUSDT'), ('sol-usdt', 'SOLUSDT')])
    def test_spot_symbol_format(self, input_symbol, expected):
        result = MEXCConfig.spot_symbol_format(input_symbol)
        assert result == expected, f'Expected {expected}, got {result}'

    @pytest.mark.parametrize('input_symbol, expected', [('BTCUSDT', 'BTC_USDT'), ('BTC_USDT', 'BTC_USDT'), ('BTC/USDT', 'BTC_USDT'), ('btc_usdt', 'BTC_USDT'), ('ETHUSDT', 'ETH_USDT'), ('eth/usdt', 'ETH_USDT')])
    def test_futures_symbol_format(self, input_symbol, expected):
        result = MEXCConfig.futures_symbol_format(input_symbol)
        assert result == expected, f'Expected {expected}, got {result}'

    @pytest.mark.parametrize('input_symbol,expected_final', [('BTCUSDT', 'BTC_USDT'), ('BTC_USDT', 'BTC_USDT'), ('ETHUSDT', 'ETH_USDT'), ('btc/usdt', 'BTC_USDT'), ('SOLUSDT', 'SOL_USDT'), ('sol-usdt', 'SOL_USDT'), ('OGUSDT', 'OG_USDT'), ('LIGHTUSDT', 'LIGHT_USDT'), ('SENTUSDT', 'SENT_USDT')])
    def test_futures_full_normalization(self, input_symbol, expected_final):
        normalized = MEXCConfig.futures_symbol_format(input_symbol)
        if '_' not in normalized:
            if normalized.endswith('USDT'):
                base = normalized[:-4]
                normalized = f'{base}_USDT'
        assert normalized == expected_final, f'Expected {expected_final}, got {normalized}'

    def test_empty_symbol(self):
        assert MEXCConfig.spot_symbol_format('') == ''
        assert MEXCConfig.futures_symbol_format('') == ''

    def test_spot_multiple_separators(self):
        result = MEXCConfig.spot_symbol_format('BTC/USDT_TEST-2')
        assert result == 'BTCUSDTTEST2'

    def test_futures_already_formatted(self):
        result = MEXCConfig.futures_symbol_format('BTC_USDT')
        assert result == 'BTC_USDT'
        assert '_' in result

    @pytest.mark.parametrize('input_symbol,expected_base_length', [('QUSDT', 1), ('OGUSDT', 2), ('BTCUSDT', 3), ('ETHUSDT', 3), ('LIGHTUSDT', 5)])
    def test_various_length_symbols(self, input_symbol, expected_base_length):
        normalized = MEXCConfig.futures_symbol_format(input_symbol)
        if '_' not in normalized:
            if normalized.endswith('USDT'):
                base = normalized[:-4]
                normalized = f'{base}_USDT'
        base_part = normalized.split('_')[0]
        assert len(base_part) == expected_base_length
        assert normalized.endswith('_USDT')
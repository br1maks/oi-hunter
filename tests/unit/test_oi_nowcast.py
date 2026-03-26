import pytest
from datetime import datetime, timedelta, timezone

def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
from src.analyzers.oi_nowcast_analyzer import OINowcastAnalyzer, normalize_symbol

class TestSymbolNormalization:

    def test_already_normalized(self):
        assert normalize_symbol('BTC_USDT') == 'BTC_USDT'

    def test_without_underscore(self):
        assert normalize_symbol('BTCUSDT') == 'BTC_USDT'
        assert normalize_symbol('ETHUSDT') == 'ETH_USDT'
        assert normalize_symbol('DOGEUSDT') == 'DOGE_USDT'

    def test_long_symbol(self):
        assert normalize_symbol('PIPPINUSDT') == 'PIPPIN_USDT'

class TestVelocityCalculation:

    def setup_method(self):
        self.analyzer = OINowcastAnalyzer()

    def test_steady_growth(self):
        base_time = _utcnow()
        history = [(base_time, 1000), (base_time + timedelta(minutes=5), 1050), (base_time + timedelta(minutes=10), 1100)]
        velocity = self.analyzer._calculate_velocity(history)
        assert 9 < velocity < 11

    def test_steady_decline(self):
        base_time = _utcnow()
        history = [(base_time, 1000), (base_time + timedelta(minutes=5), 950), (base_time + timedelta(minutes=10), 900)]
        velocity = self.analyzer._calculate_velocity(history)
        assert -11 < velocity < -9

    def test_flat(self):
        base_time = _utcnow()
        history = [(base_time, 1000), (base_time + timedelta(minutes=5), 1000), (base_time + timedelta(minutes=10), 1000)]
        velocity = self.analyzer._calculate_velocity(history)
        assert abs(velocity) < 0.01

    def test_insufficient_data(self):
        base_time = _utcnow()
        history = [(base_time, 1000)]
        velocity = self.analyzer._calculate_velocity(history)
        assert velocity == 0.0

class TestPrediction:

    def setup_method(self):
        self.analyzer = OINowcastAnalyzer()

    def test_positive_velocity(self):
        result = self.analyzer._predict_oi(current_oi=1000, velocity=10, acceleration=0, minutes_ahead=10)
        assert 1090 < result['predicted_oi'] < 1110
        assert 9 < result['predicted_change_pct'] < 11

    def test_negative_velocity(self):
        result = self.analyzer._predict_oi(current_oi=1000, velocity=-20, acceleration=0, minutes_ahead=5)
        assert 890 < result['predicted_oi'] < 910
        assert -11 < result['predicted_change_pct'] < -9

    def test_with_acceleration(self):
        result = self.analyzer._predict_oi(current_oi=1000, velocity=10, acceleration=2, minutes_ahead=10)
        assert 1190 < result['predicted_oi'] < 1210

    def test_non_negative_oi(self):
        result = self.analyzer._predict_oi(current_oi=100, velocity=-50, acceleration=0, minutes_ahead=10)
        assert result['predicted_oi'] >= 0

class TestScoring:

    def setup_method(self):
        self.analyzer = OINowcastAnalyzer()

    def test_surging_oi(self):
        long, short, msg = self.analyzer._score_prediction(12.5)
        assert long == 9.0
        assert short == 1.0
        assert 'SURGING' in msg

    def test_collapsing_oi(self):
        long, short, msg = self.analyzer._score_prediction(-12.5)
        assert long == 0.0
        assert short == 10.0
        assert 'CRASH' in msg

    def test_stable_oi(self):
        long, short, msg = self.analyzer._score_prediction(0.5)
        assert long == 5.0
        assert short == 5.0
        assert 'stable' in msg.lower()

    def test_weakening_oi(self):
        long, short, msg = self.analyzer._score_prediction(-7.0)
        assert long == 1.0
        assert short == 8.0
        assert 'COLLAPSING' in msg or 'EXIT' in msg
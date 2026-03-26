import pytest
from src.analyzers.order_book_analyzer import OrderBookAnalyzer
from src.models.market_data import MarketData

def _make_md(ob_bid_total=None, ob_ask_total=None, ob_bid_wall=None, ob_ask_wall=None, ob_t1_bid_vol=None, ob_t1_ask_vol=None, ob_t2_bid_vol=None, ob_t2_ask_vol=None, ob_spread_pct=None) -> MarketData:
    return MarketData(symbol='TEST_USDT', price=1.0, volume_24h=1000000, open_interest_usd=500000, funding_rate=0.0, ob_bid_total=ob_bid_total, ob_ask_total=ob_ask_total, ob_bid_wall=ob_bid_wall, ob_ask_wall=ob_ask_wall, ob_t1_bid_vol=ob_t1_bid_vol, ob_t1_ask_vol=ob_t1_ask_vol, ob_t2_bid_vol=ob_t2_bid_vol, ob_t2_ask_vol=ob_t2_ask_vol, ob_spread_pct=ob_spread_pct)

class TestOrderBookAnalyzerValidation:

    def test_returns_none_without_ob_data(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md()
        assert analyzer.analyze(md) is None

    def test_returns_none_when_bid_total_zero(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=0, ob_ask_total=1000)
        assert analyzer.analyze(md) is None

    def test_returns_none_when_ask_total_zero(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=0)
        assert analyzer.analyze(md) is None

class TestOrderBookImbalanceScoring:

    def test_strong_bid_dominance(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=3000, ob_ask_total=1000)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.long_score == pytest.approx(9.0, abs=0.1)
        assert result.short_score <= 2.0
        assert 'buy pressure' in result.reasoning.lower() or 'bids' in result.reasoning.lower()

    def test_strong_ask_dominance(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=3000)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.short_score >= 8.0
        assert result.long_score <= 2.0

    def test_neutral_balanced_book(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=1000)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.long_score == pytest.approx(5.0, abs=0.5)
        assert result.short_score == pytest.approx(5.0, abs=0.5)

    def test_moderate_bid_lead(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1500, ob_ask_total=1000)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.long_score == pytest.approx(7.0, abs=0.5)

    def test_moderate_ask_lead(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=1500)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.short_score == pytest.approx(7.0, abs=0.5)

    def test_extreme_ask_dominance_alert(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=4000)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.alert_level == 'critical'

    def test_key_value_is_ratio(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=2000, ob_ask_total=1000)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.key_value == pytest.approx(2.0, rel=0.01)
        assert result.key_label == 'Bid/Ask Ratio'

class TestTier1Modifiers:

    def test_heavy_t1_ask_boosts_short(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=1000, ob_t1_ask_vol=300)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.short_score == pytest.approx(7.0, abs=0.1)
        assert result.long_score == pytest.approx(4.5, abs=0.1)
        assert 'T1 Ask' in result.reasoning

    def test_heavy_t1_bid_boosts_long(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=1000, ob_t1_bid_vol=300)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.long_score == pytest.approx(7.0, abs=0.1)
        assert result.short_score == pytest.approx(4.5, abs=0.1)
        assert 'T1 Bid' in result.reasoning

    def test_t1_below_threshold_no_effect(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=1000, ob_t1_ask_vol=200)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.long_score == pytest.approx(5.0, abs=0.1)
        assert result.short_score == pytest.approx(5.0, abs=0.1)

    def test_t1_exactly_at_threshold(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=1000, ob_t1_ask_vol=300)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.short_score > 5.0

class TestTier2Modifiers:

    def test_heavy_t2_ask_boosts_short(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=1000, ob_t2_ask_vol=400)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.short_score == pytest.approx(6.0, abs=0.1)
        assert result.long_score == pytest.approx(5.0, abs=0.1)
        assert 'T2 Ask' in result.reasoning

    def test_heavy_t2_bid_boosts_long(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=1000, ob_t2_bid_vol=400)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.long_score == pytest.approx(6.0, abs=0.1)
        assert result.short_score == pytest.approx(5.0, abs=0.1)
        assert 'T2 Bid' in result.reasoning

    def test_t2_below_threshold_no_modifier(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=1000, ob_t2_ask_vol=350)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.long_score == pytest.approx(5.0, abs=0.1)
        assert result.short_score == pytest.approx(5.0, abs=0.1)

    def test_t1_and_t2_both_active_stacks(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=1000, ob_t1_ask_vol=300, ob_t2_ask_vol=400)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.short_score == pytest.approx(8.0, abs=0.1)
        assert result.long_score == pytest.approx(4.5, abs=0.1)

class TestWallDetection:

    def test_large_ask_wall_adds_short_modifier(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=1000, ob_ask_wall=400)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.short_score > 5.0
        assert 'Ask wall' in result.reasoning

    def test_large_bid_wall_adds_long_modifier(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=1000, ob_bid_wall=400)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.long_score > 5.0
        assert 'Bid wall' in result.reasoning

    def test_small_wall_no_effect(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=1000, ob_ask_wall=200)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.short_score == pytest.approx(5.0, abs=0.1)

class TestBlockingFlags:

    def test_blocks_long_on_heavy_ask_pressure(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=400, ob_ask_total=1000, ob_t1_ask_vol=300)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.blocks_long is True

    def test_blocks_short_on_heavy_bid_pressure(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=400, ob_t1_bid_vol=300)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.blocks_short is True

    def test_no_blocks_at_moderate_imbalance(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1200, ob_ask_total=1000)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.blocks_long is False
        assert result.blocks_short is False

    def test_no_blocks_without_t1_data(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=300, ob_ask_total=1000)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.blocks_long is False

    def test_blocks_long_requires_both_conditions(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=400, ob_ask_total=1000, ob_t1_ask_vol=200)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.blocks_long is False

class TestSpreadConfidence:

    def test_tight_spread_raises_confidence(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=1000, ob_spread_pct=0.02)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.confidence >= 0.79

    def test_wide_spread_lowers_confidence(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=1000, ob_spread_pct=1.5)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.confidence <= 0.6

    def test_no_spread_data_neutral_confidence(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=1000)
        result = analyzer.analyze(md)
        assert result is not None
        assert result.confidence == pytest.approx(0.75, abs=0.01)

    def test_spread_in_reasoning(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=1000, ob_spread_pct=0.15)
        result = analyzer.analyze(md)
        assert result is not None
        assert 'Spread' in result.reasoning or 'spread' in result.reasoning

    def test_wide_spread_flagged_in_reasoning(self):
        analyzer = OrderBookAnalyzer()
        md = _make_md(ob_bid_total=1000, ob_ask_total=1000, ob_spread_pct=0.8)
        result = analyzer.analyze(md)
        assert result is not None
        assert 'Wide spread' in result.reasoning
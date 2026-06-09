"""
PATH J + PATH K: Volume Spike Divergence Guards

Tests for _is_post_crash_accumulation() (PATH J) and _is_post_pump_distribution() (PATH K)
in VolumeSpikeAnalyzer. Covers all scenarios from the plan table.
"""
import pytest
from src.analyzers.volume_spike_analyzer import VolumeSpikeAnalyzer
from src.models.market_data import MarketData


def make_data(**kwargs) -> MarketData:
    defaults = dict(
        symbol='TEST_USDT',
        price=1.0,
        volume_24h=5_000_000,
        volume_1h=500_000,
        avg_volume_1h=100_000,   # vol_ratio = 5.0 → spike_score=10, blocks threshold=2.0
        open_interest_usd=2_000_000,
        funding_rate=0.0001,
        price_change_1h=None,
        price_change_24h=None,
        buy_volume_5m=None,
        sell_volume_5m=None,
        buy_volume_2h=None,
        sell_volume_2h=None,
        trade_count_5m=None,
        trade_count_2h=None,
    )
    defaults.update(kwargs)
    return MarketData(**defaults)


def make_agg_5m(pct: float):
    """Return buy/sell_volume_5m that yields given aggression_5m %."""
    buy = pct
    sell = 100.0 - pct
    return dict(buy_volume_5m=buy * 1000, sell_volume_5m=sell * 1000, trade_count_5m=50)


def make_agg_2h(pct: float):
    """Return buy/sell_volume_2h that yields given aggression_2h %."""
    buy = pct
    sell = 100.0 - pct
    return dict(buy_volume_2h=buy * 1000, sell_volume_2h=sell * 1000, trade_count_2h=100)


az = VolumeSpikeAnalyzer()


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests for _is_post_crash_accumulation (PATH J)
# ─────────────────────────────────────────────────────────────────────────────

class TestIsPostCrashAccumulation:

    def test_returns_false_when_price24h_is_none(self):
        data = make_data(price_change_24h=None, **make_agg_5m(70))
        assert az._is_post_crash_accumulation(data) is False

    def test_returns_false_when_price24h_above_threshold(self):
        # -34.9% is not enough
        data = make_data(price_change_24h=-34.9, **make_agg_5m(70))
        assert az._is_post_crash_accumulation(data) is False

    def test_returns_false_exactly_at_threshold(self):
        # -35.0 is NOT below -35 (strictly less)
        data = make_data(price_change_24h=-35.0, **make_agg_5m(70))
        assert az._is_post_crash_accumulation(data) is False

    def test_returns_true_with_5m_buyers_above_threshold(self):
        data = make_data(price_change_24h=-50.0, **make_agg_5m(60))
        assert az._is_post_crash_accumulation(data) is True

    def test_returns_true_with_5m_buyers_exactly_at_threshold(self):
        data = make_data(price_change_24h=-50.0, **make_agg_5m(60.0))
        assert az._is_post_crash_accumulation(data) is True

    def test_returns_false_when_5m_buyers_below_threshold(self):
        data = make_data(price_change_24h=-50.0, **make_agg_5m(59.9))
        assert az._is_post_crash_accumulation(data) is False

    def test_returns_true_with_2h_fallback_when_5m_none(self):
        data = make_data(price_change_24h=-50.0, **make_agg_2h(65))
        assert az._is_post_crash_accumulation(data) is True

    def test_returns_false_when_2h_fallback_below_threshold(self):
        data = make_data(price_change_24h=-50.0, **make_agg_2h(59.9))
        assert az._is_post_crash_accumulation(data) is False

    def test_returns_false_when_both_none(self):
        data = make_data(price_change_24h=-50.0)
        assert az._is_post_crash_accumulation(data) is False

    def test_5m_takes_priority_over_2h(self):
        # 5m below threshold but 2h above — 5m checked first but fails,
        # 2h is the fallback → True
        data = make_data(
            price_change_24h=-50.0,
            **make_agg_5m(55),   # below 60, won't trigger
        )
        # merge 2h as well
        data2 = make_data(
            price_change_24h=-50.0,
            buy_volume_5m=55_000, sell_volume_5m=45_000, trade_count_5m=50,
            buy_volume_2h=70_000, sell_volume_2h=30_000, trade_count_2h=100,
        )
        # 5m = 55% (fails), 2h = 70% (passes) → True
        assert az._is_post_crash_accumulation(data2) is True

    def test_5m_triggers_without_checking_2h(self):
        # 5m >= 60 → True immediately, 2h value irrelevant
        data = make_data(
            price_change_24h=-50.0,
            buy_volume_5m=65_000, sell_volume_5m=35_000, trade_count_5m=50,
            buy_volume_2h=30_000, sell_volume_2h=70_000, trade_count_2h=100,  # 2h would be False
        )
        assert az._is_post_crash_accumulation(data) is True


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests for _is_post_pump_distribution (PATH K)
# ─────────────────────────────────────────────────────────────────────────────

class TestIsPostPumpDistribution:

    def test_returns_false_when_price24h_is_none(self):
        data = make_data(price_change_24h=None, **make_agg_5m(30))
        assert az._is_post_pump_distribution(data) is False

    def test_returns_false_when_price24h_below_threshold(self):
        # +50.0 is not above +50 (strictly greater)
        data = make_data(price_change_24h=50.0, **make_agg_5m(30))
        assert az._is_post_pump_distribution(data) is False

    def test_returns_false_at_exactly_50(self):
        data = make_data(price_change_24h=50.0, **make_agg_5m(30))
        assert az._is_post_pump_distribution(data) is False

    def test_returns_true_with_5m_sellers_below_threshold(self):
        data = make_data(price_change_24h=70.0, **make_agg_5m(40))
        assert az._is_post_pump_distribution(data) is True

    def test_returns_true_with_5m_sellers_exactly_at_threshold(self):
        data = make_data(price_change_24h=70.0, **make_agg_5m(40.0))
        assert az._is_post_pump_distribution(data) is True

    def test_returns_false_when_5m_sellers_above_threshold(self):
        data = make_data(price_change_24h=70.0, **make_agg_5m(40.1))
        assert az._is_post_pump_distribution(data) is False

    def test_returns_true_with_2h_fallback_when_5m_none(self):
        data = make_data(price_change_24h=70.0, **make_agg_2h(35))
        assert az._is_post_pump_distribution(data) is True

    def test_returns_false_when_2h_fallback_above_threshold(self):
        data = make_data(price_change_24h=70.0, **make_agg_2h(40.1))
        assert az._is_post_pump_distribution(data) is False

    def test_returns_false_when_both_none(self):
        data = make_data(price_change_24h=70.0)
        assert az._is_post_pump_distribution(data) is False

    def test_5m_takes_priority_over_2h(self):
        # 5m above threshold (fails), 2h below threshold (passes) → True via fallback
        data = make_data(
            price_change_24h=70.0,
            buy_volume_5m=45_000, sell_volume_5m=55_000, trade_count_5m=50,  # 5m=45%, fails >40
            buy_volume_2h=30_000, sell_volume_2h=70_000, trade_count_2h=100,  # 2h=30%, passes
        )
        assert az._is_post_pump_distribution(data) is True

    def test_5m_triggers_without_checking_2h(self):
        # 5m <= 40 → True immediately, 2h value irrelevant
        data = make_data(
            price_change_24h=70.0,
            buy_volume_5m=35_000, sell_volume_5m=65_000, trade_count_5m=50,
            buy_volume_2h=70_000, sell_volume_2h=30_000, trade_count_2h=100,  # 2h would be False
        )
        assert az._is_post_pump_distribution(data) is True


# ─────────────────────────────────────────────────────────────────────────────
# Integration: full analyze() with BEARISH_DIVERGENCE (PATH J)
# ─────────────────────────────────────────────────────────────────────────────

class TestBearishDivergence:
    """price_change_1h < -threshold → would normally be BEARISH with blocks_long=True.
    When PATH J conditions met → BEARISH_DIVERGENCE with blocks_long=False."""

    def _bearish_data(self, **kwargs):
        base = dict(
            price_change_1h=-40.0,    # 5x vol ratio, threshold=5% → triggers BEARISH branch
            price_change_24h=-50.0,   # big dump ✓
        )
        base.update(kwargs)
        return make_data(**base)

    def test_bearish_divergence_direction(self):
        data = self._bearish_data(**make_agg_5m(65))
        result = az.analyze(data)
        assert result is not None
        assert 'BEARISH_DIVERGENCE' in result.reasoning

    def test_bearish_divergence_blocks_long_false(self):
        data = self._bearish_data(**make_agg_5m(65))
        result = az.analyze(data)
        assert result.blocks_long is False

    def test_bearish_divergence_blocks_short_false(self):
        data = self._bearish_data(**make_agg_5m(65))
        result = az.analyze(data)
        assert result.blocks_short is False

    def test_bearish_divergence_short_score_equals_spike_score(self):
        # Vol ratio = 5.0 → spike_score = 10.0
        data = self._bearish_data(**make_agg_5m(65))
        result = az.analyze(data)
        assert result.short_score == 10.0

    def test_bearish_divergence_long_score_zero(self):
        # Volume Spike doesn't give a long score — other analyzers must do that
        data = self._bearish_data(**make_agg_5m(65))
        result = az.analyze(data)
        assert result.long_score == 0.0

    def test_bearish_divergence_confidence_065(self):
        data = self._bearish_data(**make_agg_5m(65))
        result = az.analyze(data)
        assert result.confidence == 0.65

    def test_bearish_divergence_reasoning_contains_buyers_pct(self):
        data = self._bearish_data(**make_agg_5m(65))
        result = az.analyze(data)
        assert 'buyers 65%' in result.reasoning
        assert '5m' in result.reasoning

    def test_bearish_divergence_reasoning_mentions_blocks_long_lifted(self):
        data = self._bearish_data(**make_agg_5m(65))
        result = az.analyze(data)
        assert 'blocks_long lifted' in result.reasoning

    def test_bearish_divergence_uses_2h_fallback(self):
        data = self._bearish_data(**make_agg_2h(70))
        result = az.analyze(data)
        assert result is not None
        assert 'BEARISH_DIVERGENCE' in result.reasoning
        assert '2h' in result.reasoning
        assert result.blocks_long is False

    def test_bearish_divergence_exact_threshold_price24h(self):
        # -35.0% exactly does NOT trigger (strictly <)
        data = self._bearish_data(price_change_24h=-35.0, **make_agg_5m(65))
        result = az.analyze(data)
        assert result is not None
        assert 'BEARISH_DIVERGENCE' not in result.reasoning
        assert result.blocks_long is True  # normal BEARISH

    def test_bearish_divergence_exact_threshold_aggression(self):
        # 60.0% exactly DOES trigger (>=)
        data = self._bearish_data(price_change_24h=-50.0, **make_agg_5m(60.0))
        result = az.analyze(data)
        assert result is not None
        assert 'BEARISH_DIVERGENCE' in result.reasoning
        assert result.blocks_long is False

    # ── No divergence cases (should remain normal BEARISH) ──────────────────

    def test_no_divergence_when_dump_insufficient(self):
        data = self._bearish_data(price_change_24h=-15.0, **make_agg_5m(70))
        result = az.analyze(data)
        assert result is not None
        assert 'BEARISH_DIVERGENCE' not in result.reasoning
        assert result.blocks_long is True

    def test_no_divergence_when_buyers_not_active(self):
        data = self._bearish_data(price_change_24h=-50.0, **make_agg_5m(35))
        result = az.analyze(data)
        assert result is not None
        assert 'BEARISH_DIVERGENCE' not in result.reasoning
        assert result.blocks_long is True

    def test_no_divergence_when_aggression_none(self):
        data = self._bearish_data(price_change_24h=-50.0)  # no aggression data
        result = az.analyze(data)
        assert result is not None
        assert 'BEARISH_DIVERGENCE' not in result.reasoning
        assert result.blocks_long is True

    def test_no_divergence_when_price24h_none(self):
        data = self._bearish_data(price_change_24h=None, **make_agg_5m(70))
        result = az.analyze(data)
        assert result is not None
        assert 'BEARISH_DIVERGENCE' not in result.reasoning

    def test_no_divergence_exactly_59pct_aggression(self):
        data = self._bearish_data(price_change_24h=-50.0, **make_agg_5m(59.9))
        result = az.analyze(data)
        assert result is not None
        assert 'BEARISH_DIVERGENCE' not in result.reasoning
        assert result.blocks_long is True

    def test_normal_bearish_blocks_long_true_when_ratio_high(self):
        # Normal BEARISH with vol_ratio=5 → blocks_long=True (ratio>=2.0)
        data = self._bearish_data(price_change_24h=-15.0, **make_agg_5m(70))
        result = az.analyze(data)
        assert result.blocks_long is True

    def test_normal_bearish_confidence_high(self):
        # Normal BEARISH with ratio=5 → confidence=0.9
        data = self._bearish_data(price_change_24h=-15.0)
        result = az.analyze(data)
        assert result.confidence == 0.9


# ─────────────────────────────────────────────────────────────────────────────
# Integration: full analyze() with BULLISH_DIVERGENCE (PATH K)
# ─────────────────────────────────────────────────────────────────────────────

class TestBullishDivergence:
    """price_change_1h >= threshold → would normally be BULLISH with blocks_short=True.
    When PATH K conditions met → BULLISH_DIVERGENCE with blocks_short=False."""

    def _bullish_data(self, **kwargs):
        base = dict(
            price_change_1h=20.0,     # 5x vol ratio, threshold=5% → triggers BULLISH branch
            price_change_24h=70.0,    # big pump ✓
        )
        base.update(kwargs)
        return make_data(**base)

    def test_bullish_divergence_direction(self):
        data = self._bullish_data(**make_agg_5m(35))
        result = az.analyze(data)
        assert result is not None
        assert 'BULLISH_DIVERGENCE' in result.reasoning

    def test_bullish_divergence_blocks_short_false(self):
        data = self._bullish_data(**make_agg_5m(35))
        result = az.analyze(data)
        assert result.blocks_short is False

    def test_bullish_divergence_blocks_long_false(self):
        data = self._bullish_data(**make_agg_5m(35))
        result = az.analyze(data)
        assert result.blocks_long is False

    def test_bullish_divergence_short_score_is_4(self):
        data = self._bullish_data(**make_agg_5m(35))
        result = az.analyze(data)
        assert result.short_score == 4.0

    def test_bullish_divergence_long_score_equals_spike_score(self):
        # Vol ratio = 5.0 → spike_score = 10.0
        data = self._bullish_data(**make_agg_5m(35))
        result = az.analyze(data)
        assert result.long_score == 10.0

    def test_bullish_divergence_confidence_065(self):
        data = self._bullish_data(**make_agg_5m(35))
        result = az.analyze(data)
        assert result.confidence == 0.65

    def test_bullish_divergence_reasoning_contains_sellers_pct(self):
        data = self._bullish_data(**make_agg_5m(35))
        result = az.analyze(data)
        assert 'sellers 35%' in result.reasoning
        assert '5m' in result.reasoning

    def test_bullish_divergence_reasoning_mentions_blocks_short_lifted(self):
        data = self._bullish_data(**make_agg_5m(35))
        result = az.analyze(data)
        assert 'blocks_short lifted' in result.reasoning

    def test_bullish_divergence_uses_2h_fallback(self):
        data = self._bullish_data(**make_agg_2h(30))
        result = az.analyze(data)
        assert result is not None
        assert 'BULLISH_DIVERGENCE' in result.reasoning
        assert '2h' in result.reasoning
        assert result.blocks_short is False

    def test_bullish_divergence_exact_threshold_price24h(self):
        # +50.0% exactly does NOT trigger (strictly >)
        data = self._bullish_data(price_change_24h=50.0, **make_agg_5m(35))
        result = az.analyze(data)
        assert result is not None
        assert 'BULLISH_DIVERGENCE' not in result.reasoning
        assert result.blocks_short is True  # normal BULLISH

    def test_bullish_divergence_exact_threshold_aggression(self):
        # 40.0% exactly DOES trigger (<=)
        data = self._bullish_data(price_change_24h=70.0, **make_agg_5m(40.0))
        result = az.analyze(data)
        assert result is not None
        assert 'BULLISH_DIVERGENCE' in result.reasoning
        assert result.blocks_short is False

    # ── No divergence cases (should remain normal BULLISH) ──────────────────

    def test_no_divergence_when_pump_insufficient(self):
        data = self._bullish_data(price_change_24h=20.0, **make_agg_5m(30))
        result = az.analyze(data)
        assert result is not None
        assert 'BULLISH_DIVERGENCE' not in result.reasoning
        assert result.blocks_short is True

    def test_no_divergence_when_sellers_not_dominant(self):
        data = self._bullish_data(price_change_24h=70.0, **make_agg_5m(65))
        result = az.analyze(data)
        assert result is not None
        assert 'BULLISH_DIVERGENCE' not in result.reasoning
        assert result.blocks_short is True

    def test_no_divergence_when_aggression_none(self):
        data = self._bullish_data(price_change_24h=70.0)
        result = az.analyze(data)
        assert result is not None
        assert 'BULLISH_DIVERGENCE' not in result.reasoning
        assert result.blocks_short is True

    def test_no_divergence_when_price24h_none(self):
        data = self._bullish_data(price_change_24h=None, **make_agg_5m(30))
        result = az.analyze(data)
        assert result is not None
        assert 'BULLISH_DIVERGENCE' not in result.reasoning

    def test_no_divergence_exactly_41pct_aggression(self):
        data = self._bullish_data(price_change_24h=70.0, **make_agg_5m(40.1))
        result = az.analyze(data)
        assert result is not None
        assert 'BULLISH_DIVERGENCE' not in result.reasoning
        assert result.blocks_short is True

    def test_normal_bullish_blocks_short_true_when_ratio_high(self):
        # Normal BULLISH with vol_ratio=5 → blocks_short=True (ratio>=2.0)
        data = self._bullish_data(price_change_24h=20.0, **make_agg_5m(30))
        result = az.analyze(data)
        assert result.blocks_short is True

    def test_normal_bullish_confidence_high(self):
        # Normal BULLISH with ratio=5 → confidence=0.9
        data = self._bullish_data(price_change_24h=20.0)
        result = az.analyze(data)
        assert result.confidence == 0.9


# ─────────────────────────────────────────────────────────────────────────────
# Unchanged behavior: PRE_PUMP / PRE_DUMP early detection
# ─────────────────────────────────────────────────────────────────────────────

class TestEarlyDetectionUnchanged:
    """PRE_PUMP / PRE_DUMP path (price between -threshold and +threshold)
    must be completely unaffected by PATH J/K changes."""

    def _neutral_price_data(self, **kwargs):
        base = dict(price_change_1h=2.0)  # within ±5% → neutral price
        base.update(kwargs)
        return make_data(**base)

    def test_pre_pump_direction(self):
        data = self._neutral_price_data(
            buy_volume_5m=80_000, sell_volume_5m=20_000, trade_count_5m=30,
            price_change_24h=70.0,
        )
        result = az.analyze(data)
        assert result is not None
        assert 'PRE_PUMP' in result.reasoning

    def test_pre_pump_is_divergence_false(self):
        # is_divergence stays False in early detection path
        data = self._neutral_price_data(
            buy_volume_5m=80_000, sell_volume_5m=20_000, trade_count_5m=30,
        )
        result = az.analyze(data)
        assert result is not None
        assert result.confidence in (0.65, 0.70)  # early detection confidences

    def test_pre_dump_direction(self):
        data = self._neutral_price_data(
            buy_volume_5m=20_000, sell_volume_5m=80_000, trade_count_5m=30,
            price_change_24h=-50.0,
        )
        result = az.analyze(data)
        assert result is not None
        assert 'PRE_DUMP' in result.reasoning

    def test_no_early_detection_without_sufficient_trade_count(self):
        data = self._neutral_price_data(
            buy_volume_5m=80_000, sell_volume_5m=20_000, trade_count_5m=5,  # < 20
        )
        result = az.analyze(data)
        assert result is None  # insufficient trades → return None


# ─────────────────────────────────────────────────────────────────────────────
# Unchanged behavior: normal BTC-like tokens (no extreme 24h moves)
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalTokensUnchanged:
    """Tokens with typical 24h moves should behave exactly as before PATH J/K."""

    def test_bearish_normal_range(self):
        # Typical correction -10%
        data = make_data(
            price_change_1h=-15.0,
            price_change_24h=-10.0,
            **make_agg_5m(70),
        )
        result = az.analyze(data)
        assert result is not None
        assert 'BEARISH' in result.reasoning
        assert 'DIVERGENCE' not in result.reasoning
        assert result.blocks_long is True

    def test_bullish_normal_range(self):
        # Typical pump +20%
        data = make_data(
            price_change_1h=15.0,
            price_change_24h=20.0,
            **make_agg_5m(35),
        )
        result = az.analyze(data)
        assert result is not None
        assert 'BULLISH' in result.reasoning
        assert 'DIVERGENCE' not in result.reasoning
        assert result.blocks_short is True

    def test_btc_style_moderate_move(self):
        # BTC -5% in 24h with high buying aggression → no divergence
        data = make_data(
            price_change_1h=-8.0,
            price_change_24h=-5.0,
            **make_agg_5m(75),
        )
        result = az.analyze(data)
        assert result is not None
        assert 'BEARISH_DIVERGENCE' not in result.reasoning


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases and boundary conditions
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_both_5m_and_2h_satisfy_crash_accumulation(self):
        # Both conditions true — 5m should win in reasoning
        data = make_data(
            price_change_1h=-40.0,
            price_change_24h=-60.0,
            buy_volume_5m=70_000, sell_volume_5m=30_000, trade_count_5m=50,  # 5m=70% ✓
            buy_volume_2h=65_000, sell_volume_2h=35_000, trade_count_2h=100,  # 2h=65% ✓
        )
        result = az.analyze(data)
        assert result is not None
        assert 'BEARISH_DIVERGENCE' in result.reasoning
        assert '5m' in result.reasoning  # 5m takes priority

    def test_both_5m_and_2h_satisfy_pump_distribution(self):
        data = make_data(
            price_change_1h=20.0,
            price_change_24h=80.0,
            buy_volume_5m=30_000, sell_volume_5m=70_000, trade_count_5m=50,  # 5m=30% ✓
            buy_volume_2h=35_000, sell_volume_2h=65_000, trade_count_2h=100,  # 2h=35% ✓
        )
        result = az.analyze(data)
        assert result is not None
        assert 'BULLISH_DIVERGENCE' in result.reasoning
        assert '5m' in result.reasoning

    def test_divergence_uses_2h_when_5m_fails_crash(self):
        # 5m=55% (fails), 2h=65% (passes) → 2h in reasoning
        data = make_data(
            price_change_1h=-40.0,
            price_change_24h=-60.0,
            buy_volume_5m=55_000, sell_volume_5m=45_000, trade_count_5m=50,
            buy_volume_2h=65_000, sell_volume_2h=35_000, trade_count_2h=100,
        )
        result = az.analyze(data)
        assert result is not None
        assert 'BEARISH_DIVERGENCE' in result.reasoning
        assert '2h' in result.reasoning

    def test_divergence_uses_2h_when_5m_fails_pump(self):
        # 5m=45% (fails), 2h=35% (passes) → 2h in reasoning
        data = make_data(
            price_change_1h=20.0,
            price_change_24h=70.0,
            buy_volume_5m=45_000, sell_volume_5m=55_000, trade_count_5m=50,
            buy_volume_2h=35_000, sell_volume_2h=65_000, trade_count_2h=100,
        )
        result = az.analyze(data)
        assert result is not None
        assert 'BULLISH_DIVERGENCE' in result.reasoning
        assert '2h' in result.reasoning

    def test_spike_score_affects_short_score_in_bearish_divergence(self):
        # vol_ratio = 3.0 → spike_score = 9.0
        data = make_data(
            volume_1h=300_000,    # ratio = 3.0
            avg_volume_1h=100_000,
            price_change_1h=-40.0,
            price_change_24h=-50.0,
            **make_agg_5m(65),
        )
        result = az.analyze(data)
        assert result is not None
        assert result.short_score == 9.0
        assert 'BEARISH_DIVERGENCE' in result.reasoning

    def test_spike_score_affects_long_score_in_bullish_divergence(self):
        # vol_ratio = 3.0 → spike_score = 9.0
        data = make_data(
            volume_1h=300_000,
            avg_volume_1h=100_000,
            price_change_1h=20.0,
            price_change_24h=70.0,
            **make_agg_5m(35),
        )
        result = az.analyze(data)
        assert result is not None
        assert result.long_score == 9.0
        assert result.short_score == 4.0

    def test_key_value_is_volume_ratio(self):
        data = make_data(
            price_change_1h=-40.0,
            price_change_24h=-50.0,
            **make_agg_5m(65),
        )
        result = az.analyze(data)
        assert result.key_value == pytest.approx(5.0, rel=0.01)
        assert result.key_label == 'Volume Ratio'

    def test_alert_level_critical_on_5x_volume(self):
        # vol_ratio = 5.0 → alert_level = 'critical'
        data = make_data(
            price_change_1h=-40.0,
            price_change_24h=-50.0,
            **make_agg_5m(65),
        )
        result = az.analyze(data)
        assert result.alert_level == 'critical'

    def test_returns_none_when_no_volume_spike(self):
        # vol_ratio = 1.2 → spike_score = 0 → return None
        data = make_data(
            volume_1h=120_000,
            avg_volume_1h=100_000,
            price_change_1h=-40.0,
            price_change_24h=-50.0,
            **make_agg_5m(65),
        )
        result = az.analyze(data)
        assert result is None

    def test_confidence_calculation_not_called_for_none_result(self):
        # Should not crash even if data is incomplete
        data = make_data(volume_1h=None)
        result = az.analyze(data)
        assert result is None

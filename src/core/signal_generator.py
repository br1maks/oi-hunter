import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)
from ..models.market_data import MarketData
from ..models.signal import Signal, Target
from ..models.analyzer_result import AnalyzerResult
from ..analyzers.oi_mc_analyzer import OIMCAnalyzer
from ..analyzers.funding_rate_analyzer import FundingRateAnalyzer
from ..analyzers.aggression_analyzer import AggressionAnalyzer
from ..analyzers.liquidation_analyzer import LiquidationAnalyzer
from ..analyzers.volume_spike_analyzer import VolumeSpikeAnalyzer
from ..analyzers.already_pumped_analyzer import AlreadyPumpedAnalyzer
from ..analyzers.oi_nowcast_analyzer import OINowcastAnalyzer
from ..analyzers.order_book_analyzer import OrderBookAnalyzer
from ..analyzers.market_regime_detector import MarketRegimeDetector
from ..analyzers.oi_divergence_analyzer import OIDivergenceAnalyzer

class SignalGenerator:
    MIN_SIGNAL_SCORE = 6.5
    MIN_ANALYZERS = 3
    REQUIRED_OI_ANALYZERS = {'OI/MC Analyzer', 'OI Nowcast'}
    KINETIC_ANALYZERS = {'Volume Spike Analyzer', 'OI Nowcast'}
    MIN_KINETIC_SCORE = 6.0
    COVERAGE_MULTIPLIERS = {1: 0.5, 2: 0.7, 3: 0.85, 4: 0.95}
    MOMENTUM_AGGRESSION_MIN = 9.0
    MOMENTUM_VOLUME_MIN = 6.0
    MIN_VOLUME_24H = 100000
    MIN_PRICE_CHANGE_24H = 0.1
    STOP_LOSS_ATR_MULT = 2.0
    TARGET1_ATR_MULT = 1.5
    TARGET2_ATR_MULT = 3.0
    TARGET3_ATR_MULT = 4.0
    STOP_LOSS_PERCENT = 10.0
    TARGET1_PERCENT = 4.0
    TARGET2_PERCENT = 8.0
    TARGET3_PERCENT = 15.0

    def __init__(self):
        self._oi_nowcast = OINowcastAnalyzer(weight=1.5)
        self._regime_detector = MarketRegimeDetector()
        self.analyzers = [OIMCAnalyzer(weight=2.0), FundingRateAnalyzer(weight=1.0), AggressionAnalyzer(weight=1.5), LiquidationAnalyzer(weight=1.0), VolumeSpikeAnalyzer(weight=1.0), AlreadyPumpedAnalyzer(weight=0.5), OrderBookAnalyzer(weight=1.0), self._oi_nowcast, OIDivergenceAnalyzer(weight=1.25)]

    def set_database(self, db) -> None:
        self._oi_nowcast.set_database(db)

    def begin_cycle(self) -> None:
        OINowcastAnalyzer.begin_cycle()

    def generate(self, data: MarketData) -> Optional[Signal]:
        sym = data.symbol
        if data.volume_24h < self.MIN_VOLUME_24H:
            logger.info(f'[Signal] {sym} → NO SIGNAL: volume ${data.volume_24h:,.0f} < ${self.MIN_VOLUME_24H:,.0f}')
            return None
        if data.price_change_24h is not None and abs(data.price_change_24h) < self.MIN_PRICE_CHANGE_24H:
            logger.info(f'[Signal] {sym} → NO SIGNAL: price_change_24h {data.price_change_24h:.2f}% too flat')
            return None
        results: list[AnalyzerResult] = []
        for analyzer in self.analyzers:
            result = analyzer.analyze(data)
            if result is not None:
                results.append(result)
        if len(results) < self.MIN_ANALYZERS:
            logger.info(f'[Signal] {sym} → NO SIGNAL: only {len(results)} analyzers fired (min {self.MIN_ANALYZERS})')
            return None
        result_names = {r.analyzer_name for r in results}
        if not result_names & self.REQUIRED_OI_ANALYZERS:
            logger.info(f'[Signal] {sym} → NO SIGNAL: missing required OI analyzer (got {result_names})')
            return None
        self._apply_momentum_override(results)
        self._apply_extreme_funding_override(results, data)
        blocks_long = any((r.blocks_long for r in results))
        blocks_short = any((r.blocks_short for r in results))
        long_score, long_confidence = self._calculate_weighted_score(results, direction='long')
        short_score, short_confidence = self._calculate_weighted_score(results, direction='short')
        coverage_mult = self.COVERAGE_MULTIPLIERS.get(len(results), 1.0)
        long_score *= coverage_mult
        short_score *= coverage_mult
        regime = self._regime_detector.detect(data)
        logger.debug(f'[Regime] {sym} → {regime.regime}: {regime.reasoning}')
        if regime.skip:
            logger.info(f'[Signal] {sym} → NO SIGNAL: regime={regime.regime} ({regime.reasoning})')
            return None
        long_score = min(10.0, long_score * regime.long_mult)
        short_score = min(10.0, short_score * regime.short_mult)
        direction = None
        final_score = 0.0
        final_confidence = 0.0
        long_valid = long_score >= self.MIN_SIGNAL_SCORE and (not blocks_long)
        short_valid = short_score >= self.MIN_SIGNAL_SCORE and (not blocks_short)
        if not long_valid and long_score >= self.MIN_SIGNAL_SCORE and blocks_long:
            blockers = [r.analyzer_name for r in results if r.blocks_long]
            logger.info(f'[Signal] {sym} → LONG blocked by: {blockers} (score={long_score:.1f})')
        if not short_valid and short_score >= self.MIN_SIGNAL_SCORE and blocks_short:
            blockers = [r.analyzer_name for r in results if r.blocks_short]
            logger.info(f'[Signal] {sym} → SHORT blocked by: {blockers} (score={short_score:.1f})')
        if long_valid:
            long_valid = self._check_kinetic_confirmation(results, 'LONG')
            if not long_valid:
                kinetic_scores = {r.analyzer_name: r.long_score for r in results if r.analyzer_name in self.KINETIC_ANALYZERS}
                logger.info(f'[Signal] {sym} → LONG kinetic check failed (need >={self.MIN_KINETIC_SCORE}): {kinetic_scores}, raw_score={long_score:.1f}')
        if short_valid:
            short_valid = self._check_kinetic_confirmation(results, 'SHORT')
            if not short_valid:
                kinetic_scores = {r.analyzer_name: r.short_score for r in results if r.analyzer_name in self.KINETIC_ANALYZERS}
                logger.info(f'[Signal] {sym} → SHORT kinetic check failed (need >={self.MIN_KINETIC_SCORE}): {kinetic_scores}, raw_score={short_score:.1f}')
        if long_valid and short_valid:
            if long_score >= short_score:
                direction = 'LONG'
                final_score = long_score
                final_confidence = long_confidence
            else:
                direction = 'SHORT'
                final_score = short_score
                final_confidence = short_confidence
        elif long_valid:
            direction = 'LONG'
            final_score = long_score
            final_confidence = long_confidence
        elif short_valid:
            direction = 'SHORT'
            final_score = short_score
            final_confidence = short_confidence
        else:
            if long_score < self.MIN_SIGNAL_SCORE and short_score < self.MIN_SIGNAL_SCORE:
                logger.info(f'[Signal] {sym} → NO SIGNAL: scores too low L={long_score:.1f} S={short_score:.1f} (min {self.MIN_SIGNAL_SCORE})')
            return None
        entry_price = data.price
        stop_loss, stop_loss_percent = self._calculate_stop_loss(data, direction)
        targets = self._calculate_targets(data, direction)
        key_factors = self._extract_key_factors(results, direction)
        reason = self._generate_reason(direction, final_score, blocks_long, blocks_short, results)
        return Signal(symbol=data.symbol, timestamp=datetime.now(timezone.utc), direction=direction, entry_price=entry_price, stop_loss=stop_loss, stop_loss_percent=stop_loss_percent, targets=targets, overall_score=round(final_score, 1), confidence=round(final_confidence, 2), analyzer_results=results, reason=reason, key_factors=key_factors, current_price=data.price, oi_mc_ratio=data.oi_mc_ratio, market_cap_usd=data.market_cap_usd, funding_rate=data.funding_rate, volume_24h=data.volume_24h, price_change_24h=data.price_change_24h, exchange=data.exchange, is_new_listing=data.is_new_listing, days_since_listing=data.days_since_listing, liquidation_detected=data.liquidation_detected, liquidation_side=data.liquidation_side, liquidation_volume=data.liquidation_volume, liquidation_context=data.liquidation_context)

    def analyze_only(self, data: MarketData) -> dict:
        results: list[AnalyzerResult] = []
        for analyzer in self.analyzers:
            result = analyzer.analyze(data)
            if result is not None:
                results.append(result)
        self._apply_momentum_override(results)
        self._apply_extreme_funding_override(results, data)
        result_names = {r.analyzer_name for r in results}
        insufficient = len(results) < self.MIN_ANALYZERS or not result_names & self.REQUIRED_OI_ANALYZERS
        blocks_long = any((r.blocks_long for r in results))
        blocks_short = any((r.blocks_short for r in results))
        long_score, long_confidence = self._calculate_weighted_score(results, direction='long')
        short_score, short_confidence = self._calculate_weighted_score(results, direction='short')
        coverage_mult = self.COVERAGE_MULTIPLIERS.get(len(results), 1.0)
        long_score *= coverage_mult
        short_score *= coverage_mult
        regime = self._regime_detector.detect(data)
        long_score = min(10.0, long_score * regime.long_mult)
        short_score = min(10.0, short_score * regime.short_mult)
        long_valid = long_score >= self.MIN_SIGNAL_SCORE and (not blocks_long)
        short_valid = short_score >= self.MIN_SIGNAL_SCORE and (not blocks_short)
        if long_valid:
            long_valid = self._check_kinetic_confirmation(results, 'LONG')
        if short_valid:
            short_valid = self._check_kinetic_confirmation(results, 'SHORT')
        would_signal = 'INSUFFICIENT DATA' if insufficient else 'LONG' if long_valid else 'SHORT' if short_valid else 'NO SIGNAL'
        if regime.skip:
            would_signal = 'NO SIGNAL (ILLIQUID)'
        return {'symbol': data.symbol, 'results': results, 'long_score': round(long_score, 1), 'short_score': round(short_score, 1), 'long_confidence': round(long_confidence, 2), 'short_confidence': round(short_confidence, 2), 'blocks_long': blocks_long, 'blocks_short': blocks_short, 'would_signal': would_signal, 'analyzers_count': len(results), 'coverage_mult': round(coverage_mult, 2), 'regime': regime.regime, 'regime_reasoning': regime.reasoning}

    def _calculate_weighted_score(self, results: list[AnalyzerResult], direction: str) -> tuple[float, float]:
        if not results:
            return (0.0, 0.0)
        weight_map = {a.analyzer_name: a.weight for a in self.analyzers}
        total_weighted_score = 0.0
        total_weight = 0.0
        total_confidence = 0.0
        for result in results:
            weight = weight_map.get(result.analyzer_name, 1.0)
            score = result.long_score if direction == 'long' else result.short_score
            confidence = result.confidence
            effective_weight = weight * confidence
            total_weighted_score += score * effective_weight
            total_weight += effective_weight
            total_confidence += confidence
        if total_weight == 0:
            return (0.0, 0.0)
        weighted_score = total_weighted_score / total_weight
        avg_confidence = total_confidence / len(results)
        return (weighted_score, avg_confidence)

    def _check_kinetic_confirmation(self, results: list[AnalyzerResult], direction: str) -> bool:
        for r in results:
            if r.analyzer_name in self.KINETIC_ANALYZERS:
                score = r.long_score if direction == 'LONG' else r.short_score
                if score >= self.MIN_KINETIC_SCORE:
                    return True
        return False

    def _apply_momentum_override(self, results: list[AnalyzerResult]) -> bool:
        aggression_long = 0.0
        volume_long = 0.0
        oi_mc_ratio = None
        for r in results:
            if r.analyzer_name == 'Aggression Analyzer':
                aggression_long = r.long_score
            elif r.analyzer_name == 'Volume Spike Analyzer':
                volume_long = r.long_score
            elif r.analyzer_name == 'OI/MC Analyzer':
                # key_value holds the actual OI/MC ratio for this analyzer
                oi_mc_ratio = r.key_value
        if not (aggression_long >= self.MOMENTUM_AGGRESSION_MIN and volume_long >= self.MOMENTUM_VOLUME_MIN):
            return False
        # Never override when OI/MC is in short/danger territory (>= 0.60).
        # High aggression + volume spike in an overleveraged market = retail FOMO
        # at the top, not a genuine long setup. Entering long here is a trap.
        if oi_mc_ratio is not None and oi_mc_ratio >= 0.60:
            return False
        applied = False
        for r in results:
            if r.analyzer_name == 'OI/MC Analyzer' and r.blocks_long:
                # only neutralize the block if ratio is below danger threshold
                if oi_mc_ratio is None or oi_mc_ratio < 0.60:
                    r.blocks_long = False
                    r.long_score = max(r.long_score, 5.0)
                    r.reasoning += ' | MOMENTUM OVERRIDE: OI/MC block lifted by strong momentum'
                    applied = True
            elif r.analyzer_name == 'Already Pumped Analyzer' and r.blocks_long:
                r.blocks_long = False
                r.long_score = 5.0
                r.short_score = min(r.short_score, 3.0)
                r.reasoning += ' | MOMENTUM OVERRIDE: pump block lifted by strong momentum'
                applied = True
        return applied

    def _apply_extreme_funding_override(self, results: list[AnalyzerResult], data: MarketData) -> bool:
        """Lift blocks_short/blocks_long from Aggression and Volume Spike when funding is extreme (≥ 0.2%).

        Extreme positive funding means longs are structurally overloaded — even a bullish
        volume spike shouldn't block SHORT in this context (distribution top).
        Symmetric: extreme negative funding lifts blocks_long from both analyzers.
        """
        THRESHOLD = 0.002  # 0.2%
        OVERRIDE_ANALYZERS = {'Aggression Analyzer', 'Volume Spike Analyzer'}
        rate = data.funding_rate or 0.0
        applied = False
        if rate >= THRESHOLD:
            for r in results:
                if r.analyzer_name in OVERRIDE_ANALYZERS and r.blocks_short:
                    r.blocks_short = False
                    r.short_score = max(r.short_score, 2.0)
                    r.reasoning += f' | EXTREME FUNDING OVERRIDE: blocks_short lifted (funding {rate * 100:.3f}%)'
                    applied = True
        elif rate <= -THRESHOLD:
            for r in results:
                if r.analyzer_name in OVERRIDE_ANALYZERS and r.blocks_long:
                    r.blocks_long = False
                    r.long_score = max(r.long_score, 2.0)
                    r.reasoning += f' | EXTREME FUNDING OVERRIDE: blocks_long lifted (funding {rate * 100:.3f}%)'
                    applied = True
        return applied

    def _calculate_stop_loss(self, data: MarketData, direction: str) -> tuple[float, float]:
        price = data.price
        if data.atr and data.atr > 0:
            stop_distance = data.atr * self.STOP_LOSS_ATR_MULT
            stop_percent = stop_distance / price * 100
        else:
            stop_percent = self.STOP_LOSS_PERCENT
            stop_distance = price * (stop_percent / 100)
        if direction == 'LONG':
            stop_price = price - stop_distance
            stop_percent = -stop_percent
        else:
            stop_price = price + stop_distance
            stop_percent = stop_percent
        return (max(0.001, stop_price), round(stop_percent, 2))

    def _calculate_targets(self, data: MarketData, direction: str) -> list[Target]:
        price = data.price
        if data.atr and data.atr > 0:
            t1_dist = data.atr * self.TARGET1_ATR_MULT
            t2_dist = data.atr * self.TARGET2_ATR_MULT
            t3_dist = data.atr * self.TARGET3_ATR_MULT
        else:
            t1_dist = price * (self.TARGET1_PERCENT / 100)
            t2_dist = price * (self.TARGET2_PERCENT / 100)
            t3_dist = price * (self.TARGET3_PERCENT / 100)
        if direction == 'LONG':
            t1_price = price + t1_dist
            t2_price = price + t2_dist
            t3_price = price + t3_dist
            t1_gain = t1_dist / price * 100
            t2_gain = t2_dist / price * 100
            t3_gain = t3_dist / price * 100
        else:
            t1_price = price - t1_dist
            t2_price = price - t2_dist
            t3_price = price - t3_dist
            t1_gain = t1_dist / price * 100
            t2_gain = t2_dist / price * 100
            t3_gain = t3_dist / price * 100
        return [Target(target_number=1, target_price=round(t1_price, 6), percent_allocation=30.0, expected_gain_percent=round(t1_gain, 2)), Target(target_number=2, target_price=round(t2_price, 6), percent_allocation=40.0, expected_gain_percent=round(t2_gain, 2)), Target(target_number=3, target_price=round(t3_price, 6), percent_allocation=30.0, expected_gain_percent=round(t3_gain, 2))]

    def _extract_key_factors(self, results: list[AnalyzerResult], direction: str) -> list[str]:
        factors = []
        for result in results:
            score = result.long_score if direction == 'LONG' else result.short_score
            if score >= 5:
                factor = f'{result.analyzer_name}: {result.reasoning}'
                factors.append((score, factor))
            if result.blocks_long and direction == 'LONG':
                factors.append((10, f'⚠️ {result.analyzer_name} blocked LONG'))
            if result.blocks_short and direction == 'SHORT':
                factors.append((10, f'⚠️ {result.analyzer_name} blocked SHORT'))
        factors.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in factors[:5]]

    def _generate_reason(self, direction: str, score: float, blocks_long: bool, blocks_short: bool, results: list[AnalyzerResult]) -> str:
        strongest = []
        for r in results:
            s = r.long_score if direction == 'LONG' else r.short_score
            if s >= 7:
                strongest.append(r.analyzer_name.replace(' Analyzer', ''))
        reason_parts = [f'{direction} signal (score {score:.1f}/10)']
        if strongest:
            reason_parts.append(f"Strong: {', '.join(strongest)}")
        critical = [r for r in results if r.alert_level == 'critical']
        if critical:
            reason_parts.append(f'Critical: {len(critical)} alerts')
        return ' | '.join(reason_parts)
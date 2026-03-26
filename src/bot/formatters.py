from typing import Optional
from src.models.signal import Signal
from src.models.market_data import MarketData
from src.models.analyzer_result import AnalyzerResult

def format_signal_alert(signal: Signal, market_data: MarketData) -> str:
    symbol = _clean_symbol(signal.symbol)
    direction = signal.direction
    base_emoji = '🟢' if direction == 'LONG' else '🔴'
    nowcast_full = _nowcast_is_full(signal.analyzer_results)
    emoji = f'{base_emoji}{base_emoji}{base_emoji}' if nowcast_full else base_emoji
    lc_flag = ' [LC]' if signal.market_cap_usd and signal.market_cap_usd < 30000000 else ''
    header = f'{emoji} {direction} SIGNAL: {symbol}{lc_flag}'
    analyzer_count = len(signal.analyzer_results)
    score_line = f'Score: {signal.overall_score:.1f}/10  ({analyzer_count} analyzers)'
    lines = [header, score_line, '━━━━━━━━━━━━━━━━━━━━━', '']
    lines.append(f'Price:   {_fmt_price(signal.current_price)}')
    if market_data.open_interest_usd:
        lines.append(f'OI:      ${market_data.open_interest_usd:,.0f}')
    if signal.oi_mc_ratio is not None:
        lines.append(f'OI/MC:   {signal.oi_mc_ratio:.4f}')
    elif signal.market_cap_usd is None:
        lines.append('OI/MC:   N/A (MC unknown)')
    if market_data.oi_change_1h is not None:
        lines.append(f'OI Δ1h:  {market_data.oi_change_1h:+.1f}%')
    if market_data.oi_change_5m is not None:
        lines.append(f'OI Δ5m:  {market_data.oi_change_5m:+.1f}%')
    if signal.funding_rate is not None:
        lines.append(f'FR:      {signal.funding_rate * 100:+.4f}%')
    if signal.volume_24h:
        lines.append(f'Vol 24h: ${signal.volume_24h:,.0f}')
    if signal.market_cap_usd:
        lines.append(f'MC:      ${signal.market_cap_usd:,.0f}')
    if market_data.price_change_1h is not None:
        lines.append(f'Chg 1h:  {market_data.price_change_1h:+.2f}%')
    if market_data.price_change_24h is not None:
        lines.append(f'Chg 24h: {market_data.price_change_24h:+.2f}%')
    vol_spike = _extract_vol_spike_ratio(signal.analyzer_results)
    if vol_spike is not None:
        lines.append(f'Vol Spike: {vol_spike:.1f}x')
    agg5 = market_data.aggression_5m
    agg2h = market_data.aggression_2h
    if agg5 is not None or agg2h is not None:
        lines.append('')
        lines.append('Aggression:')
        if agg5 is not None:
            side5 = 'buy' if agg5 >= 50 else 'sell'
            lines.append(f'  5m:  {agg5:.1f}% {side5}')
        if agg2h is not None:
            side2h = 'buy' if agg2h >= 50 else 'sell'
            lines.append(f'  2h:  {agg2h:.1f}% {side2h}')
    if market_data.liquidation_detected:
        liq_line = 'Liquidation:'
        if market_data.liquidation_side:
            liq_line += f' {market_data.liquidation_side}'
        if market_data.liquidation_volume:
            liq_line += f' ${market_data.liquidation_volume:,.0f}'
        if market_data.liquidation_context:
            liq_line += f' [{market_data.liquidation_context}]'
        lines.append('')
        lines.append(liq_line)
    ob_line = _extract_order_book_line(signal.analyzer_results)
    if ob_line:
        lines.append('')
        lines.append(ob_line)
    nowcast = _extract_nowcast_line(signal.analyzer_results)
    if nowcast:
        lines.append('')
        lines.append(nowcast)
    blocks = _extract_blocks(signal.analyzer_results, direction)
    if blocks:
        lines.append('')
        for b in blocks:
            lines.append(b)
    return '\n'.join(lines)

def format_analysis_result(symbol: str, analysis: dict, market_data: MarketData) -> str:
    symbol_clean = _clean_symbol(symbol)
    long_score = analysis.get('long_score', 0)
    short_score = analysis.get('short_score', 0)
    if long_score >= 7.0 and long_score >= short_score:
        emoji, score_line = ('🟢', f'LONG {long_score:.1f}/10')
    elif short_score >= 7.0:
        emoji, score_line = ('🔴', f'SHORT {short_score:.1f}/10')
    elif long_score >= 5.0:
        emoji, score_line = ('🟡', f'Watch L:{long_score:.1f} S:{short_score:.1f}')
    else:
        emoji, score_line = ('⚪', f'No signal  L:{long_score:.1f} S:{short_score:.1f}')
    lines = [f'{emoji} {symbol_clean}', f'Score: {score_line}', '━━━━━━━━━━━━━━━━━━━━━']
    lines.append(f'Price:   {_fmt_price(market_data.price)}')
    if market_data.open_interest_usd:
        lines.append(f'OI:      ${market_data.open_interest_usd:,.0f}')
    if market_data.oi_mc_ratio is not None:
        lines.append(f'OI/MC:   {market_data.oi_mc_ratio:.4f}')
    elif market_data.market_cap_usd is None:
        lines.append('OI/MC:   N/A (MC unknown)')
    if market_data.funding_rate is not None:
        lines.append(f'FR:      {market_data.funding_rate * 100:+.4f}%')
    if market_data.volume_24h:
        lines.append(f'Vol 24h: ${market_data.volume_24h:,.0f}')
    if market_data.market_cap_usd:
        lines.append(f'MC:      ${market_data.market_cap_usd:,.0f}')
    agg5 = market_data.aggression_5m
    agg2h = market_data.aggression_2h
    if agg5 is not None or agg2h is not None:
        lines.append('')
        lines.append('Aggression:')
        if agg5 is not None:
            lines.append(f"  5m:  {agg5:.1f}% {('buy' if agg5 >= 50 else 'sell')}")
        if agg2h is not None:
            lines.append(f"  2h:  {agg2h:.1f}% {('buy' if agg2h >= 50 else 'sell')}")
    results: list[AnalyzerResult] = analysis.get('results', [])
    if results:
        lines.append('')
        lines.append('Analyzers:')
        for r in results:
            name = r.analyzer_name[:20].ljust(20)
            flag = ''
            if r.blocks_long:
                flag = ' [BL]'
            elif r.blocks_short:
                flag = ' [BS]'
            lines.append(f'  {name} L={r.long_score:.0f} S={r.short_score:.0f}{flag}')
            if 'Nowcast' in r.analyzer_name and r.reasoning:
                lines.append(f'  -> {r.reasoning}')
    return '\n'.join(lines)

def format_watchlist(symbols: list[str]) -> str:
    if not symbols:
        return 'Watchlist пуст.\n\nДобавить: /watch BLESSUSDT'
    lines = ['Твой watchlist:', '']
    for i, sym in enumerate(symbols, 1):
        lines.append(f'{i}. {_clean_symbol(sym)}')
    lines += ['', '/watch SYMBOL  — добавить', '/unwatch SYMBOL — убрать']
    return '\n'.join(lines)

def format_help() -> str:
    return 'OI Hunter — сигналы по MEXC фьючерсам\n\nКоманды:\n/analyze SYMBOL — анализ монеты\n/watch SYMBOL   — добавить в watchlist\n/unwatch SYMBOL — убрать из watchlist\n/watchlist      — показать watchlist\n/status         — статус монитора\n/help           — справка\n\nСигналы приходят автоматически при score >= 7.0'

def format_status(is_running: bool, tracked_count: int, signals_today: int) -> str:
    emoji = '🟢' if is_running else '🔴'
    status = 'работает' if is_running else 'остановлен'
    return f'{emoji} Монитор {status}\nОтслеживается: {tracked_count} токенов\nСигналов сегодня: {signals_today}'

def _clean_symbol(symbol: str) -> str:
    return symbol.replace('_USDT', 'USDT').replace('_', '')

def _fmt_price(price: float) -> str:
    if price <= 0:
        return '$0'
    if price >= 1000:
        return f'${price:,.2f}'
    if price >= 1:
        return f'${price:.4f}'
    if price >= 0.01:
        return f'${price:.6f}'
    return f'${price:.8f}'

def _extract_order_book_line(results: list[AnalyzerResult]) -> Optional[str]:
    for r in results:
        if r.analyzer_name == 'Order Book' and r.reasoning:
            return f'[OB] {r.reasoning}'
    return None

def _extract_nowcast_line(results: list[AnalyzerResult]) -> Optional[str]:
    for r in results:
        if 'Nowcast' in r.analyzer_name and r.reasoning:
            return f'[OI Nowcast] {r.reasoning}'
    return None

def _extract_vol_spike_ratio(results: list[AnalyzerResult]) -> Optional[float]:
    for r in results:
        if 'Volume' in r.analyzer_name and r.key_value is not None:
            return r.key_value
    return None

def _nowcast_is_full(results: list[AnalyzerResult]) -> bool:
    for r in results:
        if 'Nowcast' in r.analyzer_name:
            if r.key_label != 'Predicted OI 10m %':
                return False
            return r.key_value is not None and abs(r.key_value) > 2.0
    return False

def _extract_blocks(results: list[AnalyzerResult], direction: str) -> list[str]:
    blocks = []
    for r in results:
        if direction == 'LONG' and r.blocks_short:
            blocks.append(f'[CONFIRMS LONG] Shorts blocked by {r.analyzer_name}')
        elif direction == 'SHORT' and r.blocks_long:
            blocks.append(f'[CONFIRMS SHORT] Longs blocked by {r.analyzer_name}')
    return blocks
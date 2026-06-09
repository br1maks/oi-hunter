from typing import Optional
from src.models.signal import Signal
from src.models.market_data import MarketData
from src.models.analyzer_result import AnalyzerResult
from src.models.squeeze_alert import SqueezeAlert

def format_signal_alert(signal: Signal, market_data: MarketData, previous_direction: Optional[str] = None) -> str:
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
    if previous_direction and previous_direction != direction:
        lines = [f'🔄 Разворот: {previous_direction} → {direction}', ''] + lines
    lines.append(f'Price:   {_fmt_price(signal.current_price)}')
    if market_data.open_interest_usd:
        lines.append(f'OI:      ${market_data.open_interest_usd:,.0f}')
    if signal.oi_mc_ratio is not None:
        lines.append(f'OI/MC:   {signal.oi_mc_ratio:.4f}')
        if signal.oi_mc_ratio > 0.30:
            lines.append(f'⚠️ High leverage: OI/MC {signal.oi_mc_ratio:.2f}')
    elif signal.market_cap_usd is None:
        lines.append('OI/MC:   N/A (MC unknown)')
    if market_data.oi_change_1h is not None:
        lines.append(f'OI Δ1h:  {market_data.oi_change_1h:+.1f}%')
    if market_data.oi_change_5m is not None:
        lines.append(f'OI Δ5m:  {market_data.oi_change_5m:+.1f}%')
    if signal.funding_rate is not None:
        lines.append(f'FR:      {signal.funding_rate * 100:+.4f}%')
        if signal.funding_rate > 0.002:
            lines.append('⚠️ High FR: short-term trade only')
        elif signal.funding_rate < -0.002:
            lines.append('⚠️ High -FR: short positions decay fast')
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

def format_squeeze_alert(alert: SqueezeAlert) -> str:
    symbol = _clean_symbol(alert.symbol)
    is_long = alert.direction == 'LONG_SQUEEZE'
    is_strong = alert.alert_level == 'STRONG'

    is_triggered = alert.alert_level == 'TRIGGERED'
    base_emoji = '⚡' if is_long else '💥'
    if is_triggered:
        prefix = f'🚨{base_emoji}'
    elif is_strong:
        prefix = f'🔥{base_emoji}'
    else:
        prefix = base_emoji
    dir_label = 'LONG SQUEEZE' if is_long else 'SHORT SQUEEZE'
    header = f'{prefix} {dir_label} ({alert.alert_level}): {symbol}'

    lines = [header, f'Score: {alert.squeeze_score:.1f}/10', '━━━━━━━━━━━━━━━━━━━━━', '']
    lines.append(f'Price: {_fmt_price(alert.price)}   OI: ${_fmt_large(alert.oi_usd)}')
    if alert.oi_change_1h is not None:
        lines.append(f'OI Δ1h: {alert.oi_change_1h:+.1f}%')
    if alert.price_change_1h is not None:
        lines.append(f'Price Δ1h: {alert.price_change_1h:+.2f}%')
    if alert.price_change_4h is not None:
        lines.append(f'Price Δ4h: {alert.price_change_4h:+.2f}%')
    lines.append(f'FR: {alert.funding_rate * 100:+.4f}%')

    # Component breakdown
    lines += ['', 'Components:']
    c1_label = 'Trapped Shorts' if is_long else 'Trapped Longs'
    c2_label = 'Ask Vacuum' if is_long else 'Bid Vacuum'
    c3_label = 'Buy Aggression' if is_long else 'Sell Aggression'
    c4_label = 'Compression' if is_long else 'Over-Extension'
    for label, val in [(c1_label, alert.c1_score), (c2_label, alert.c2_score),
                       (c3_label, alert.c3_score), (c4_label, alert.c4_score)]:
        if val is not None:
            lines.append(f'  {label:<18} {val:.1f}')
    if alert.funding_adj != 0.0:
        lines.append(f'  FR Adj             {alert.funding_adj:+.2f}')

    # Aggression detail
    if alert.aggression_5m is not None:
        side = 'buy' if is_long else 'sell'
        agg_val = alert.aggression_5m if is_long else (100.0 - alert.aggression_5m)
        agg_line = f'  Aggression 5m:   {agg_val:.1f}% {side}'
        if alert.aggression_accel is not None and abs(alert.aggression_accel) >= 1.0:
            agg_line += f' ({alert.aggression_accel:+.1f}% vs 2h)'
        lines.append(agg_line)

    # Squeeze-specific context
    if alert.ob_ratio is not None:
        ob_label = 'bid/ask' if is_long else 'ask/bid'
        lines.append(f'  OB {ob_label}:       {alert.ob_ratio:.2f}x')
    if alert.vci is not None:
        vci_flag = ' 🔴' if alert.vci < 0.55 else (' 🟡' if alert.vci < 0.65 else '')
        lines.append(f'  VCI:               {alert.vci:.3f}{vci_flag}')
    if alert.cfc >= 2:
        lines.append(f'  Flat candles:      {alert.cfc}')

    lines += ['', alert.reasoning]
    return '\n'.join(lines)

def _fmt_large(value: float) -> str:
    if value >= 1_000_000:
        return f'{value / 1_000_000:.2f}M'
    if value >= 1_000:
        return f'{value / 1_000:.1f}K'
    return f'{value:.0f}'

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
        if market_data.oi_mc_ratio > 0.30:
            lines.append(f'⚠️ High leverage: OI/MC {market_data.oi_mc_ratio:.2f}')
    elif market_data.market_cap_usd is None:
        lines.append('OI/MC:   N/A (MC unknown)')
    if market_data.funding_rate is not None:
        lines.append(f'FR:      {market_data.funding_rate * 100:+.4f}%')
        if market_data.funding_rate > 0.002:
            lines.append('⚠️ High FR: short-term trade only')
        elif market_data.funding_rate < -0.002:
            lines.append('⚠️ High -FR: short positions decay fast')
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
    regime = analysis.get('regime')
    regime_reasoning = analysis.get('regime_reasoning', '')
    if regime:
        lines.append(f'Regime:  {regime} ({regime_reasoning})')
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
    return 'OI Hunter — сигналы по MEXC фьючерсам\n\nКоманды:\n/analyze SYMBOL — анализ монеты\n/watch SYMBOL   — добавить в watchlist\n/unwatch SYMBOL — убрать из watchlist\n/watchlist      — показать watchlist\n/stats          — статистика forward-test\n/status         — статус монитора\n/help           — справка\n\nСигналы приходят автоматически при score >= 7.0'

def format_stats(stats: dict) -> str:
    if 'error' in stats:
        return f'Ошибка статистики: {stats["error"]}'
    total = stats.get('total', 0)
    open_count = stats.get('open', 0)
    if total == 0:
        return (
            'Forward Test\n\n'
            f'Закрытых сигналов: 0\n'
            f'Открытых: {open_count}\n\n'
            'Статистика появится после первых закрытых сделок.'
        )
    win_rate = stats.get('win_rate', 0.0)
    wins = stats.get('wins', 0)
    losses = stats.get('losses', 0)
    avg_pnl = stats.get('avg_pnl', 0.0)
    best = stats.get('best', 0.0)
    worst = stats.get('worst', 0.0)
    rate_emoji = '🟢' if win_rate >= 60 else ('🟡' if win_rate >= 40 else '🔴')
    lines = [
        '📊 Forward Test',
        '━━━━━━━━━━━━━━━━━━━━━',
        f'Закрыто: {total}   Открыто: {open_count}',
        '',
        f'{rate_emoji} Win Rate: {win_rate:.1f}%  ({wins}W / {losses}L)',
        f'Avg PnL:  {avg_pnl:+.2f}%',
        f'Лучшая:   {best:+.2f}%',
        f'Худшая:   {worst:+.2f}%',
        '',
        'По направлению:',
        f'  LONG:  {stats.get("long_wins", 0)}/{stats.get("long_total", 0)}'
        f' ({stats.get("long_win_rate", 0.0):.1f}%)',
        f'  SHORT: {stats.get("short_wins", 0)}/{stats.get("short_total", 0)}'
        f' ({stats.get("short_win_rate", 0.0):.1f}%)',
    ]
    t1 = stats.get('t1_wins', 0)
    t2 = stats.get('t2_wins', 0)
    t3 = stats.get('t3_wins', 0)
    if wins > 0:
        lines += ['', f'Тейки: T1={t1}  T2={t2}  T3={t3}']
    return '\n'.join(lines)


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
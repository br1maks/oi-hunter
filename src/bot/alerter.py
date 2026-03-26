import logging
import time
from src.models.signal import Signal
from src.models.market_data import MarketData
from src.bot.formatters import format_signal_alert
logger = logging.getLogger(__name__)

class Alerter:
    COOLDOWN_SECONDS = 5 * 60

    def __init__(self, bot):
        self._bot = bot
        self._last_alert: dict[str, float] = {}

    def is_on_cooldown(self, symbol: str) -> bool:
        last = self._last_alert.get(symbol, 0)
        return time.time() - last < self.COOLDOWN_SECONDS

    async def send_signal_alert(self, signal: Signal, market_data: MarketData):
        symbol = signal.symbol
        if self.is_on_cooldown(symbol):
            last = self._last_alert.get(symbol, 0)
            remaining = int(self.COOLDOWN_SECONDS - (time.time() - last))
            logger.debug(f'[Alerter] {symbol} cooldown {remaining}s')
            return
        try:
            text = format_signal_alert(signal, market_data)
            await self._bot.send_signal(text)
            self._last_alert[symbol] = time.time()
            logger.info(f'[Alerter] Sent: {symbol} {signal.direction} {signal.overall_score:.1f}/10')
        except Exception as e:
            logger.error(f'[Alerter] Failed to send alert for {symbol}: {e}')

    def update_monitor_status(self, tracked_count: int):
        self._bot.set_monitor_status(running=True, tracked_count=tracked_count)

    async def send_message(self, text: str):
        try:
            await self._bot.send_message(text)
        except Exception as e:
            logger.error(f'[Alerter] Failed to send message: {e}')
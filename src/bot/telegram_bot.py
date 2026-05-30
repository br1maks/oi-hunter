import os
import logging
from datetime import datetime, timezone
from typing import Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from src.bot.formatters import format_analysis_result, format_watchlist, format_help, format_status, format_stats
logger = logging.getLogger(__name__)

class OIHunterBot:

    def __init__(self, token: str, chat_id: Optional[int]=None, db=None):
        self.token = token
        self.chat_id = chat_id
        self._db = db
        self._app: Optional[Application] = None
        self._watchlist: list[str] = []
        self._monitor_running = False
        self._signals_today = 0
        self._tracked_count = 0
        self._mc_cache = None

    def _load_watchlist(self) -> None:
        if self._db is None or self.chat_id is None:
            return
        try:
            from src.database.models import UserWatchlist
            with self._db.session() as s:
                rows = s.query(UserWatchlist).filter_by(chat_id=self.chat_id).all()
                self._watchlist = [r.symbol for r in rows]
            logger.info(f'Loaded {len(self._watchlist)} watchlist symbols from DB')
        except Exception as e:
            logger.warning(f'Failed to load watchlist from DB: {e}')

    def _save_watchlist_add(self, symbol: str) -> None:
        if self._db is None or self.chat_id is None:
            return
        try:
            from src.database.models import UserWatchlist
            with self._db.session() as s:
                entry = UserWatchlist(chat_id=self.chat_id, symbol=symbol, added_at=datetime.now(timezone.utc))
                s.add(entry)
        except Exception as e:
            logger.warning(f'Failed to persist watchlist add for {symbol}: {e}')

    def _save_watchlist_remove(self, symbol: str) -> None:
        if self._db is None or self.chat_id is None:
            return
        try:
            from src.database.models import UserWatchlist
            with self._db.session() as s:
                s.query(UserWatchlist).filter_by(chat_id=self.chat_id, symbol=symbol).delete()
        except Exception as e:
            logger.warning(f'Failed to persist watchlist remove for {symbol}: {e}')

    async def start(self):
        self._app = Application.builder().token(self.token).build()
        self._register_handlers()
        if self._db is not None and self.chat_id is not None:
            self._load_watchlist()
        logger.info('Starting Telegram bot...')
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info('Telegram bot is running. Send /start to your bot.')

    async def stop(self):
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info('Telegram bot stopped.')

    async def send_signal(self, message: str):
        if not self.chat_id:
            logger.warning('chat_id not set — signal not sent. Use /start to register.')
            return
        if not self._app:
            logger.warning('Bot not started — signal not sent.')
            return
        try:
            await self._app.bot.send_message(chat_id=self.chat_id, text=message)
            self._signals_today += 1
            logger.info(f'Signal sent to chat {self.chat_id}')
        except Exception as e:
            logger.error(f'Failed to send signal: {e}')

    async def send_message(self, text: str):
        await self.send_signal(text)

    def set_monitor_status(self, running: bool, tracked_count: int=0):
        self._monitor_running = running
        self._tracked_count = tracked_count

    def set_market_cap_cache(self, mc_cache) -> None:
        self._mc_cache = mc_cache

    def get_watchlist(self) -> list[str]:
        return list(self._watchlist)

    def _register_handlers(self):
        app = self._app
        app.add_handler(CommandHandler('start', self._cmd_start))
        app.add_handler(CommandHandler('help', self._cmd_help))
        app.add_handler(CommandHandler('analyze', self._cmd_analyze))
        app.add_handler(CommandHandler('watch', self._cmd_watch))
        app.add_handler(CommandHandler('unwatch', self._cmd_unwatch))
        app.add_handler(CommandHandler('watchlist', self._cmd_watchlist))
        app.add_handler(CommandHandler('status', self._cmd_status))
        app.add_handler(CommandHandler('stats', self._cmd_stats))
        app.add_error_handler(self._on_error)

    async def _on_error(self, update: object, ctx: ContextTypes.DEFAULT_TYPE):
        from telegram.error import TimedOut, NetworkError
        err = ctx.error
        if isinstance(err, (TimedOut, NetworkError)):
            logger.warning(f'Telegram network error (ignored): {err}')
        else:
            logger.error(f'Unhandled bot error: {err}', exc_info=err)

    async def _cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_chat.id
        if not self.chat_id:
            self.chat_id = user_id
            logger.info(f'Registered chat_id: {user_id}')
            self._load_watchlist()
        await update.message.reply_text(f'OI Hunter запущен!\n\nТвой chat ID: {user_id}\nДобавь в .env: TELEGRAM_CHAT_ID={user_id}\n\n{format_help()}')

    async def _cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(format_help())

    async def _cmd_analyze(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        args = ctx.args
        if not args:
            await update.message.reply_text('Укажи символ. Пример: /analyze BLESSUSDT')
            return
        symbol = args[0].upper().strip()
        if not symbol.endswith('USDT'):
            symbol = symbol + 'USDT'
        try:
            await update.message.reply_text(f'Анализирую {symbol}...')
            from src.data.data_aggregator import DataAggregator
            from src.core.signal_generator import SignalGenerator
            async with DataAggregator(mc_cache=self._mc_cache) as aggregator:
                market_data = await aggregator.aggregate(symbol)
            generator = SignalGenerator()
            if self._db is not None:
                generator.set_database(self._db)
            analysis = generator.analyze_only(market_data)
            msg = format_analysis_result(symbol, analysis, market_data)
            await update.message.reply_text(msg)
        except Exception as e:
            logger.error(f'Analysis failed for {symbol}: {e}')
            try:
                await update.message.reply_text(f'Ошибка при анализе {symbol}: {str(e)[:200]}')
            except Exception:
                pass

    async def _cmd_watch(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        args = ctx.args
        if not args:
            await update.message.reply_text('Укажи символ. Пример: /watch BLESSUSDT')
            return
        symbol = args[0].upper().strip()
        if not symbol.endswith('USDT'):
            symbol = symbol + 'USDT'
        if symbol in self._watchlist:
            await update.message.reply_text(f'{symbol} уже в watchlist.')
            return
        self._watchlist.append(symbol)
        self._save_watchlist_add(symbol)
        await update.message.reply_text(f'{symbol} добавлен в watchlist.\nБуду присылать все сигналы по этой монете.')

    async def _cmd_unwatch(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        args = ctx.args
        if not args:
            await update.message.reply_text('Укажи символ. Пример: /unwatch BLESSUSDT')
            return
        symbol = args[0].upper().strip()
        if not symbol.endswith('USDT'):
            symbol = symbol + 'USDT'
        if symbol not in self._watchlist:
            await update.message.reply_text(f'{symbol} нет в watchlist.')
            return
        self._watchlist.remove(symbol)
        self._save_watchlist_remove(symbol)
        await update.message.reply_text(f'{symbol} убран из watchlist.')

    async def _cmd_watchlist(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        msg = format_watchlist(self._watchlist)
        await update.message.reply_text(msg)

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        msg = format_status(is_running=self._monitor_running, tracked_count=self._tracked_count, signals_today=self._signals_today)
        await update.message.reply_text(msg)

    async def _cmd_stats(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if self._db is None:
            await update.message.reply_text('База данных не подключена.')
            return
        try:
            from src.core.forward_tester import ForwardTester
            stats = ForwardTester(self._db).get_stats()
            await update.message.reply_text(format_stats(stats))
        except Exception as e:
            logger.error(f'Stats command failed: {e}')
            await update.message.reply_text(f'Ошибка: {str(e)[:200]}')

def create_bot_from_env(db=None) -> OIHunterBot:
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    if not token:
        raise ValueError('TELEGRAM_BOT_TOKEN не задан в .env')
    chat_id_str = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
    chat_id = int(chat_id_str) if chat_id_str else None
    return OIHunterBot(token=token, chat_id=chat_id, db=db)
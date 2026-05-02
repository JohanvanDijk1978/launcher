"""
Telegram bot — control panel and notification system.
Commands: /start, /stop, /status, /launches, /score, /config
"""

import asyncio
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from config import Config
from utils.dedup import DedupStore

logger = logging.getLogger("bot.telegram")


class TelegramBot:
    def __init__(self, config: Config, launcher, dedup: DedupStore):
        self.config = config
        self.launcher = launcher
        self.dedup = dedup
        self.running = True
        self.app = None

    async def start(self):
        """Start the Telegram bot."""
        if not self.config.telegram_bot_token:
            logger.warning("No Telegram bot token configured — skipping bot")
            return

        self.app = Application.builder().token(self.config.telegram_bot_token).build()

        # Register commands
        self.app.add_handler(CommandHandler("start", self._cmd_start))
        self.app.add_handler(CommandHandler("stop", self._cmd_stop))
        self.app.add_handler(CommandHandler("resume", self._cmd_resume))
        self.app.add_handler(CommandHandler("status", self._cmd_status))
        self.app.add_handler(CommandHandler("launches", self._cmd_launches))
        self.app.add_handler(CommandHandler("help", self._cmd_help))

        logger.info("Telegram bot started")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)
        # Keep running until cancelled
        try:
            await asyncio.Event().wait()
        finally:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()

    async def notify(self, message: str):
        """Send a notification to the configured chat."""
        if not self.app or not self.config.telegram_chat_id:
            logger.info(f"[TG NOTIFY] {message}")
            return

        try:
            await self.app.bot.send_message(
                chat_id=self.config.telegram_chat_id,
                text=message,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"Telegram notify failed: {e}")

    # --- Command handlers ---

    async def _cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        self.running = True
        await update.message.reply_text(
            "✅ *Viral Launcher is ACTIVE*\n\nMonitoring Twitter + Reddit for trends.",
            parse_mode="Markdown",
        )

    async def _cmd_stop(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        self.running = False
        await update.message.reply_text(
            "⏸ *Launcher PAUSED*\n\nNo new coins will be launched until you /resume.",
            parse_mode="Markdown",
        )

    async def _cmd_resume(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        self.running = True
        await update.message.reply_text("▶️ *Launcher RESUMED*", parse_mode="Markdown")

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        total = len(self.dedup.get_all())
        status = "🟢 ACTIVE" if self.running else "🔴 PAUSED"
        await update.message.reply_text(
            f"*Status:* {status}\n"
            f"*Total launched:* {total} coins\n"
            f"*Poll interval:* {self.config.poll_interval_seconds}s\n"
            f"*Min virality score:* {self.config.min_virality_score}",
            parse_mode="Markdown",
        )

    async def _cmd_launches(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        launches = self.dedup.get_all()
        if not launches:
            await update.message.reply_text("No coins launched yet.")
            return

        recent = list(launches.items())[-10:]  # Last 10
        lines = [f"• `{key}` — {info.get('name', '?')} (${info.get('ticker', '?')})"
                 for key, info in reversed(recent)]
        await update.message.reply_text(
            f"*Last {len(recent)} launches:*\n" + "\n".join(lines),
            parse_mode="Markdown",
        )

    async def _cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "*Viral Launcher Commands:*\n\n"
            "/status — Show bot status + stats\n"
            "/stop — Pause launching\n"
            "/resume — Resume launching\n"
            "/launches — Show recent coin launches\n"
            "/help — Show this message",
            parse_mode="Markdown",
        )

    def _is_authorized(self, update: Update) -> bool:
        """Only respond to the configured chat ID."""
        if not self.config.telegram_chat_id:
            return True  # No restriction if not configured
        return str(update.effective_chat.id) == str(self.config.telegram_chat_id)

    @property
    def is_running(self) -> bool:
        return self.running

import logging
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)

try:
    from telegram import Bot
except ImportError:  # pragma: no cover
    Bot = None


class TelegramService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.bot: Any | None = Bot(settings.telegram_bot_token) if Bot and settings.telegram_bot_token else None

    async def start(self) -> None:
        if not self.bot:
            logger.warning("Telegram bot token is empty. Telegram notifications are disabled.")

    async def stop(self) -> None:
        return None

    async def send_admin_message(self, text: str) -> None:
        if not self.bot or not self.settings.telegram_chat_id:
            logger.info("Telegram message: %s", text)
            return
        await self.bot.send_message(chat_id=self.settings.telegram_chat_id, text=text)

    async def notify_entry(self, symbol: str, side: str, qty: float, leverage: int, order_id: str | None = None) -> None:
        await self.send_admin_message(
            f"Entry submitted\n"
            f"{symbol} {side} {leverage}x\n"
            f"Quantity: {qty}\n"
            f"Order ID: {order_id or '-'}"
        )

    async def notify_exit(self, symbol: str, reason: str | None = None) -> None:
        await self.send_admin_message(f"Exit submitted\n{symbol}\nReason: {reason or '-'}")

    async def notify_error(self, source: str, message: str) -> None:
        await self.send_admin_message(f"Error\nSource: {source}\n{message}")

    async def notify_daily_summary(self, summary: dict[str, Any]) -> None:
        await self.send_admin_message(
            f"Daily summary\n"
            f"Open positions: {summary.get('open_positions')}\n"
            f"Today orders: {summary.get('today_orders')}\n"
            f"Today PnL: {summary.get('today_pnl')}"
        )

import asyncio

from app.config import Settings
from app.services.telegram import TelegramService


def test_telegram_without_token_logs_message():
    settings = Settings(TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID=0)
    service = TelegramService(settings)
    asyncio.run(service.notify_error("test", "message"))
    assert service.bot is None

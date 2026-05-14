from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.routes.webhook import router as webhook_router
from app.services.database import Database
from app.services.exchange import ExchangeService
from app.services.risk import RiskService
from app.services.telegram import TelegramService
from app.utils.logger import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_file)
    db = Database(settings)
    db.init()
    exchange = ExchangeService(settings)
    risk = RiskService(settings, db)
    telegram = TelegramService(settings, db, exchange, risk)

    app.state.settings = settings
    app.state.db = db
    app.state.exchange = exchange
    app.state.risk = risk
    app.state.telegram = telegram

    await telegram.start()
    try:
        yield
    finally:
        await telegram.stop()


app = FastAPI(title="XRPUSDT Semi Auto Trading Bot", lifespan=lifespan)
app.include_router(webhook_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

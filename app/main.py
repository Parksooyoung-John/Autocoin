from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.routes.webhook import router as webhook_router
from app.services.database import Database
from app.services.exchange import ExchangeService
from app.services.orders import OrderService
from app.services.positions import PositionService
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
    orders = OrderService(settings, db, exchange, risk)
    positions = PositionService(settings, db, exchange)
    telegram = TelegramService(settings)

    app.state.settings = settings
    app.state.db = db
    app.state.exchange = exchange
    app.state.risk = risk
    app.state.orders = orders
    app.state.positions = positions
    app.state.telegram = telegram

    await telegram.start()
    try:
        yield
    finally:
        await telegram.stop()


app = FastAPI(title="BTC/XRP Binance Futures 5x Auto Trading Bot", lifespan=lifespan)
app.include_router(webhook_router)


@app.get("/health")
async def health() -> dict:
    settings = get_settings()
    db = Database(settings)
    db.init()
    return {
        "status": "ok",
        "app": settings.app_name,
        "testnet": settings.binance_testnet,
        "paused": db.is_paused(),
        "supported_symbols": settings.supported_symbols,
    }

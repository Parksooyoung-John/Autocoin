from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.routes.webhook import router
from app.services.database import Database


class FakeTelegram:
    def __init__(self):
        self.sent = []

    async def send_signal_alert(self, signal):
        self.sent.append(signal)


def make_client(tmp_path):
    settings = Settings(
        TRADINGVIEW_SECRET="SECRET",
        ADMIN_CHAT_ID=123,
        DATABASE_URL=f"sqlite:///{tmp_path / 'bot.db'}",
        TELEGRAM_BOT_TOKEN="",
        BYBIT_API_KEY="",
        BYBIT_API_SECRET="",
    )
    db = Database(settings)
    db.init()
    telegram = FakeTelegram()
    app = FastAPI()
    app.state.settings = settings
    app.state.db = db
    app.state.telegram = telegram
    app.include_router(router)
    return TestClient(app), db, telegram


def payload(**overrides):
    data = {
        "secret": "SECRET",
        "signal_id": "XRPUSDT-1",
        "symbol": "XRPUSDT",
        "side": "long",
        "order_type": "limit",
        "entry": 2.5,
        "stop_loss": 2.47,
        "take_profit": 2.59,
        "leverage": 3,
        "risk_percent": 1.0,
        "timeframe": "15m",
        "strategy": "EMA20_EMA60_BREAKOUT",
    }
    data.update(overrides)
    return data


def test_webhook_rejects_secret_mismatch(tmp_path):
    client, _, _ = make_client(tmp_path)
    response = client.post("/webhook", json=payload(secret="BAD"))
    assert response.status_code == 403


def test_webhook_rejects_invalid_payload(tmp_path):
    client, _, _ = make_client(tmp_path)
    response = client.post("/webhook", json={"secret": "SECRET"})
    assert response.status_code == 400


def test_webhook_stores_signal_and_sends_telegram(tmp_path):
    client, db, telegram = make_client(tmp_path)
    response = client.post("/webhook", json=payload())
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert db.get_signal("XRPUSDT-1") is not None
    assert len(telegram.sent) == 1


def test_webhook_rejects_duplicate_signal_id(tmp_path):
    client, _, _ = make_client(tmp_path)
    assert client.post("/webhook", json=payload()).status_code == 200
    response = client.post("/webhook", json=payload())
    assert response.status_code == 409


def test_webhook_rejects_missing_stop_loss(tmp_path):
    client, _, _ = make_client(tmp_path)
    response = client.post("/webhook", json=payload(stop_loss=None))
    assert response.status_code == 400

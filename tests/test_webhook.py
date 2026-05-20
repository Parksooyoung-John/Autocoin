from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.routes.webhook import router
from app.services.database import Database
from app.services.orders import OrderService
from app.services.positions import PositionService
from app.services.risk import RiskService


class FakeExchange:
    markets = {"BTC/USDT:USDT": {}, "ETH/USDT:USDT": {}, "XRP/USDT:USDT": {}}

    def __init__(self):
        self.orders = []

    def get_usdt_balance(self):
        return 1000

    def get_positions(self, symbols=None):
        return []

    def normalize_quantity(self, symbol, qty):
        return round(qty, 6)

    def normalize_price(self, symbol, price):
        return round(price, 2)

    def set_leverage(self, symbol, leverage):
        self.leverage = (symbol, leverage)

    def place_entry_order(self, plan):
        self.orders.append(("entry", plan.symbol, plan.quantity))
        return {"id": "ENTRY-1", "status": "closed", "filled": plan.quantity}

    def place_stop_market(self, symbol, side, qty, stop_price):
        self.orders.append(("stop", symbol, qty, stop_price))
        return {"id": "SL-1", "status": "open"}

    def place_take_profit_market(self, symbol, side, qty, stop_price):
        self.orders.append(("tp", symbol, qty, stop_price))
        return {"id": f"TP-{len(self.orders)}", "status": "open"}

    def place_reduce_only_market(self, symbol, side, qty):
        self.orders.append(("exit", symbol, qty))
        return {"id": "EXIT-1", "status": "closed"}

    def fetch_order(self, order_id, symbol):
        return {"id": order_id, "status": "open", "filled": 0}

    def cancel_order(self, order_id, symbol):
        self.orders.append(("cancel", symbol, order_id))
        return {"id": order_id, "status": "canceled"}

    def cancel_open_algo_orders(self, symbol):
        self.orders.append(("cancel_algo", symbol))
        return {"status": "ok"}


class FakeTelegram:
    def __init__(self):
        self.messages = []

    async def notify_entry(self, symbol, side, qty, leverage, order_id=None):
        self.messages.append(("entry", symbol, side, qty, leverage))

    async def notify_exit(self, symbol, reason=None):
        self.messages.append(("exit", symbol, reason))

    async def notify_error(self, source, message):
        self.messages.append(("error", source, message))


def make_client(tmp_path):
    settings = Settings(
        WEBHOOK_SECRET="SECRET",
        TELEGRAM_CHAT_ID=123,
        DATABASE_URL=f"sqlite:///{tmp_path / 'bot.db'}",
        BINANCE_API_KEY="",
        BINANCE_API_SECRET="",
        ORDER_TIMEOUT_SECONDS=0,
    )
    db = Database(settings)
    db.init()
    exchange = FakeExchange()
    risk = RiskService(settings, db)
    orders = OrderService(settings, db, exchange, risk)
    telegram = FakeTelegram()
    app = FastAPI()
    app.state.settings = settings
    app.state.db = db
    app.state.exchange = exchange
    app.state.risk = risk
    app.state.orders = orders
    app.state.positions = PositionService(settings, db, exchange)
    app.state.telegram = telegram
    app.include_router(router)
    return TestClient(app), db, exchange, telegram


def entry_payload(**overrides):
    data = {
        "secret": "SECRET",
        "signal_id": "BTCUSDT-1",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "signal": "ENTRY",
        "timeframe": "1h",
        "price": 65000,
        "atr": 800,
        "strategy": "ema_atr_swing",
        "timestamp": "2026-05-20T00:00:00Z",
    }
    data.update(overrides)
    return data


def test_webhook_rejects_secret_mismatch(tmp_path):
    client, _, _, _ = make_client(tmp_path)
    response = client.post("/webhook", json=entry_payload(secret="BAD"))
    assert response.status_code == 401


def test_webhook_rejects_invalid_payload(tmp_path):
    client, _, _, _ = make_client(tmp_path)
    response = client.post("/webhook", json={"secret": "SECRET"})
    assert response.status_code == 400


def test_webhook_orders_entry_and_notifies(tmp_path):
    client, db, exchange, telegram = make_client(tmp_path)
    response = client.post("/webhook", json=entry_payload())
    assert response.status_code == 200
    assert response.json()["status"] == "ordered"
    assert db.get_signal("BTCUSDT-1").status.value == "ordered"
    assert db.open_position_for_symbol("BTCUSDT") is not None
    assert len(exchange.orders) == 4
    assert telegram.messages[0][0] == "entry"


def test_unfilled_limit_entry_does_not_create_position_or_protective_orders(tmp_path):
    client, db, exchange, _ = make_client(tmp_path)

    def open_entry(plan):
        exchange.orders.append(("entry", plan.symbol, plan.quantity))
        return {"id": "ENTRY-OPEN", "status": "open", "filled": 0}

    exchange.place_entry_order = open_entry
    response = client.post("/webhook", json=entry_payload(signal_id="BTCUSDT-open"))
    assert response.status_code == 200
    assert response.json()["status"] == "ordered"
    assert db.open_position_for_symbol("BTCUSDT") is None
    assert exchange.orders == [("entry", "BTCUSDT", 0.0125), ("cancel", "BTCUSDT", "ENTRY-OPEN")]
    assert db.get_signal("BTCUSDT-open").status.value == "cancelled"


def test_webhook_rejects_unsupported_symbol(tmp_path):
    client, _, _, _ = make_client(tmp_path)
    response = client.post("/webhook", json=entry_payload(symbol="SOLUSDT"))
    assert response.status_code == 400


def test_webhook_rejects_duplicate_signal_id(tmp_path):
    client, _, _, _ = make_client(tmp_path)
    assert client.post("/webhook", json=entry_payload()).status_code == 200
    response = client.post("/webhook", json=entry_payload())
    assert response.status_code == 409


def test_exit_signal_closes_tracked_position(tmp_path):
    client, db, exchange, telegram = make_client(tmp_path)
    assert client.post("/webhook", json=entry_payload()).status_code == 200
    response = client.post(
        "/webhook",
        json={
            "secret": "SECRET",
            "signal_id": "BTCUSDT-exit",
            "symbol": "BTCUSDT",
            "side": "LONG",
            "signal": "EXIT",
            "reason": "take_profit_1",
            "price": 66300,
            "timestamp": "2026-05-20T01:00:00Z",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "closed"
    assert db.open_position_for_symbol("BTCUSDT") is None
    assert telegram.messages[-1][0] == "exit"
    assert ("cancel_algo", "BTCUSDT") in exchange.orders

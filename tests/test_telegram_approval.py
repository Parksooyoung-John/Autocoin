import asyncio

from app.config import Settings
from app.models import SignalStatus, TradingViewSignal
from app.services.database import Database
from app.services.risk import RiskService
from app.services.telegram import TelegramService


class FakeExchange:
    def __init__(self):
        self.orders = []
        self.position_exists = False
        self.sl_tp_called = False

    def has_open_position(self, symbol):
        return self.position_exists

    def get_usdt_balance(self):
        return 1000.0

    def set_leverage(self, symbol, leverage):
        self.leverage = leverage

    def place_entry_order(self, signal, qty):
        self.orders.append((signal, qty))
        return {"retCode": 0, "result": {"orderId": "OID-1"}}

    def get_position(self, symbol):
        return {"symbol": symbol, "size": "1"} if self.orders else None

    def set_stop_loss_take_profit(self, signal):
        self.sl_tp_called = True
        return {"retCode": 0}


def build_service(tmp_path):
    settings = Settings(
        TRADINGVIEW_SECRET="SECRET",
        ADMIN_CHAT_ID=123,
        DATABASE_URL=f"sqlite:///{tmp_path / 'bot.db'}",
    )
    db = Database(settings)
    db.init()
    exchange = FakeExchange()
    risk = RiskService(settings, db)
    service = TelegramService(settings, db, exchange, risk)
    return db, exchange, service


def store_signal(db):
    payload = {
        "secret": "SECRET",
        "signal_id": "sig-approve",
        "symbol": "XRPUSDT",
        "side": "long",
        "order_type": "limit",
        "entry": 2.5,
        "stop_loss": 2.47,
        "take_profit": 2.59,
        "leverage": 3,
        "risk_percent": 1.0,
    }
    signal = TradingViewSignal.model_validate(payload)
    db.create_signal(signal, payload)


def test_reject_does_not_place_order(tmp_path):
    db, exchange, service = build_service(tmp_path)
    store_signal(db)
    result = asyncio.run(service.handle_signal_action("sig-approve", "reject", "123"))
    assert "거절 완료" in result
    assert exchange.orders == []
    assert db.get_signal("sig-approve").status == SignalStatus.rejected


def test_approve_places_order_and_sets_sl_tp(tmp_path):
    db, exchange, service = build_service(tmp_path)
    store_signal(db)
    result = asyncio.run(service.handle_signal_action("sig-approve", "approve", "123"))
    assert "주문 성공" in result
    assert len(exchange.orders) == 1
    assert exchange.sl_tp_called is True
    assert db.get_signal("sig-approve").status == SignalStatus.ordered


def test_approve_blocks_existing_position(tmp_path):
    db, exchange, service = build_service(tmp_path)
    store_signal(db)
    exchange.position_exists = True
    result = asyncio.run(service.handle_signal_action("sig-approve", "approve", "123"))
    assert "기존 포지션" in result
    assert exchange.orders == []
    assert db.get_signal("sig-approve").status == SignalStatus.failed

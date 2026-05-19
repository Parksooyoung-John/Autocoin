import pytest

from app.config import Settings
from app.models import OrderType, PlannedOrder, SignalSide
from app.services.exchange import ExchangeError, ExchangeService


class FlakySession:
    def __init__(self):
        self.calls = 0

    def fetch_balance(self, params=None):
        self.calls += 1
        if self.calls < 3:
            raise RuntimeError("temporary")
        return {"USDT": {"free": "100"}}


class FailingSession:
    def __init__(self):
        self.calls = 0

    def fetch_balance(self, params=None):
        self.calls += 1
        raise RuntimeError("temporary")


class OrderSession:
    markets = {"BTC/USDT:USDT": {}}

    def __init__(self):
        self.created = []

    def amount_to_precision(self, symbol, qty):
        return "0.125"

    def price_to_precision(self, symbol, price):
        return "65000.12"

    def create_order(self, symbol, order_type, side, qty, price=None, params=None):
        self.created.append((symbol, order_type, side, qty, price, params or {}))
        return {"id": "OID-1", "status": "open"}


def test_exchange_retries_until_success():
    settings = Settings(API_RETRY_COUNT=3)
    session = FlakySession()
    exchange = ExchangeService(settings, session=session)
    assert exchange.get_usdt_balance() == 100
    assert session.calls == 3


def test_exchange_retries_three_times_then_fails():
    settings = Settings(API_RETRY_COUNT=3)
    session = FailingSession()
    exchange = ExchangeService(settings, session=session)
    with pytest.raises(ExchangeError):
        exchange.get_usdt_balance()
    assert session.calls == 3


def test_exchange_places_limit_entry_order():
    exchange = ExchangeService(Settings(), session=OrderSession())
    plan = PlannedOrder(
        signal_id="sig",
        symbol="BTCUSDT",
        side=SignalSide.long,
        order_type=OrderType.limit,
        entry_price=65000.123,
        stop_loss=63800,
        quantity=0.2,
        leverage=5,
        risk_percent=1.5,
        atr=800,
    )
    response = exchange.place_entry_order(plan)
    assert response["id"] == "OID-1"
    assert exchange.session.created[0] == (
        "BTC/USDT:USDT",
        "limit",
        "buy",
        0.125,
        65000.12,
        {"timeInForce": "GTC"},
    )


def test_exchange_places_reduce_only_market_exit():
    exchange = ExchangeService(Settings(), session=OrderSession())
    exchange.place_reduce_only_market("BTCUSDT", SignalSide.long, 0.2)
    assert exchange.session.created[0][-1] == {"reduceOnly": True}

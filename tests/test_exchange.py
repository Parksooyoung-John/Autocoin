import pytest

from app.config import Settings
from app.services.exchange import ExchangeError, ExchangeService


class FlakySession:
    def __init__(self):
        self.calls = 0

    def get_wallet_balance(self, **kwargs):
        self.calls += 1
        if self.calls < 3:
            return {"retCode": 10001, "retMsg": "temporary"}
        return {"retCode": 0, "result": {"list": [{"coin": [{"coin": "USDT", "walletBalance": "100"}]}]}}


class FailingSession:
    def __init__(self):
        self.calls = 0

    def get_wallet_balance(self, **kwargs):
        self.calls += 1
        return {"retCode": 10001, "retMsg": "temporary"}


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

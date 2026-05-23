import pytest

from app.config import Settings
from app.models import SignalSide, TradingViewSignal
from app.services.database import Database
from app.services.risk import RiskError, RiskService


def build_risk(tmp_path, **settings_overrides):
    settings = Settings(
        WEBHOOK_SECRET="SECRET",
        TELEGRAM_CHAT_ID=123,
        DATABASE_URL=f"sqlite:///{tmp_path / 'bot.db'}",
        **settings_overrides,
    )
    db = Database(settings)
    db.init()
    risk = RiskService(settings, db)
    return settings, db, risk


def entry(**overrides):
    data = {
        "secret": "SECRET",
        "signal_id": "sig-1",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "signal": "ENTRY",
        "price": 65000,
        "atr": 800,
        "timestamp": "2026-05-20T00:00:00Z",
    }
    data.update(overrides)
    return TradingViewSignal.model_validate(data)


def test_risk_calculates_quantity_from_balance_weight_and_atr(tmp_path):
    _, _, risk = build_risk(tmp_path)
    plan = risk.validate_entry(entry(), account_balance=10000)
    assert plan.leverage == 5
    assert plan.stop_loss == 63000
    assert plan.quantity == 0.075


def test_xrp_weight_limits_quantity(tmp_path):
    _, _, risk = build_risk(tmp_path)
    plan = risk.validate_entry(entry(symbol="XRPUSDT", price=0.5, atr=0.01), account_balance=1000)
    assert plan.quantity == 600


def test_blocks_daily_loss_limit(tmp_path):
    _, db, risk = build_risk(tmp_path)
    db.create_order(
        signal_id="loss",
        symbol="BTCUSDT",
        side="LONG",
        action="EXIT",
        quantity=1,
        leverage=5,
        status="closed",
        pnl=-600,
    )
    with pytest.raises(RiskError):
        risk.validate_entry(entry(), account_balance=10000)


def test_blocks_duplicate_symbol_position(tmp_path):
    _, db, risk = build_risk(tmp_path)
    db.upsert_position(
        symbol="BTCUSDT",
        side=SignalSide.long,
        entry_price=65000,
        quantity=0.1,
        leverage=5,
        stop_loss=63800,
        take_profit_1=66040,
        take_profit_2=66950,
        trailing_stop=63800,
        signal_id="existing",
    )
    with pytest.raises(RiskError):
        risk.validate_entry(entry(), account_balance=10000)


def test_blocks_third_open_position(tmp_path):
    _, db, risk = build_risk(
        tmp_path,
        SUPPORTED_SYMBOLS=["BTCUSDT", "ETHUSDT", "XRPUSDT"],
        SYMBOL_WEIGHTS={"BTCUSDT": 0.4, "ETHUSDT": 0.0, "XRPUSDT": 0.6},
    )
    for symbol in ("BTCUSDT", "ETHUSDT"):
        db.upsert_position(
            symbol=symbol,
            side=SignalSide.long,
            entry_price=100,
            quantity=1,
            leverage=5,
            stop_loss=90,
            take_profit_1=102,
            take_profit_2=103,
            trailing_stop=90,
            signal_id=symbol,
        )
    with pytest.raises(RiskError):
        risk.validate_entry(entry(symbol="XRPUSDT", price=0.5, atr=0.01), account_balance=10000)


def test_blocks_market_entry_when_disabled(tmp_path):
    _, _, risk = build_risk(tmp_path)
    with pytest.raises(RiskError):
        risk.validate_entry(entry(order_type="market"), account_balance=10000)

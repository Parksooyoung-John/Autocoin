import pytest

from app.config import Settings
from app.models import TradingViewSignal
from app.services.database import Database
from app.services.risk import RiskError, RiskService


def build_risk(tmp_path):
    settings = Settings(
        TRADINGVIEW_SECRET="SECRET",
        ADMIN_CHAT_ID=123,
        DATABASE_URL=f"sqlite:///{tmp_path / 'bot.db'}",
    )
    db = Database(settings)
    db.init()
    risk = RiskService(settings, db)
    return settings, db, risk


def store_signal(db, **overrides):
    data = {
        "secret": "SECRET",
        "signal_id": overrides.pop("signal_id", "sig-1"),
        "symbol": "XRPUSDT",
        "side": "long",
        "order_type": "limit",
        "entry": 2.5,
        "stop_loss": 2.47,
        "take_profit": 2.59,
        "leverage": 3,
        "risk_percent": 1.0,
    }
    data.update(overrides)
    signal = TradingViewSignal.model_validate(data)
    db.create_signal(signal, data)
    return db.get_signal(signal.signal_id)


def test_risk_blocks_leverage_over_limit(tmp_path):
    _, db, risk = build_risk(tmp_path)
    signal = store_signal(db, leverage=6)
    with pytest.raises(RiskError):
        risk.validate_signal_for_order(signal, account_balance=1000)


def test_risk_blocks_risk_percent_over_limit(tmp_path):
    _, db, risk = build_risk(tmp_path)
    signal = store_signal(db, risk_percent=1.1)
    with pytest.raises(RiskError):
        risk.validate_signal_for_order(signal, account_balance=1000)


def test_risk_blocks_daily_trade_limit(tmp_path):
    _, db, risk = build_risk(tmp_path)
    signal = store_signal(db)
    for index in range(3):
        db.create_order(f"sig-{index}", "order", "XRPUSDT", "long", "limit", 1, 2.5, "success")
    with pytest.raises(RiskError):
        risk.validate_signal_for_order(signal, account_balance=1000)


def test_risk_blocks_daily_loss_limit(tmp_path):
    _, db, risk = build_risk(tmp_path)
    signal = store_signal(db)
    db.create_order("sig-loss", "order", "XRPUSDT", "long", "limit", 1, 2.5, "success")
    with db.connect() as conn:
        conn.execute("UPDATE orders SET realized_pnl = ? WHERE signal_id = ?", (-30, "sig-loss"))
    with pytest.raises(RiskError):
        risk.validate_signal_for_order(signal, account_balance=1000)


def test_risk_calculates_quantity_from_balance_and_stop(tmp_path):
    _, db, risk = build_risk(tmp_path)
    signal = store_signal(db)
    qty = risk.validate_signal_for_order(signal, account_balance=1000)
    assert qty == 333.3

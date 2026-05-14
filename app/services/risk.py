import math

from app.config import Settings
from app.models import StoredSignal
from app.services.database import Database


class RiskError(ValueError):
    pass


class RiskService:
    def __init__(self, settings: Settings, db: Database):
        self.settings = settings
        self.db = db

    def validate_signal_for_order(self, signal: StoredSignal, account_balance: float) -> float:
        if signal.symbol != self.settings.default_symbol:
            raise RiskError(f"허용되지 않은 심볼입니다: {signal.symbol}")
        if signal.stop_loss is None:
            raise RiskError("손절가가 없는 신호는 주문할 수 없습니다")
        if signal.leverage > self.settings.max_leverage:
            raise RiskError(f"레버리지는 최대 {self.settings.max_leverage}배까지만 허용됩니다")
        if signal.risk_percent > self.settings.max_risk_per_trade:
            raise RiskError(f"1회 거래 리스크는 최대 {self.settings.max_risk_per_trade}%입니다")
        if self.db.today_trade_count() >= self.settings.max_daily_trades:
            raise RiskError(f"하루 최대 거래 횟수 {self.settings.max_daily_trades}회를 초과했습니다")

        today_pnl = self.db.today_realized_pnl()
        if account_balance > 0 and today_pnl < 0:
            daily_loss_percent = abs(today_pnl) / account_balance * 100
            if daily_loss_percent >= self.settings.max_daily_loss:
                raise RiskError(f"하루 최대 손실 {self.settings.max_daily_loss}%에 도달했습니다")

        return self.calculate_quantity(signal, account_balance)

    def calculate_quantity(self, signal: StoredSignal, account_balance: float) -> float:
        loss_per_unit = abs(signal.entry - signal.stop_loss)
        if loss_per_unit <= 0:
            raise RiskError("진입가와 손절가가 같아 수량을 계산할 수 없습니다")
        risk_amount = account_balance * (signal.risk_percent / 100)
        raw_qty = risk_amount / loss_per_unit
        # XRPUSDT는 보통 0.1 단위 주문이 가능하므로 보수적으로 내림 처리합니다.
        qty = math.floor(raw_qty * 10) / 10
        if qty <= 0:
            raise RiskError("계산된 주문 수량이 0 이하입니다")
        return qty

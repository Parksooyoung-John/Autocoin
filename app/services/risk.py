import math

from app.config import Settings
from app.models import OrderType, PlannedOrder, SignalAction, SignalSide, TradingViewSignal
from app.services.database import Database


class RiskError(ValueError):
    pass


class RiskService:
    def __init__(self, settings: Settings, db: Database):
        self.settings = settings
        self.db = db

    def validate_entry(self, signal: TradingViewSignal, account_balance: float) -> PlannedOrder:
        if signal.signal != SignalAction.entry:
            raise RiskError("ENTRY signal is required")
        if signal.symbol not in self.settings.supported_symbols:
            raise RiskError(f"Unsupported symbol: {signal.symbol}")
        if self.db.is_paused():
            raise RiskError("Bot is paused")
        if self.db.open_position_for_symbol(signal.symbol):
            raise RiskError(f"Open position already exists for {signal.symbol}")
        if len(self.db.open_positions()) >= self.settings.max_open_positions:
            raise RiskError(f"Max open positions reached: {self.settings.max_open_positions}")
        if signal.price is None or signal.atr is None:
            raise RiskError("ENTRY requires price and atr")
        if signal.atr <= 0:
            raise RiskError("ATR must be positive")

        leverage = signal.leverage or self.settings.leverage_for(signal.symbol)
        if leverage > self.settings.max_leverage:
            raise RiskError(f"Leverage exceeds max leverage: {leverage} > {self.settings.max_leverage}")

        order_type = signal.order_type or OrderType(self.settings.default_order_type)
        if order_type == OrderType.market and not self.settings.allow_market_entry:
            raise RiskError("Market entry is disabled")

        today_pnl = self.db.today_realized_pnl()
        if account_balance > 0 and today_pnl < 0:
            daily_loss_percent = abs(today_pnl) / account_balance * 100
            if daily_loss_percent >= self.settings.max_daily_loss_percent:
                raise RiskError(f"Daily loss limit reached: {daily_loss_percent:.2f}%")

        stop_loss = self.stop_loss(signal.side, signal.price, signal.atr)
        risk_percent = self.effective_risk_percent(signal.side)
        qty = self.calculate_quantity(
            symbol=signal.symbol,
            entry=signal.price,
            stop_loss=stop_loss,
            account_balance=account_balance,
            risk_percent=risk_percent,
            leverage=leverage,
        )

        return PlannedOrder(
            signal_id=signal.signal_id or "",
            symbol=signal.symbol,
            side=signal.side,
            order_type=order_type,
            entry_price=signal.price,
            stop_loss=stop_loss,
            quantity=qty,
            leverage=leverage,
            risk_percent=risk_percent,
            atr=signal.atr,
        )

    def validate_exit(self, signal: TradingViewSignal) -> dict:
        if signal.symbol not in self.settings.supported_symbols:
            raise RiskError(f"Unsupported symbol: {signal.symbol}")
        position = self.db.open_position_for_symbol(signal.symbol)
        if not position:
            raise RiskError(f"No open position for {signal.symbol}")
        if signal.side and position["side"] != signal.side.value:
            raise RiskError(f"Exit side does not match open position for {signal.symbol}")
        return position

    def stop_loss(self, side: SignalSide, entry: float, atr: float) -> float:
        distance = self.settings.atr_stop_multiplier * atr
        if side == SignalSide.long:
            return entry - distance
        return entry + distance

    def take_profit_prices(self, side: SignalSide, entry: float, leverage: int) -> tuple[float, float]:
        tp1_move = (self.settings.take_profit_1_percent / 100) / leverage
        tp2_move = (self.settings.take_profit_2_percent / 100) / leverage
        if side == SignalSide.long:
            return entry * (1 + tp1_move), entry * (1 + tp2_move)
        return entry * (1 - tp1_move), entry * (1 - tp2_move)

    def trailing_stop(self, side: SignalSide, entry: float, atr: float) -> float:
        distance = self.settings.atr_stop_multiplier * atr
        if side == SignalSide.long:
            return entry - distance
        return entry + distance

    def effective_risk_percent(self, side: SignalSide) -> float:
        risk = self.settings.risk_per_trade_percent
        if side == SignalSide.short:
            risk *= self.settings.short_risk_multiplier
        return risk

    def calculate_quantity(
        self,
        *,
        symbol: str,
        entry: float,
        stop_loss: float,
        account_balance: float,
        risk_percent: float,
        leverage: int,
    ) -> float:
        loss_per_unit = abs(entry - stop_loss)
        if loss_per_unit <= 0:
            raise RiskError("Invalid stop loss distance")

        symbol_cap = account_balance * self.settings.weight_for(symbol)
        risk_cap = account_balance * (risk_percent / 100)
        notional_cap_qty = (symbol_cap * leverage) / entry
        risk_qty = risk_cap / loss_per_unit
        qty = min(notional_cap_qty, risk_qty)
        qty = math.floor((qty + 1e-12) * 1000000) / 1000000
        if qty <= 0:
            raise RiskError("Calculated quantity is too small")
        return qty

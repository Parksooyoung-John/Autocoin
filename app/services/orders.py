import time

from app.config import Settings
from app.models import PlannedOrder, SignalAction, SignalSide, SignalStatus, TradingViewSignal
from app.services.database import Database
from app.services.exchange import ExchangeService
from app.services.risk import RiskService


class OrderService:
    def __init__(self, settings: Settings, db: Database, exchange: ExchangeService, risk: RiskService):
        self.settings = settings
        self.db = db
        self.exchange = exchange
        self.risk = risk

    def handle_entry(self, signal: TradingViewSignal) -> PlannedOrder:
        balance = self.exchange.get_usdt_balance()
        plan = self.risk.validate_entry(signal, balance)
        plan.quantity = self.exchange.normalize_quantity(plan.symbol, plan.quantity)
        plan.stop_loss = self.exchange.normalize_price(plan.symbol, plan.stop_loss)

        tp1, tp2 = self.risk.take_profit_prices(plan.side, plan.entry_price, plan.leverage)
        tp1 = self.exchange.normalize_price(plan.symbol, tp1)
        tp2 = self.exchange.normalize_price(plan.symbol, tp2)
        trailing_stop = self.exchange.normalize_price(
            plan.symbol,
            self.risk.trailing_stop(plan.side, plan.entry_price, plan.atr),
        )

        self.exchange.set_leverage(plan.symbol, plan.leverage)
        response = self.exchange.place_entry_order(plan)
        order_id = extract_order_id(response)
        response = self._wait_for_entry_fill(order_id, plan, response)
        self.db.create_order(
            signal_id=signal.signal_id,
            symbol=plan.symbol,
            side=plan.side.value,
            action=SignalAction.entry.value,
            entry_price=plan.entry_price,
            quantity=plan.quantity,
            leverage=plan.leverage,
            order_id=order_id,
            status=response.get("status") or "submitted",
            exchange_response=response,
        )

        filled_qty = filled_quantity(response)
        if filled_qty <= 0 and response.get("status") != "closed":
            if order_id:
                cancel_response = self.exchange.cancel_order(order_id, plan.symbol)
                self.db.update_order_status(order_id, "cancelled", exchange_response=cancel_response)
            self.db.update_signal_status(signal.signal_id or "", SignalStatus.cancelled)
            response["status"] = "cancelled"
            return plan

        if filled_qty > 0:
            plan.quantity = filled_qty

        self.db.upsert_position(
            symbol=plan.symbol,
            side=plan.side,
            entry_price=plan.entry_price,
            quantity=plan.quantity,
            leverage=plan.leverage,
            stop_loss=plan.stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            trailing_stop=trailing_stop,
            signal_id=signal.signal_id or "",
        )
        self._place_protective_orders(plan, tp1, tp2)
        self.db.update_signal_status(signal.signal_id or "", SignalStatus.ordered)
        return plan

    def handle_exit(self, signal: TradingViewSignal) -> dict:
        position = self.risk.validate_exit(signal)
        side = SignalSide(position["side"])
        qty = float(position["remaining_quantity"])
        response = self.exchange.place_reduce_only_market(signal.symbol, side, qty)
        cancel_response = self.exchange.cancel_open_algo_orders(signal.symbol)
        order_id = extract_order_id(response)
        self.db.create_order(
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            side=side.value,
            action=SignalAction.exit.value,
            exit_price=signal.price,
            quantity=qty,
            leverage=int(position["leverage"]),
            order_id=order_id,
            status=response.get("status") or "submitted",
            exchange_response={"close": response, "cancel_algo": cancel_response},
        )
        self.db.close_position(signal.symbol)
        self.db.update_signal_status(signal.signal_id or "", SignalStatus.closed)
        return response

    def close_position(self, symbol: str, reason: str = "manual_close") -> dict:
        position = self.db.open_position_for_symbol(symbol)
        if not position:
            raise ValueError(f"No open position for {symbol}")
        side = SignalSide(position["side"])
        qty = float(position["remaining_quantity"])
        response = self.exchange.place_reduce_only_market(symbol, side, qty)
        cancel_response = self.exchange.cancel_open_algo_orders(symbol)
        self.db.create_order(
            signal_id=None,
            symbol=symbol,
            side=side.value,
            action="MANUAL_CLOSE",
            exit_price=None,
            quantity=qty,
            leverage=int(position["leverage"]),
            order_id=extract_order_id(response),
            status=response.get("status") or "submitted",
            exchange_response={"reason": reason, "exchange": response, "cancel_algo": cancel_response},
        )
        self.db.close_position(symbol)
        return response

    def _place_protective_orders(self, plan: PlannedOrder, tp1: float, tp2: float) -> None:
        stop = self.exchange.place_stop_market(plan.symbol, plan.side, plan.quantity, plan.stop_loss)
        self.db.create_order(
            signal_id=plan.signal_id,
            symbol=plan.symbol,
            side=plan.side.value,
            action="STOP_LOSS",
            exit_price=plan.stop_loss,
            quantity=plan.quantity,
            leverage=plan.leverage,
            order_id=extract_order_id(stop),
            status=stop.get("status") or "submitted",
            exchange_response=stop,
        )

        tp1_qty = self.exchange.normalize_quantity(plan.symbol, plan.quantity * self.settings.take_profit_1_size)
        tp2_qty = self.exchange.normalize_quantity(plan.symbol, plan.quantity * self.settings.take_profit_2_size)
        for action, price, qty in (("TAKE_PROFIT_1", tp1, tp1_qty), ("TAKE_PROFIT_2", tp2, tp2_qty)):
            response = self.exchange.place_take_profit_market(plan.symbol, plan.side, qty, price)
            self.db.create_order(
                signal_id=plan.signal_id,
                symbol=plan.symbol,
                side=plan.side.value,
                action=action,
                exit_price=price,
                quantity=qty,
                leverage=plan.leverage,
                order_id=extract_order_id(response),
                status=response.get("status") or "submitted",
                exchange_response=response,
            )

    def _wait_for_entry_fill(self, order_id: str, plan: PlannedOrder, response: dict) -> dict:
        if filled_quantity(response) > 0 or response.get("status") == "closed":
            return response
        if not order_id:
            return response

        deadline = time.time() + self.settings.order_timeout_seconds
        latest = response
        while time.time() < deadline:
            time.sleep(1)
            latest = self.exchange.fetch_order(order_id, plan.symbol)
            if filled_quantity(latest) > 0 or latest.get("status") == "closed":
                return latest
            if latest.get("status") in {"canceled", "cancelled", "rejected", "expired"}:
                return latest
        return latest


def extract_order_id(response: dict) -> str:
    return str(response.get("id") or response.get("orderId") or response.get("info", {}).get("orderId") or "")


def filled_quantity(response: dict) -> float:
    filled = response.get("filled")
    if filled is None:
        filled = response.get("info", {}).get("executedQty") or response.get("info", {}).get("cumQty")
    try:
        return float(filled or 0)
    except (TypeError, ValueError):
        return 0

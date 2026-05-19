import logging
import time
from typing import Any, Callable

from app.config import Settings
from app.models import OrderType, PlannedOrder, SignalSide

logger = logging.getLogger(__name__)


class ExchangeError(RuntimeError):
    pass


class ExchangeService:
    def __init__(self, settings: Settings, session: Any | None = None):
        self.settings = settings
        self.session = session or self._build_session()

    def _build_session(self) -> Any:
        if not self.settings.binance_api_key or not self.settings.binance_api_secret:
            logger.warning("Binance API key/secret is empty. Exchange calls will fail until .env is configured.")
        try:
            import ccxt
        except ImportError as exc:
            raise ExchangeError("ccxt is not installed. Run pip install -r requirements.txt") from exc

        exchange = ccxt.binanceusdm(
            {
                "apiKey": self.settings.binance_api_key,
                "secret": self.settings.binance_api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "future", "adjustForTimeDifference": True},
            }
        )
        if self.settings.binance_testnet:
            exchange.set_sandbox_mode(True)
        return exchange

    def get_usdt_balance(self) -> float:
        data = self._retry(lambda: self.session.fetch_balance({"type": "future"}))
        if "USDT" in data:
            return float(data["USDT"].get("free") or data["USDT"].get("total") or 0)
        return float(data.get("free", {}).get("USDT") or data.get("total", {}).get("USDT") or 0)

    def get_positions(self, symbols: list[str] | None = None) -> list[dict[str, Any]]:
        ccxt_symbols = [self._ccxt_symbol(symbol) for symbol in symbols] if symbols else None
        return self._retry(lambda: self.session.fetch_positions(ccxt_symbols))

    def get_position(self, symbol: str) -> dict[str, Any] | None:
        positions = self.get_positions([symbol])
        for position in positions:
            contracts = position.get("contracts")
            if contracts is None:
                info = position.get("info", {})
                contracts = info.get("positionAmt") or 0
            if abs(float(contracts or 0)) > 0:
                return position
        return None

    def has_open_position(self, symbol: str) -> bool:
        return self.get_position(symbol) is not None

    def set_leverage(self, symbol: str, leverage: int) -> Any:
        return self._retry(lambda: self.session.set_leverage(leverage, self._ccxt_symbol(symbol)))

    def normalize_quantity(self, symbol: str, qty: float) -> float:
        ccxt_symbol = self._ccxt_symbol(symbol)
        self._load_markets()
        try:
            value = float(self.session.amount_to_precision(ccxt_symbol, qty))
        except Exception as exc:
            raise ExchangeError(f"Failed to normalize quantity precision: {exc}") from exc
        if value <= 0:
            raise ExchangeError("Calculated quantity is below Binance minimum precision")
        return value

    def normalize_price(self, symbol: str, price: float) -> float:
        ccxt_symbol = self._ccxt_symbol(symbol)
        self._load_markets()
        try:
            return float(self.session.price_to_precision(ccxt_symbol, price))
        except Exception as exc:
            raise ExchangeError(f"Failed to normalize price precision: {exc}") from exc

    def place_entry_order(self, plan: PlannedOrder) -> dict[str, Any]:
        ccxt_symbol = self._ccxt_symbol(plan.symbol)
        side = "buy" if plan.side == SignalSide.long else "sell"
        qty = self.normalize_quantity(plan.symbol, plan.quantity)
        price = self.normalize_price(plan.symbol, plan.entry_price) if plan.order_type == OrderType.limit else None
        params = {"timeInForce": "GTC"} if plan.order_type == OrderType.limit else {}
        return self._retry(lambda: self.session.create_order(ccxt_symbol, plan.order_type.value, side, qty, price, params))

    def place_reduce_only_market(self, symbol: str, side: SignalSide, qty: float) -> dict[str, Any]:
        ccxt_symbol = self._ccxt_symbol(symbol)
        exit_side = "sell" if side == SignalSide.long else "buy"
        qty = self.normalize_quantity(symbol, qty)
        return self._retry(
            lambda: self.session.create_order(ccxt_symbol, "market", exit_side, qty, None, {"reduceOnly": True})
        )

    def place_stop_market(self, symbol: str, side: SignalSide, qty: float, stop_price: float) -> dict[str, Any]:
        ccxt_symbol = self._ccxt_symbol(symbol)
        exit_side = "sell" if side == SignalSide.long else "buy"
        qty = self.normalize_quantity(symbol, qty)
        stop_price = self.normalize_price(symbol, stop_price)
        return self._retry(
            lambda: self.session.create_order(
                ccxt_symbol,
                "STOP_MARKET",
                exit_side,
                qty,
                None,
                {"reduceOnly": True, "workingType": "MARK_PRICE", "stopPrice": stop_price},
            )
        )

    def place_take_profit_market(self, symbol: str, side: SignalSide, qty: float, stop_price: float) -> dict[str, Any]:
        ccxt_symbol = self._ccxt_symbol(symbol)
        exit_side = "sell" if side == SignalSide.long else "buy"
        qty = self.normalize_quantity(symbol, qty)
        stop_price = self.normalize_price(symbol, stop_price)
        return self._retry(
            lambda: self.session.create_order(
                ccxt_symbol,
                "TAKE_PROFIT_MARKET",
                exit_side,
                qty,
                None,
                {"reduceOnly": True, "workingType": "MARK_PRICE", "stopPrice": stop_price},
            )
        )

    def fetch_order(self, order_id: str, symbol: str) -> dict[str, Any]:
        return self._retry(lambda: self.session.fetch_order(order_id, self._ccxt_symbol(symbol)))

    def cancel_order(self, order_id: str, symbol: str) -> dict[str, Any]:
        return self._retry(lambda: self.session.cancel_order(order_id, self._ccxt_symbol(symbol)))

    def _load_markets(self) -> None:
        if hasattr(self.session, "markets") and self.session.markets:
            return
        self._retry(lambda: self.session.load_markets())

    def _ccxt_symbol(self, symbol: str) -> str:
        if "/" in symbol:
            return symbol
        if symbol.endswith("USDT"):
            base = symbol.removesuffix("USDT")
            return f"{base}/USDT:USDT"
        return symbol

    def _retry(self, func: Callable[[], Any]) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self.settings.api_retry_count + 1):
            try:
                return func()
            except Exception as exc:
                last_error = exc
                logger.warning("Binance API call failed (%s/%s): %s", attempt, self.settings.api_retry_count, exc)
                if attempt < self.settings.api_retry_count:
                    time.sleep(0.2 * attempt)
        raise ExchangeError(str(last_error))

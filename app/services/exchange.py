import logging
import time
from typing import Any, Callable

from app.config import Settings
from app.models import StoredSignal

logger = logging.getLogger(__name__)


class ExchangeError(RuntimeError):
    pass


class ExchangeService:
    def __init__(self, settings: Settings, session: Any | None = None):
        self.settings = settings
        self.session = session or self._build_session()

    def _build_session(self) -> Any:
        if not self.settings.bybit_api_key or not self.settings.bybit_api_secret:
            logger.warning("Bybit API key/secret is empty. Exchange calls will fail until .env is configured.")
        try:
            from pybit.unified_trading import HTTP
        except ImportError as exc:
            raise ExchangeError("pybit is not installed. Run pip install -r requirements.txt") from exc
        return HTTP(
            testnet=self.settings.bybit_testnet,
            api_key=self.settings.bybit_api_key,
            api_secret=self.settings.bybit_api_secret,
        )

    def get_usdt_balance(self) -> float:
        data = self._retry(lambda: self.session.get_wallet_balance(accountType="UNIFIED", coin="USDT"))
        coins = data.get("result", {}).get("list", [{}])[0].get("coin", [])
        for coin in coins:
            if coin.get("coin") == "USDT":
                value = coin.get("walletBalance") or coin.get("equity") or 0
                return float(value)
        return 0.0

    def get_position(self, symbol: str) -> dict[str, Any] | None:
        data = self._retry(lambda: self.session.get_positions(category="linear", symbol=symbol))
        positions = data.get("result", {}).get("list", [])
        for position in positions:
            if float(position.get("size") or 0) > 0:
                return position
        return None

    def has_open_position(self, symbol: str) -> bool:
        return self.get_position(symbol) is not None

    def set_leverage(self, symbol: str, leverage: int) -> None:
        self._retry(
            lambda: self.session.set_leverage(
                category="linear",
                symbol=symbol,
                buyLeverage=str(leverage),
                sellLeverage=str(leverage),
            )
        )

    def place_entry_order(self, signal: StoredSignal, qty: float) -> dict[str, Any]:
        side = "Buy" if signal.side.value == "long" else "Sell"
        params: dict[str, Any] = {
            "category": "linear",
            "symbol": signal.symbol,
            "side": side,
            "orderType": "Limit" if signal.order_type.value == "limit" else "Market",
            "qty": str(qty),
        }
        if signal.order_type.value == "limit":
            params["price"] = str(signal.entry)
            params["timeInForce"] = "GTC"
        return self._retry(lambda: self.session.place_order(**params))

    def set_stop_loss_take_profit(self, signal: StoredSignal) -> dict[str, Any]:
        params: dict[str, Any] = {
            "category": "linear",
            "symbol": signal.symbol,
            "stopLoss": str(signal.stop_loss),
            "slTriggerBy": "LastPrice",
            "positionIdx": 0,
        }
        if signal.take_profit:
            params["takeProfit"] = str(signal.take_profit)
            params["tpTriggerBy"] = "LastPrice"
        return self._retry(lambda: self.session.set_trading_stop(**params))

    def _retry(self, func: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.settings.retry_count + 1):
            try:
                response = func()
                ret_code = response.get("retCode", 0)
                if ret_code not in (0, "0"):
                    raise ExchangeError(f"Bybit error {ret_code}: {response.get('retMsg')}")
                return response
            except Exception as exc:
                last_error = exc
                logger.warning("Bybit API call failed (%s/%s): %s", attempt, self.settings.retry_count, exc)
                if attempt < self.settings.retry_count:
                    time.sleep(0.2 * attempt)
        raise ExchangeError(str(last_error))

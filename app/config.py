from functools import lru_cache
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


load_dotenv()


class Settings(BaseSettings):
    app_name: str = "BTC/ETH/XRP Binance Futures 5x Auto Trading Bot"

    webhook_secret: str = Field(
        default="CHANGE_ME",
        validation_alias=AliasChoices("WEBHOOK_SECRET", "TRADINGVIEW_SECRET"),
    )

    binance_api_key: str = Field(default="", alias="BINANCE_API_KEY")
    binance_api_secret: str = Field(default="", alias="BINANCE_API_SECRET")
    binance_testnet: bool = Field(default=True, alias="BINANCE_TESTNET")

    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: int = Field(
        default=0,
        validation_alias=AliasChoices("TELEGRAM_CHAT_ID", "ADMIN_CHAT_ID"),
    )

    supported_symbols: Annotated[list[str], NoDecode] = Field(
        default=["BTCUSDT", "ETHUSDT", "XRPUSDT"],
        alias="SUPPORTED_SYMBOLS",
    )
    symbol_weights: Annotated[dict[str, float], NoDecode] = Field(
        default={"BTCUSDT": 0.4, "XRPUSDT": 0.6},
        alias="SYMBOL_WEIGHTS",
    )
    symbol_leverages: Annotated[dict[str, int], NoDecode] = Field(default={}, alias="SYMBOL_LEVERAGES")

    default_leverage: int = Field(default=5, alias="DEFAULT_LEVERAGE")
    max_leverage: int = Field(default=5, alias="MAX_LEVERAGE")
    risk_per_trade_percent: float = Field(default=1.5, alias="RISK_PER_TRADE_PERCENT")
    max_daily_loss_percent: float = Field(default=5.0, alias="MAX_DAILY_LOSS_PERCENT")
    max_open_positions: int = Field(default=2, alias="MAX_OPEN_POSITIONS")
    short_risk_multiplier: float = Field(default=0.6, alias="SHORT_RISK_MULTIPLIER")
    atr_stop_multiplier: float = Field(default=2.5, alias="ATR_STOP_MULTIPLIER")

    default_order_type: str = Field(default="limit", alias="DEFAULT_ORDER_TYPE")
    allow_market_entry: bool = Field(default=False, alias="ALLOW_MARKET_ENTRY")
    order_timeout_seconds: int = Field(default=30, alias="ORDER_TIMEOUT_SECONDS")
    api_retry_count: int = Field(default=3, alias="API_RETRY_COUNT")

    take_profit_1_percent: float = Field(default=8.0, alias="TAKE_PROFIT_1_PERCENT")
    take_profit_1_size: float = Field(default=0.30, alias="TAKE_PROFIT_1_SIZE")
    take_profit_2_percent: float = Field(default=15.0, alias="TAKE_PROFIT_2_PERCENT")
    take_profit_2_size: float = Field(default=0.40, alias="TAKE_PROFIT_2_SIZE")
    trailing_size: float = Field(default=0.30, alias="TRAILING_SIZE")

    database_url: str = Field(default="sqlite:///./data/trading_bot.db", alias="DATABASE_URL")
    log_file: str = Field(default="./logs/bot.log", alias="LOG_FILE")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    @field_validator("supported_symbols", mode="before")
    @classmethod
    def parse_symbols(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip().upper() for item in value.split(",") if item.strip()]
        return [item.upper().strip() for item in value]

    @field_validator("symbol_weights", mode="before")
    @classmethod
    def parse_weights(cls, value: str | dict[str, float]) -> dict[str, float]:
        if isinstance(value, dict):
            return {key.upper().strip(): float(weight) for key, weight in value.items()}
        return parse_symbol_map(value, float)

    @field_validator("symbol_leverages", mode="before")
    @classmethod
    def parse_leverages(cls, value: str | dict[str, int]) -> dict[str, int]:
        if isinstance(value, dict):
            return {key.upper().strip(): int(leverage) for key, leverage in value.items()}
        return parse_symbol_map(value, int)

    @field_validator("default_order_type")
    @classmethod
    def normalize_order_type(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in {"limit", "market"}:
            raise ValueError("DEFAULT_ORDER_TYPE must be limit or market")
        return value

    @property
    def sqlite_path(self) -> Path:
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("Only sqlite:/// DATABASE_URL is supported")
        return Path(self.database_url.replace("sqlite:///", "", 1))

    def leverage_for(self, symbol: str) -> int:
        return self.symbol_leverages.get(symbol.upper(), self.default_leverage)

    def weight_for(self, symbol: str) -> float:
        return self.symbol_weights.get(symbol.upper(), 0)


def parse_symbol_map(value: str, caster):
    if not value:
        return {}
    result = {}
    for item in value.split(","):
        if not item.strip():
            continue
        symbol, raw = item.split(":", 1)
        result[symbol.strip().upper()] = caster(raw.strip())
    return result


@lru_cache
def get_settings() -> Settings:
    return Settings()

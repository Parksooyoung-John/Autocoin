from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


load_dotenv()


class Settings(BaseSettings):
    app_name: str = "XRPUSDT Semi Auto Trading Bot"
    tradingview_secret: str = Field(default="CHANGE_ME", alias="TRADINGVIEW_SECRET")

    bybit_api_key: str = Field(default="", alias="BYBIT_API_KEY")
    bybit_api_secret: str = Field(default="", alias="BYBIT_API_SECRET")
    bybit_testnet: bool = Field(default=True, alias="BYBIT_TESTNET")

    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    admin_chat_id: int = Field(default=0, alias="ADMIN_CHAT_ID")

    database_url: str = Field(default="sqlite:///./data/bot.db", alias="DATABASE_URL")
    default_symbol: str = Field(default="XRPUSDT", alias="DEFAULT_SYMBOL")

    max_leverage: int = Field(default=5, alias="MAX_LEVERAGE")
    max_risk_per_trade: float = Field(default=1.0, alias="MAX_RISK_PER_TRADE")
    max_daily_loss: float = Field(default=3.0, alias="MAX_DAILY_LOSS")
    max_daily_trades: int = Field(default=3, alias="MAX_DAILY_TRADES")

    retry_count: int = Field(default=3, alias="API_RETRY_COUNT")
    log_file: str = Field(default="./logs/bot.log", alias="LOG_FILE")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    @property
    def sqlite_path(self) -> Path:
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("Only sqlite:/// DATABASE_URL is supported")
        return Path(self.database_url.replace("sqlite:///", "", 1))


@lru_cache
def get_settings() -> Settings:
    return Settings()

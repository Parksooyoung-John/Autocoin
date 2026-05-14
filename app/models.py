from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SignalSide(str, Enum):
    long = "long"
    short = "short"


class OrderType(str, Enum):
    limit = "limit"
    market = "market"


class SignalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    ordered = "ordered"
    failed = "failed"
    cancelled = "cancelled"


class TradingViewSignal(BaseModel):
    secret: str
    signal_id: str = Field(min_length=1, max_length=120)
    symbol: str = Field(min_length=1)
    side: SignalSide
    order_type: OrderType = OrderType.limit
    entry: float = Field(gt=0)
    stop_loss: float | None = Field(default=None)
    take_profit: float | None = Field(default=None)
    leverage: int = Field(gt=0)
    risk_percent: float = Field(gt=0)
    timeframe: str | None = None
    strategy: str | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper().strip()

    @field_validator("stop_loss", "take_profit")
    @classmethod
    def positive_optional_price(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("price must be positive")
        return value


class StoredSignal(BaseModel):
    signal_id: str
    symbol: str
    side: SignalSide
    order_type: OrderType
    entry: float
    stop_loss: float
    take_profit: float | None = None
    leverage: int
    risk_percent: float
    timeframe: str | None = None
    strategy: str | None = None
    status: SignalStatus
    raw_payload: dict[str, Any]
    created_at: datetime

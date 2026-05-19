from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class SignalSide(str, Enum):
    long = "LONG"
    short = "SHORT"


class SignalAction(str, Enum):
    entry = "ENTRY"
    exit = "EXIT"


class OrderType(str, Enum):
    limit = "limit"
    market = "market"


class SignalStatus(str, Enum):
    accepted = "accepted"
    rejected = "rejected"
    ordered = "ordered"
    closed = "closed"
    failed = "failed"
    cancelled = "cancelled"


class PositionStatus(str, Enum):
    open = "open"
    closed = "closed"


class TradingViewSignal(BaseModel):
    secret: str
    symbol: str = Field(min_length=1)
    side: SignalSide
    signal: SignalAction = Field(default=SignalAction.entry)
    price: float | None = Field(default=None, gt=0)
    atr: float | None = Field(default=None, gt=0)
    timeframe: str | None = None
    strategy: str | None = None
    timestamp: str | None = None
    reason: str | None = None
    signal_id: str | None = Field(default=None, max_length=160)
    order_type: OrderType | None = None
    leverage: int | None = Field(default=None, gt=0)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper().strip()

    @field_validator("side", mode="before")
    @classmethod
    def normalize_side(cls, value: str | SignalSide) -> str | SignalSide:
        return value.upper().strip() if isinstance(value, str) else value

    @field_validator("signal", mode="before")
    @classmethod
    def normalize_signal(cls, value: str | SignalAction) -> str | SignalAction:
        return value.upper().strip() if isinstance(value, str) else value

    @field_validator("order_type", mode="before")
    @classmethod
    def normalize_order_type(cls, value: str | OrderType | None) -> str | OrderType | None:
        return value.lower().strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_entry_fields(self) -> "TradingViewSignal":
        if self.signal == SignalAction.entry and (self.price is None or self.atr is None):
            raise ValueError("ENTRY signals require price and atr")
        if not self.signal_id:
            stamp = self.timestamp or datetime.utcnow().isoformat()
            self.signal_id = f"{self.symbol}-{self.side.value}-{self.signal.value}-{stamp}"
        return self

    @property
    def entry_price(self) -> float:
        if self.price is None:
            raise ValueError("price is required")
        return self.price


class ClosePositionRequest(BaseModel):
    symbol: str
    side: SignalSide | None = None
    reason: str = "manual_close"

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper().strip()

    @field_validator("side", mode="before")
    @classmethod
    def normalize_side(cls, value: str | SignalSide | None) -> str | SignalSide | None:
        return value.upper().strip() if isinstance(value, str) else value


class PlannedOrder(BaseModel):
    signal_id: str
    symbol: str
    side: SignalSide
    order_type: OrderType
    entry_price: float
    stop_loss: float
    quantity: float
    leverage: int
    risk_percent: float
    atr: float


class StoredSignal(BaseModel):
    signal_id: str
    timestamp: str | None
    symbol: str
    side: SignalSide
    action: SignalAction
    price: float | None
    atr: float | None
    timeframe: str | None
    strategy: str | None
    reason: str | None
    status: SignalStatus
    raw_payload: dict[str, Any]
    error_message: str | None
    created_at: str

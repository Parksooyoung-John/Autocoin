from typing import Any

from app.config import Settings
from app.services.database import Database
from app.services.exchange import ExchangeService


class PositionService:
    def __init__(self, settings: Settings, db: Database, exchange: ExchangeService):
        self.settings = settings
        self.db = db
        self.exchange = exchange

    def summary(self) -> dict[str, Any]:
        exchange_positions = []
        try:
            exchange_positions = self.exchange.get_positions(self.settings.supported_symbols)
        except Exception as exc:
            exchange_positions = [{"error": str(exc)}]
        return {
            "tracked": self.db.open_positions(),
            "exchange": exchange_positions,
        }

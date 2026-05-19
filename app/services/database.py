import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterator

from app.config import Settings
from app.models import PositionStatus, SignalAction, SignalSide, SignalStatus, StoredSignal, TradingViewSignal


class Database:
    def __init__(self, settings: Settings):
        self.path = settings.sqlite_path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            self._archive_incompatible_tables(conn)
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    signal_id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    action TEXT NOT NULL,
                    price REAL,
                    atr REAL,
                    timeframe TEXT,
                    strategy TEXT,
                    reason TEXT,
                    status TEXT NOT NULL,
                    raw_payload TEXT NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    action TEXT NOT NULL,
                    entry_price REAL,
                    exit_price REAL,
                    quantity REAL NOT NULL,
                    leverage INTEGER NOT NULL,
                    order_id TEXT,
                    status TEXT NOT NULL,
                    pnl REAL NOT NULL DEFAULT 0,
                    error_message TEXT,
                    exchange_response TEXT
                );

                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY,
                    side TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    remaining_quantity REAL NOT NULL,
                    leverage INTEGER NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit_1 REAL NOT NULL,
                    take_profit_2 REAL NOT NULL,
                    trailing_stop REAL,
                    status TEXT NOT NULL,
                    opened_signal_id TEXT NOT NULL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    realized_pnl REAL NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS fills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    action TEXT NOT NULL,
                    price REAL,
                    quantity REAL NOT NULL,
                    fee REAL,
                    pnl REAL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT,
                    source TEXT NOT NULL,
                    message TEXT NOT NULL,
                    detail TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                ("paused", "false", utc_now()),
            )

    def _archive_incompatible_tables(self, conn: sqlite3.Connection) -> None:
        required = {
            "signals": {"signal_id", "action", "price", "atr", "status"},
            "orders": {"signal_id", "action", "entry_price", "exit_price", "quantity", "pnl", "error_message"},
        }
        for table, columns in required.items():
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            if not row:
                continue
            existing = {item["name"] for item in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if columns.issubset(existing):
                continue
            archive = f"{table}_legacy_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
            conn.execute(f"ALTER TABLE {table} RENAME TO {archive}")

    def create_signal(self, signal: TradingViewSignal, raw_payload: dict[str, Any]) -> bool:
        with self.connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO signals
                    (signal_id, timestamp, symbol, side, action, price, atr, timeframe, strategy,
                     reason, status, raw_payload, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        signal.signal_id,
                        signal.timestamp,
                        signal.symbol,
                        signal.side.value,
                        signal.signal.value,
                        signal.price,
                        signal.atr,
                        signal.timeframe,
                        signal.strategy,
                        signal.reason,
                        SignalStatus.accepted.value,
                        json.dumps(raw_payload, ensure_ascii=False),
                        utc_now(),
                    ),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def update_signal_status(
        self,
        signal_id: str,
        status: SignalStatus | str,
        error_message: str | None = None,
    ) -> None:
        value = status.value if isinstance(status, SignalStatus) else status
        with self.connect() as conn:
            conn.execute(
                "UPDATE signals SET status = ?, error_message = COALESCE(?, error_message) WHERE signal_id = ?",
                (value, error_message, signal_id),
            )

    def get_signal(self, signal_id: str) -> StoredSignal | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM signals WHERE signal_id = ?", (signal_id,)).fetchone()
        return row_to_signal(row) if row else None

    def signal_exists(self, signal_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT 1 FROM signals WHERE signal_id = ?", (signal_id,)).fetchone()
        return row is not None

    def create_order(
        self,
        *,
        signal_id: str | None,
        symbol: str,
        side: str,
        action: str,
        quantity: float,
        leverage: int,
        status: str,
        order_id: str | None = None,
        entry_price: float | None = None,
        exit_price: float | None = None,
        pnl: float = 0,
        error_message: str | None = None,
        exchange_response: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO orders
                (signal_id, timestamp, symbol, side, action, entry_price, exit_price, quantity,
                 leverage, order_id, status, pnl, error_message, exchange_response)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_id,
                    utc_now(),
                    symbol,
                    side,
                    action,
                    entry_price,
                    exit_price,
                    quantity,
                    leverage,
                    order_id,
                    status,
                    pnl,
                    error_message,
                    json.dumps(exchange_response or {}, ensure_ascii=False, default=str),
                ),
            )

    def upsert_position(
        self,
        *,
        symbol: str,
        side: SignalSide,
        entry_price: float,
        quantity: float,
        leverage: int,
        stop_loss: float,
        take_profit_1: float,
        take_profit_2: float,
        trailing_stop: float | None,
        signal_id: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO positions
                (symbol, side, entry_price, quantity, remaining_quantity, leverage, stop_loss,
                 take_profit_1, take_profit_2, trailing_stop, status, opened_signal_id, opened_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    side = excluded.side,
                    entry_price = excluded.entry_price,
                    quantity = excluded.quantity,
                    remaining_quantity = excluded.remaining_quantity,
                    leverage = excluded.leverage,
                    stop_loss = excluded.stop_loss,
                    take_profit_1 = excluded.take_profit_1,
                    take_profit_2 = excluded.take_profit_2,
                    trailing_stop = excluded.trailing_stop,
                    status = excluded.status,
                    opened_signal_id = excluded.opened_signal_id,
                    opened_at = excluded.opened_at,
                    closed_at = NULL
                """,
                (
                    symbol,
                    side.value,
                    entry_price,
                    quantity,
                    quantity,
                    leverage,
                    stop_loss,
                    take_profit_1,
                    take_profit_2,
                    trailing_stop,
                    PositionStatus.open.value,
                    signal_id,
                    utc_now(),
                ),
            )

    def close_position(self, symbol: str, pnl: float = 0) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE positions
                SET status = ?, remaining_quantity = 0, closed_at = ?, realized_pnl = realized_pnl + ?
                WHERE symbol = ? AND status = ?
                """,
                (PositionStatus.closed.value, utc_now(), pnl, symbol, PositionStatus.open.value),
            )

    def open_positions(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM positions WHERE status = ? ORDER BY opened_at ASC",
                (PositionStatus.open.value,),
            ).fetchall()
        return [dict(row) for row in rows]

    def open_position_for_symbol(self, symbol: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM positions WHERE symbol = ? AND status = ?",
                (symbol, PositionStatus.open.value),
            ).fetchone()
        return dict(row) if row else None

    def recent_logs(self, limit: int = 50) -> dict[str, list[dict[str, Any]]]:
        with self.connect() as conn:
            orders = conn.execute("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            errors = conn.execute("SELECT * FROM errors ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            signals = conn.execute("SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return {
            "signals": [dict(row) for row in signals],
            "orders": [dict(row) for row in orders],
            "errors": [dict(row) for row in errors],
        }

    def record_error(
        self,
        source: str,
        message: str,
        signal_id: str | None = None,
        detail: Any | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO errors (signal_id, source, message, detail, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    signal_id,
                    source,
                    message,
                    json.dumps(detail, ensure_ascii=False, default=str) if detail is not None else None,
                    utc_now(),
                ),
            )

    def is_paused(self) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", ("paused",)).fetchone()
        return bool(row and row["value"] == "true")

    def set_paused(self, paused: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                ("paused", "true" if paused else "false", utc_now()),
            )

    def today_realized_pnl(self) -> float:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(pnl), 0) AS pnl FROM orders WHERE timestamp >= ?",
                (today_start(),),
            ).fetchone()
        return float(row["pnl"])

    def today_order_count(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM orders WHERE timestamp >= ? AND status NOT IN ('failed', 'cancelled')",
                (today_start(),),
            ).fetchone()
        return int(row["count"])

    def status_summary(self) -> dict[str, Any]:
        return {
            "paused": self.is_paused(),
            "open_positions": len(self.open_positions()),
            "today_orders": self.today_order_count(),
            "today_pnl": self.today_realized_pnl(),
        }


def row_to_signal(row: sqlite3.Row) -> StoredSignal:
    return StoredSignal(
        signal_id=row["signal_id"],
        timestamp=row["timestamp"],
        symbol=row["symbol"],
        side=row["side"],
        action=row["action"],
        price=row["price"],
        atr=row["atr"],
        timeframe=row["timeframe"],
        strategy=row["strategy"],
        reason=row["reason"],
        status=row["status"],
        raw_payload=json.loads(row["raw_payload"]),
        error_message=row["error_message"],
        created_at=row["created_at"],
    )


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def today_start() -> str:
    now = datetime.now(UTC)
    return datetime(now.year, now.month, now.day, tzinfo=UTC).isoformat()

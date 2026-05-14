import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from app.config import Settings
from app.models import SignalStatus, StoredSignal, TradingViewSignal


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
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    signal_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    entry REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL,
                    leverage INTEGER NOT NULL,
                    risk_percent REAL NOT NULL,
                    timeframe TEXT,
                    strategy TEXT,
                    status TEXT NOT NULL,
                    raw_payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    approved_by TEXT NOT NULL,
                    telegram_message_id INTEGER,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT NOT NULL,
                    order_id TEXT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    qty REAL NOT NULL,
                    price REAL,
                    status TEXT NOT NULL,
                    realized_pnl REAL NOT NULL DEFAULT 0,
                    exchange_response TEXT,
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

                CREATE TABLE IF NOT EXISTS bot_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO bot_state (key, value, updated_at) VALUES (?, ?, ?)",
                ("paused", "false", utc_now()),
            )

    def create_signal(self, signal: TradingViewSignal, raw_payload: dict[str, Any]) -> bool:
        with self.connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO signals
                    (signal_id, symbol, side, order_type, entry, stop_loss, take_profit,
                     leverage, risk_percent, timeframe, strategy, status, raw_payload, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        signal.signal_id,
                        signal.symbol,
                        signal.side.value,
                        signal.order_type.value,
                        signal.entry,
                        signal.stop_loss,
                        signal.take_profit,
                        signal.leverage,
                        signal.risk_percent,
                        signal.timeframe,
                        signal.strategy,
                        SignalStatus.pending.value,
                        json.dumps(raw_payload, ensure_ascii=False),
                        utc_now(),
                    ),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def get_signal(self, signal_id: str) -> StoredSignal | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM signals WHERE signal_id = ?", (signal_id,)).fetchone()
        return row_to_signal(row) if row else None

    def update_signal_status(self, signal_id: str, status: SignalStatus | str) -> None:
        value = status.value if isinstance(status, SignalStatus) else status
        with self.connect() as conn:
            conn.execute("UPDATE signals SET status = ? WHERE signal_id = ?", (value, signal_id))

    def pending_signals(self) -> list[StoredSignal]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM signals WHERE status = ? ORDER BY created_at ASC",
                (SignalStatus.pending.value,),
            ).fetchall()
        return [row_to_signal(row) for row in rows]

    def record_approval(
        self,
        signal_id: str,
        action: str,
        approved_by: str,
        telegram_message_id: int | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO approvals (signal_id, action, approved_by, telegram_message_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (signal_id, action, approved_by, telegram_message_id, utc_now()),
            )

    def create_order(
        self,
        signal_id: str,
        order_id: str | None,
        symbol: str,
        side: str,
        order_type: str,
        qty: float,
        price: float | None,
        status: str,
        exchange_response: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO orders
                (signal_id, order_id, symbol, side, order_type, qty, price, status, exchange_response, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_id,
                    order_id,
                    symbol,
                    side,
                    order_type,
                    qty,
                    price,
                    status,
                    json.dumps(exchange_response or {}, ensure_ascii=False),
                    utc_now(),
                ),
            )

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
            row = conn.execute("SELECT value FROM bot_state WHERE key = ?", ("paused",)).fetchone()
        return bool(row and row["value"] == "true")

    def set_paused(self, paused: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO bot_state (key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                ("paused", "true" if paused else "false", utc_now()),
            )

    def today_trade_count(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM orders WHERE created_at >= ? AND status = ?",
                (today_start(), "success"),
            ).fetchone()
        return int(row["count"])

    def today_realized_pnl(self) -> float:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(realized_pnl), 0) AS pnl FROM orders WHERE created_at >= ?",
                (today_start(),),
            ).fetchone()
        return float(row["pnl"])

    def status_summary(self) -> dict[str, Any]:
        with self.connect() as conn:
            pending = conn.execute(
                "SELECT COUNT(*) AS count FROM signals WHERE status = ?",
                (SignalStatus.pending.value,),
            ).fetchone()["count"]
        return {
            "paused": self.is_paused(),
            "pending": int(pending),
            "today_trades": self.today_trade_count(),
            "today_pnl": self.today_realized_pnl(),
        }


def row_to_signal(row: sqlite3.Row) -> StoredSignal:
    return StoredSignal(
        signal_id=row["signal_id"],
        symbol=row["symbol"],
        side=row["side"],
        order_type=row["order_type"],
        entry=row["entry"],
        stop_loss=row["stop_loss"],
        take_profit=row["take_profit"],
        leverage=row["leverage"],
        risk_percent=row["risk_percent"],
        timeframe=row["timeframe"],
        strategy=row["strategy"],
        status=row["status"],
        raw_payload=json.loads(row["raw_payload"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def today_start() -> str:
    now = datetime.now(UTC)
    return datetime(now.year, now.month, now.day, tzinfo=UTC).isoformat()

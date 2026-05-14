import logging
from typing import Any

from app.config import Settings
from app.models import SignalStatus, StoredSignal
from app.services.database import Database
from app.services.exchange import ExchangeError, ExchangeService
from app.services.risk import RiskError, RiskService

logger = logging.getLogger(__name__)

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
    from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
except ImportError:  # pragma: no cover - exercised only before dependencies are installed.
    InlineKeyboardButton = InlineKeyboardMarkup = Update = Application = CallbackQueryHandler = CommandHandler = None
    ContextTypes = None


class TelegramService:
    def __init__(self, settings: Settings, db: Database, exchange: ExchangeService, risk: RiskService):
        self.settings = settings
        self.db = db
        self.exchange = exchange
        self.risk = risk
        self.application: Any | None = None

    async def start(self) -> None:
        if not self.settings.telegram_bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN is empty. Telegram polling is disabled.")
            return
        if Application is None:
            logger.warning("python-telegram-bot is not installed. Telegram polling is disabled.")
            return

        self.application = Application.builder().token(self.settings.telegram_bot_token).build()
        self.application.add_handler(CallbackQueryHandler(self.on_callback))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        self.application.add_handler(CommandHandler("positions", self.cmd_positions))
        self.application.add_handler(CommandHandler("today", self.cmd_today))
        self.application.add_handler(CommandHandler("pause", self.cmd_pause))
        self.application.add_handler(CommandHandler("resume", self.cmd_resume))
        self.application.add_handler(CommandHandler("cancel", self.cmd_cancel))
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        logger.info("Telegram bot started")

    async def stop(self) -> None:
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            logger.info("Telegram bot stopped")

    async def send_signal_alert(self, signal: StoredSignal) -> None:
        if not self.application:
            logger.info("Telegram disabled. Signal pending: %s", signal.signal_id)
            return
        approve_label = "LONG 승인" if signal.side.value == "long" else "SHORT 승인"
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(approve_label, callback_data=f"approve:{signal.signal_id}"),
                    InlineKeyboardButton("거절", callback_data=f"reject:{signal.signal_id}"),
                ]
            ]
        )
        await self.application.bot.send_message(
            chat_id=self.settings.admin_chat_id,
            text=format_signal_message(signal),
            reply_markup=keyboard,
        )

    async def send_admin_message(self, text: str) -> None:
        if self.application:
            await self.application.bot.send_message(chat_id=self.settings.admin_chat_id, text=text)
        else:
            logger.info("Telegram message: %s", text)

    async def on_callback(self, update: Any, context: Any) -> None:
        query = update.callback_query
        await query.answer()
        if not self._is_admin(update):
            await query.edit_message_text("권한이 없습니다.")
            return
        action, signal_id = query.data.split(":", 1)
        result = await self.handle_signal_action(
            signal_id=signal_id,
            action=action,
            actor=str(update.effective_user.id if update.effective_user else update.effective_chat.id),
            telegram_message_id=query.message.message_id if query.message else None,
        )
        await query.edit_message_text(result)

    async def handle_signal_action(
        self,
        signal_id: str,
        action: str,
        actor: str,
        telegram_message_id: int | None = None,
    ) -> str:
        signal = self.db.get_signal(signal_id)
        if not signal:
            return "신호를 찾을 수 없습니다."
        if signal.status.value != SignalStatus.pending.value:
            return f"이미 처리된 신호입니다. 현재 상태: {signal.status.value}"

        self.db.record_approval(signal_id, action, actor, telegram_message_id)
        if action == "reject":
            self.db.update_signal_status(signal_id, SignalStatus.rejected)
            return f"거절 완료: {signal_id}"
        if action != "approve":
            return "알 수 없는 작업입니다."

        try:
            return await self._approve_and_order(signal)
        except Exception as exc:
            self.db.update_signal_status(signal.signal_id, SignalStatus.failed)
            self.db.record_error("telegram_approval", str(exc), signal.signal_id)
            await self.send_admin_message(f"주문 실패 경고\n{signal.signal_id}\n{exc}")
            return f"주문 실패: {exc}"

    async def _approve_and_order(self, signal: StoredSignal) -> str:
        self.db.update_signal_status(signal.signal_id, SignalStatus.approved)
        if self.exchange.has_open_position(signal.symbol):
            raise RiskError("기존 포지션이 있어 새 주문을 차단했습니다")

        balance = self.exchange.get_usdt_balance()
        qty = self.risk.validate_signal_for_order(signal, balance)
        self.exchange.set_leverage(signal.symbol, signal.leverage)
        response = self.exchange.place_entry_order(signal, qty)
        order_id = response.get("result", {}).get("orderId")
        self.db.create_order(
            signal_id=signal.signal_id,
            order_id=order_id,
            symbol=signal.symbol,
            side=signal.side.value,
            order_type=signal.order_type.value,
            qty=qty,
            price=signal.entry if signal.order_type.value == "limit" else None,
            status="submitted",
            exchange_response=response,
        )

        position = self.exchange.get_position(signal.symbol)
        if position is None:
            logger.warning("Order submitted but no open position confirmed yet: %s", signal.signal_id)
        try:
            self.exchange.set_stop_loss_take_profit(signal)
        except ExchangeError as exc:
            self.db.record_error("sl_tp", str(exc), signal.signal_id)
            await self.send_admin_message(f"손절/익절 설정 실패 경고\n{signal.signal_id}\n{exc}")
            raise

        self.db.update_signal_status(signal.signal_id, SignalStatus.ordered)
        await self.send_admin_message(f"주문 성공\n{signal.symbol} {signal.side.value.upper()}\n수량: {qty}\n주문ID: {order_id}")
        return f"주문 성공: {signal.signal_id}"

    async def cmd_status(self, update: Any, context: Any) -> None:
        if not await self._reply_if_admin(update):
            return
        status = self.db.status_summary()
        await update.message.reply_text(
            f"상태: {'PAUSED' if status['paused'] else 'RUNNING'}\n"
            f"Pending: {status['pending']}\n"
            f"오늘 거래: {status['today_trades']}\n"
            f"오늘 손익: {status['today_pnl']}"
        )

    async def cmd_positions(self, update: Any, context: Any) -> None:
        if not await self._reply_if_admin(update):
            return
        try:
            position = self.exchange.get_position(self.settings.default_symbol)
            await update.message.reply_text(f"현재 포지션: {position or '없음'}")
        except Exception as exc:
            await update.message.reply_text(f"포지션 조회 실패: {exc}")

    async def cmd_today(self, update: Any, context: Any) -> None:
        if not await self._reply_if_admin(update):
            return
        await update.message.reply_text(
            f"오늘 거래 횟수: {self.db.today_trade_count()}\n오늘 손익: {self.db.today_realized_pnl()}"
        )

    async def cmd_pause(self, update: Any, context: Any) -> None:
        if not await self._reply_if_admin(update):
            return
        self.db.set_paused(True)
        await update.message.reply_text("신규 신호 수신을 중단했습니다.")

    async def cmd_resume(self, update: Any, context: Any) -> None:
        if not await self._reply_if_admin(update):
            return
        self.db.set_paused(False)
        await update.message.reply_text("신규 신호 수신을 재개했습니다.")

    async def cmd_cancel(self, update: Any, context: Any) -> None:
        if not await self._reply_if_admin(update):
            return
        pending = self.db.pending_signals()
        for signal in pending:
            self.db.update_signal_status(signal.signal_id, SignalStatus.cancelled)
        await update.message.reply_text(f"Pending 신호 {len(pending)}개를 취소했습니다.")

    async def _reply_if_admin(self, update: Any) -> bool:
        if self._is_admin(update):
            return True
        await update.message.reply_text("권한이 없습니다.")
        return False

    def _is_admin(self, update: Any) -> bool:
        chat_id = update.effective_chat.id if update.effective_chat else None
        user_id = update.effective_user.id if update.effective_user else None
        return self.settings.admin_chat_id in (chat_id, user_id)


def format_signal_message(signal: StoredSignal) -> str:
    return (
        f"신규 TradingView 신호\n"
        f"심볼: {signal.symbol}\n"
        f"방향: {signal.side.value.upper()}\n"
        f"진입가: {signal.entry}\n"
        f"손절가: {signal.stop_loss}\n"
        f"익절가: {signal.take_profit or '-'}\n"
        f"레버리지: {signal.leverage}x\n"
        f"예상 손실률: {signal.risk_percent}%\n"
        f"타임프레임: {signal.timeframe or '-'}\n"
        f"전략: {signal.strategy or '-'}\n"
        f"신호ID: {signal.signal_id}"
    )

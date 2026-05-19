import logging

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import ValidationError

from app.models import ClosePositionRequest, SignalAction, TradingViewSignal
from app.services.exchange import ExchangeError
from app.services.risk import RiskError

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/webhook")
async def tradingview_webhook(request: Request) -> dict[str, str]:
    db = request.app.state.db
    settings = request.app.state.settings
    order_service = request.app.state.orders
    telegram = request.app.state.telegram

    try:
        payload = await request.json()
        signal = TradingViewSignal.model_validate(payload)
    except ValidationError as exc:
        db.record_error("webhook", "invalid signal payload", detail=exc.errors())
        raise HTTPException(status_code=400, detail="Invalid TradingView payload") from exc
    except Exception as exc:
        db.record_error("webhook", "invalid json", detail=str(exc))
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    if signal.secret != settings.webhook_secret:
        db.record_error("webhook", "secret mismatch", signal.signal_id)
        raise HTTPException(status_code=401, detail="Invalid secret")

    created = db.create_signal(signal, payload)
    if not created:
        db.record_error("webhook", "duplicate signal", signal.signal_id)
        raise HTTPException(status_code=409, detail="Duplicate signal_id")

    try:
        if signal.signal == SignalAction.entry:
            plan = order_service.handle_entry(signal)
            await telegram.notify_entry(signal.symbol, signal.side.value, plan.quantity, plan.leverage)
            logger.info("Entry signal ordered: %s", signal.signal_id)
            return {"status": "ordered", "signal_id": signal.signal_id or ""}

        order_service.handle_exit(signal)
        await telegram.notify_exit(signal.symbol, signal.reason)
        logger.info("Exit signal submitted: %s", signal.signal_id)
        return {"status": "closed", "signal_id": signal.signal_id or ""}
    except (RiskError, ExchangeError, ValueError) as exc:
        db.update_signal_status(signal.signal_id or "", "failed", str(exc))
        db.record_error("webhook_order", str(exc), signal.signal_id)
        await telegram.notify_error("webhook_order", str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/positions")
async def positions(request: Request) -> dict:
    return request.app.state.positions.summary()


@router.get("/logs")
async def logs(request: Request, limit: int = Query(default=50, ge=1, le=200)) -> dict:
    return request.app.state.db.recent_logs(limit)


@router.post("/close-position")
async def close_position(request: Request, payload: ClosePositionRequest) -> dict[str, str]:
    try:
        request.app.state.orders.close_position(payload.symbol, payload.reason)
        await request.app.state.telegram.notify_exit(payload.symbol, payload.reason)
        return {"status": "close_submitted", "symbol": payload.symbol}
    except (ExchangeError, ValueError) as exc:
        request.app.state.db.record_error("close_position", str(exc), payload.symbol)
        await request.app.state.telegram.notify_error("close_position", str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/pause")
async def pause(request: Request) -> dict[str, str]:
    request.app.state.db.set_paused(True)
    return {"status": "paused"}


@router.post("/resume")
async def resume(request: Request) -> dict[str, str]:
    request.app.state.db.set_paused(False)
    return {"status": "running"}

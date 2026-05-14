import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from app.models import TradingViewSignal

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/webhook")
async def tradingview_webhook(request: Request) -> dict[str, str]:
    db = request.app.state.db
    settings = request.app.state.settings
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

    if signal.secret != settings.tradingview_secret:
        db.record_error("webhook", "secret mismatch", signal.signal_id)
        raise HTTPException(status_code=403, detail="Invalid secret")
    if db.is_paused():
        db.record_error("webhook", "bot paused", signal.signal_id)
        raise HTTPException(status_code=423, detail="Bot is paused")
    if signal.symbol != settings.default_symbol:
        db.record_error("webhook", f"unsupported symbol {signal.symbol}", signal.signal_id)
        raise HTTPException(status_code=400, detail="Unsupported symbol")
    if signal.stop_loss is None:
        db.record_error("webhook", "missing stop loss", signal.signal_id)
        raise HTTPException(status_code=400, detail="stop_loss is required")

    created = db.create_signal(signal, payload)
    if not created:
        db.record_error("webhook", "duplicate signal", signal.signal_id)
        raise HTTPException(status_code=409, detail="Duplicate signal_id")

    stored = db.get_signal(signal.signal_id)
    logger.info("Signal accepted: %s", signal.signal_id)
    await telegram.send_signal_alert(stored)
    return {"status": "pending", "signal_id": signal.signal_id}

# BTC/ETH/XRP Binance Futures 5x 자동매매 봇

TradingView Alert를 FastAPI Webhook 서버로 받아 Binance USDT-M Futures Testnet에서 자동 주문하는 Python 봇입니다. 대상 종목은 `BTCUSDT`, `ETHUSDT`, `XRPUSDT`이며 기본 레버리지는 5배입니다.

기본값은 안전을 위해 `BINANCE_TESTNET=true`입니다. 실전 주문은 `.env`에서 `BINANCE_TESTNET=false`로 명시했을 때만 사용합니다.

## 역할 분담

TradingView가 전략 조건을 계산합니다.

- 4H: EMA20/EMA60/EMA200 기반 메인 추세
- 1H: 눌림 후 반등 또는 반등 실패
- 15M: 세부 진입/청산 관리
- RSI(14), ATR(14), Volume SMA20, 횡보장 필터, BTC 약세 필터

봇은 전략 지표를 다시 계산하지 않습니다. 봇의 책임은 webhook secret 검증, 지원 종목 검증, 중복 진입 방지, 리스크 관리, 주문 실행, SQLite 로그, Telegram 알림입니다.

## 설치

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

## .env 설정

```env
BINANCE_API_KEY=
BINANCE_API_SECRET=
BINANCE_TESTNET=true

WEBHOOK_SECRET=충분히_긴_랜덤_문자열

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=0

DEFAULT_LEVERAGE=5
MAX_DAILY_LOSS_PERCENT=5
RISK_PER_TRADE_PERCENT=1.5
```

Binance API Key에는 출금 권한을 절대 부여하지 마세요. Testnet 검증 전에는 `BINANCE_TESTNET=false`로 바꾸지 마세요.

## 실행

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

상태 확인:

```powershell
curl http://localhost:8000/health
```

TradingView에서 로컬 서버로 webhook을 보내려면 ngrok 같은 HTTPS 터널이 필요합니다.

```powershell
ngrok http 8000
```

TradingView Webhook URL:

```text
https://YOUR_NGROK_DOMAIN/webhook
```

## TradingView Webhook Message

ENTRY 예시:

```json
{
  "secret": "WEBHOOK_SECRET와_같은_값",
  "signal_id": "{{ticker}}-{{timenow}}-entry",
  "symbol": "BTCUSDT",
  "side": "LONG",
  "signal": "ENTRY",
  "timeframe": "1h",
  "price": 65000,
  "atr": 800,
  "strategy": "ema_atr_swing",
  "timestamp": "{{timenow}}"
}
```

EXIT 예시:

```json
{
  "secret": "WEBHOOK_SECRET와_같은_값",
  "signal_id": "{{ticker}}-{{timenow}}-exit",
  "symbol": "BTCUSDT",
  "side": "LONG",
  "signal": "EXIT",
  "reason": "take_profit_1",
  "price": 66300,
  "timestamp": "{{timenow}}"
}
```

`secret` 값은 `.env`의 `WEBHOOK_SECRET` 오른쪽 값과 정확히 같아야 합니다.

## 리스크 관리

- 지원 종목: `BTCUSDT`, `ETHUSDT`, `XRPUSDT`
- 기본 비중: BTC 40%, ETH 40%, XRP 20%
- 기본 레버리지: 5배
- 1회 거래 리스크: 계좌 기준 기본 1.5%
- 하루 최대 손실: 기본 5%
- 동시 포지션: 최대 2개
- 숏 리스크: 롱보다 보수적으로 `SHORT_RISK_MULTIPLIER` 적용
- 물타기, 마틴게일, 동일 심볼 중복 진입 금지

손절은 ATR 기반입니다.

```text
LONG stop_loss = entry - 1.5 * ATR
SHORT stop_loss = entry + 1.5 * ATR
```

익절은 Binance reduce-only 보호 주문으로 등록합니다.

```text
1차 익절: 포지션 수익률 +8%에서 30%
2차 익절: 포지션 수익률 +15%에서 40%
잔여 30%: trailing stop 추적 상태로 DB 기록
```

위 수익률은 레버리지 적용 후 포지션 수익률 기준입니다.

## API

- `POST /webhook`: TradingView 신호 수신 및 자동 주문
- `GET /health`: 서버 상태
- `GET /positions`: Binance 포지션과 DB 추적 포지션
- `GET /logs`: 최근 신호/주문/에러 로그
- `POST /close-position`: 수동 청산
- `POST /pause`: 신규 진입 중단
- `POST /resume`: 신규 진입 재개

수동 청산 예시:

```powershell
curl -X POST http://localhost:8000/close-position `
  -H "Content-Type: application/json" `
  -d '{"symbol":"BTCUSDT","reason":"manual"}'
```

## 테스트

```powershell
pytest
```

테스트는 Binance와 Telegram을 mock 처리하므로 실제 API Key 없이 실행됩니다.

## 실전 전 체크리스트

- Binance Futures Testnet에서 최소 2주 이상 모의 운영
- 주문, 손절, 분할 익절, 수동 청산, pause/resume 확인
- API Key에 출금 권한이 없는지 확인
- `WEBHOOK_SECRET` 외부 노출 여부 확인
- ngrok 또는 배포 서버의 HTTPS 주소가 안정적인지 확인
- `BINANCE_TESTNET=false` 전환 후에도 최초에는 소액으로만 검증

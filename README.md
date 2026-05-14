# XRPUSDT Bybit 반자동 매매봇

TradingView Webhook 신호를 Telegram으로 전달하고, 관리자가 Telegram 버튼으로 승인한 경우에만 Bybit USDT Perpetual 주문을 실행하는 Python 기반 반자동 매매봇입니다. 기본값은 Bybit testnet입니다.

## 안전 원칙

- 완전 자동 진입을 하지 않습니다. Telegram 승인 전에는 주문 함수가 호출되지 않습니다.
- API Key는 `.env`에서만 관리합니다.
- Bybit API Key에는 출금 권한을 부여하지 마세요.
- 기본은 `BYBIT_TESTNET=true`입니다.
- 실거래 전환은 코드 수정이 아니라 `.env`의 `BYBIT_TESTNET=false` 변경으로만 합니다.
- 이 봇은 투자 수익을 보장하지 않습니다.
- 마틴게일, 무한 물타기, 손절 없는 전략은 구현하지 않습니다.

## 설치

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

`.env`를 열어 다음 값을 설정합니다.

```env
BYBIT_API_KEY=Bybit testnet API key
BYBIT_API_SECRET=Bybit testnet API secret
BYBIT_TESTNET=true

TRADINGVIEW_SECRET=충분히_긴_랜덤_문자열

TELEGRAM_BOT_TOKEN=Telegram BotFather token
ADMIN_CHAT_ID=관리자 Telegram chat id
```

## 실행

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

상태 확인:

```bash
curl http://localhost:8000/health
```

Docker 실행:

```bash
copy .env.example .env
docker compose up --build
```

## TradingView Webhook 설정

Webhook URL:

```text
https://YOUR_DOMAIN/webhook
```

예시 메시지:

```json
{
  "secret": "CHANGE_ME",
  "signal_id": "{{ticker}}-{{time}}",
  "symbol": "XRPUSDT",
  "side": "long",
  "order_type": "limit",
  "entry": 2.5000,
  "stop_loss": 2.4700,
  "take_profit": 2.5900,
  "leverage": 3,
  "risk_percent": 1.0,
  "timeframe": "15m",
  "strategy": "EMA20_EMA60_BREAKOUT"
}
```

`secret`은 `.env`의 `TRADINGVIEW_SECRET`과 반드시 같아야 합니다. `signal_id`는 중복 방지 키이므로 재사용하지 마세요.

## Telegram 사용

신호가 들어오면 관리자 채팅에 다음 버튼이 표시됩니다.

- `LONG 승인` 또는 `SHORT 승인`
- `거절`

관리자 명령어:

- `/status`: 봇 상태, pending 신호, 오늘 거래 수, 오늘 손익
- `/positions`: 현재 XRPUSDT 포지션 조회
- `/today`: 오늘 거래 횟수와 손익
- `/pause`: 신규 신호 수신 중단
- `/resume`: 신규 신호 수신 재개
- `/cancel`: pending 신호 전체 취소

`ADMIN_CHAT_ID`와 일치하지 않는 채팅/사용자의 명령과 버튼은 거절됩니다.

## Bybit Testnet 예시

1. Bybit testnet에서 API Key를 생성합니다.
2. 권한은 주문/조회에 필요한 권한만 부여하고 출금 권한은 절대 부여하지 않습니다.
3. `.env`에 `BYBIT_TESTNET=true`를 유지합니다.
4. TradingView webhook을 testnet 서버에 연결된 이 봇 URL로 보냅니다.
5. Telegram에서 승인 버튼을 눌러 주문 흐름을 검증합니다.

## 실거래 전환 주의사항

실거래 전환 전 반드시 다음을 확인하세요.

- testnet에서 주문, SL/TP, 중복 차단, pause/resume을 충분히 검증했는지
- Bybit API Key에 출금 권한이 없는지
- `.env`의 `TRADINGVIEW_SECRET`이 외부에 노출되지 않았는지
- 서버 접근 권한과 로그 보관 위치가 안전한지
- `BYBIT_TESTNET=false` 변경 후 소액으로만 검증했는지

## 테스트

```bash
pytest
```

테스트는 Telegram과 Bybit를 mock 처리하므로 실제 API Key 없이 실행됩니다.

# BTC/XRP Binance Futures 5x 자동매매 봇

TradingView Alert를 FastAPI Webhook 서버로 받아 Binance USDT-M Futures에서 `BTCUSDT`, `ETHUSDT`, `XRPUSDT`를 자동매매하는 Python 봇입니다. 기본 운영 환경은 Binance Demo/Testnet이며, 실전 전환은 `.env`에서 `BINANCE_TESTNET=false`로 명시했을 때만 가능합니다.

> 투자 및 자동매매에는 손실 위험이 있습니다. 실전 전환 전 최소 2주 이상 Demo 환경에서 실제 운영과 동일한 구조로 검증하세요.

## 현재 운영 기준

- Demo도 실전과 동일한 구조로 운영합니다.
- 연습용 임시 URL이나 매번 바뀌는 ngrok URL을 운영 기준으로 쓰지 않습니다.
- 운영 확인은 모바일 중심입니다.
  - TradingView 모바일 앱: Alert 활성 상태 확인
  - Telegram 모바일 앱: 진입/익절/손절/에러 알림 확인
  - Binance 모바일 앱 Demo/Futures: 포지션 확인
  - 모바일 브라우저: `/health` 상태 확인

현재 배포 기준 Webhook 주소:

```text
https://autocoin.auto-coin-bot.com/webhook
```

상태 확인 주소:

```text
https://autocoin.auto-coin-bot.com/health
```

## 전체 흐름

```text
TradingView Alert
→ FastAPI /webhook
→ Signal Validator
→ Risk Manager
→ Binance Futures Demo/Live 주문
→ SQLite 로그 저장
→ Telegram 모바일 알림
```

TradingView가 EMA/RSI/ATR/Volume 조건을 계산합니다. 봇은 지표를 다시 계산하지 않고, secret 검증, 지원 심볼 검증, 중복 진입 방지, 하루 손실 제한, 수량 계산, 주문 실행, 로그 저장, Telegram 알림을 담당합니다.

## 파일 구조

```text
app/
  main.py
  config.py
  exchange.py
  strategy.py
  risk.py
  orders.py
  positions.py
  database.py
  telegram.py
  schemas.py
  utils.py
tests/
.env.example
requirements.txt
README.md
```

## 필수 환경변수

`.env.example`을 복사해 `.env`를 만들고 실제 값을 입력합니다. `.env`는 절대 GitHub에 올리지 않습니다.

```env
BINANCE_API_KEY=
BINANCE_API_SECRET=
BINANCE_TESTNET=true

WEBHOOK_SECRET=CHANGE_ME

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=0

SUPPORTED_SYMBOLS=BTCUSDT,XRPUSDT
SYMBOL_WEIGHTS=BTCUSDT:0.4,XRPUSDT:0.6
SYMBOL_LEVERAGES=BTCUSDT:5,XRPUSDT:5

DEFAULT_LEVERAGE=5
MAX_LEVERAGE=5
MAX_OPEN_POSITIONS=2
RISK_PER_TRADE_PERCENT=1.5
MAX_DAILY_LOSS_PERCENT=5
ATR_STOP_MULTIPLIER=2.5

DEFAULT_ORDER_TYPE=limit
ALLOW_MARKET_ENTRY=false
ORDER_TIMEOUT_SECONDS=30

TAKE_PROFIT_1_PERCENT=8
TAKE_PROFIT_1_SIZE=0.30
TAKE_PROFIT_2_PERCENT=15
TAKE_PROFIT_2_SIZE=0.40
TRAILING_SIZE=0.30

DATABASE_URL=sqlite:///./data/trading_bot.db
API_RETRY_COUNT=3
LOG_FILE=./logs/bot.log
```

| 항목 | 효과 |
| --- | --- |
| `BINANCE_API_KEY`, `BINANCE_API_SECRET` | Binance Futures Demo 또는 Live 계정 조회/주문에 사용합니다. 출금 권한 없는 Key만 사용합니다. |
| `BINANCE_TESTNET` | `true`면 Demo endpoint를 사용합니다. Live 전환은 `false`일 때만 가능합니다. |
| `WEBHOOK_SECRET` | TradingView에서 들어온 요청이 내 봇용 신호인지 검증합니다. 노출되면 즉시 교체하세요. |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | 주문, 청산, 에러, 일일 요약 알림을 모바일로 받습니다. |
| `SYMBOL_WEIGHTS` | 기본 포트폴리오 비중을 제어합니다. 현재 v5-LONG 기준 기본은 BTC 40%, XRP 60%이며 ETH는 보류입니다. |
| `RISK_PER_TRADE_PERCENT` | 1회 거래 최대 손실 한도입니다. |
| `MAX_DAILY_LOSS_PERCENT` | 하루 손실 한도입니다. 도달 시 신규 진입을 차단합니다. |
| `DEFAULT_ORDER_TYPE` | 기본 진입 주문 방식입니다. 운영 기본값은 `limit`입니다. |
| `ORDER_TIMEOUT_SECONDS` | Limit 주문이 이 시간 안에 체결되지 않으면 자동 취소합니다. |

## WEBHOOK_SECRET 생성 및 교체

Windows PowerShell:

```powershell
[guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
```

Linux:

```bash
openssl rand -hex 32
```

생성한 값을 `.env`의 `WEBHOOK_SECRET`과 TradingView Pine Script의 `secret`에 동일하게 넣습니다. 화면 캡처, 로그, 채팅에 노출되면 새 값으로 교체하고 서버를 재시작하세요.

## Binance Demo API Key

1. Binance Demo Trading API Management로 이동합니다.

```text
https://demo.binance.com/en/my/settings/api-management
```

2. `Create API`를 선택합니다.
3. `System generated`를 선택합니다.
4. 생성된 `API Key`, `Secret Key`를 `.env`에 입력합니다.
5. `.env`에서 `BINANCE_TESTNET=true`를 유지합니다.
6. Demo Futures 계정에 USDT 잔고가 있는지 확인합니다.

Demo와 Live의 차이:

- Demo: Demo API Key, Demo endpoint, 모의 잔고 사용
- Live: Live API Key, Live endpoint, 실제 자금 사용
- 공통: TradingView Alert, Webhook URL, Telegram 알림, 리스크 관리, 주문/청산 흐름은 동일하게 운영

## Telegram Bot Token 재발급

Token이 노출되면 즉시 재발급합니다.

1. Telegram에서 `@BotFather`를 엽니다.
2. `/mybots` 입력
3. 봇 선택
4. `API Token` 선택
5. `Revoke current token` 또는 새 token 발급
6. 서버 `.env`의 `TELEGRAM_BOT_TOKEN` 교체
7. 봇 서비스 재시작

Chat ID 확인:

1. 봇에게 아무 메시지나 보냅니다.
2. 브라우저에서 아래 주소를 엽니다.

```text
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates
```

3. 응답의 `chat.id` 값을 `.env`의 `TELEGRAM_CHAT_ID`에 입력합니다.

## TradingView Alert 설정

Alert는 심볼별로 1개씩 생성합니다. Pine Script 안에서 `alert()`가 ENTRY와 EXIT 메시지를 모두 보내므로 ENTRY/EXIT Alert를 따로 만들 필요는 없습니다.

권장 설정:

```text
Condition: AutoCoin EMA ATR Signal
Trigger: Any alert() function call
Interval: 4 hours
Message: blank
Webhook URL: https://autocoin.auto-coin-bot.com/webhook
```

심볼별 확인:

```text
BTCUSDT chart → Bot Symbol = BTCUSDT → Alert name BTC_AUTO
ETHUSDT chart → Bot Symbol = ETHUSDT → Alert name ETH_AUTO
XRPUSDT chart → Bot Symbol = XRPUSDT → Alert name XRP_AUTO
```

차트 심볼과 `Bot Symbol`이 다르면 다른 종목으로 주문이 나갈 수 있으니 반드시 일치시킵니다.

ENTRY 메시지에는 `price`와 `atr`이 필요합니다.

- `price`: 진입 기준 가격입니다. 보통 Pine Script의 `close`를 사용합니다.
- `atr`: ATR 기반 손절가와 주문 수량 계산에 사용합니다.
- LONG 손절가: `entry - 1.5 * ATR`
- SHORT 손절가: `entry + 1.5 * ATR`

## 서버 설치 요약

Ubuntu 서버 기준:

```bash
sudo apt update
sudo apt install -y git python3-venv python3-pip curl unzip
git clone https://github.com/Parksooyoung-John/Autocoin.git
cd Autocoin
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
```

설정 확인:

```bash
python - <<'PY'
from app.config import get_settings
settings = get_settings()
print("BINANCE_TESTNET =", settings.binance_testnet)
print("SUPPORTED_SYMBOLS =", settings.supported_symbols)
print("TELEGRAM_CONFIGURED =", bool(settings.telegram_bot_token and settings.telegram_chat_id))
print("WEBHOOK_SECRET_CONFIGURED =", bool(settings.webhook_secret and settings.webhook_secret != "CHANGE_ME"))
print("BINANCE_KEY_CONFIGURED =", bool(settings.binance_api_key and settings.binance_api_secret))
PY
```

## systemd 운영

`/etc/systemd/system/autocoin.service`:

```ini
[Unit]
Description=Autocoin FastAPI Trading Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/Autocoin
Environment="PATH=/home/ubuntu/Autocoin/.venv/bin"
ExecStart=/home/ubuntu/Autocoin/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

서비스 시작:

```bash
sudo systemctl daemon-reload
sudo systemctl enable autocoin
sudo systemctl start autocoin
sudo systemctl status autocoin --no-pager
```

로그 확인:

```bash
sudo journalctl -u autocoin -f
```

## Caddy HTTPS 설정

Cloudflare DNS:

```text
Type: A
Name: autocoin
IPv4 address: 3.37.181.250
Proxy status: DNS only
TTL: Auto
```

`/etc/caddy/Caddyfile`:

```caddy
autocoin.auto-coin-bot.com {
    reverse_proxy 127.0.0.1:8000
}
```

적용:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
curl https://autocoin.auto-coin-bot.com/health
```

## API 확인

```bash
curl https://autocoin.auto-coin-bot.com/health
curl https://autocoin.auto-coin-bot.com/positions
```

기대값:

```json
{"status":"ok","testnet":true,"paused":false}
```

포지션이 없으면:

```json
{"tracked":[],"exchange":[]}
```

## 리스크 관리

- 기본 레버리지 5배
- 최대 동시 포지션 2개
- BTC/XRP 기본 비중 40/60
- 1회 거래 손실 한도 기본 1.5%
- 하루 최대 손실 기본 5%
- 동일 심볼 중복 진입 차단
- 물타기 금지
- 마틴게일 금지
- 손절 없는 진입 차단
- XRP 비중은 BTC/ETH보다 작게 유지
- 숏은 롱보다 작은 리스크 배율 적용 가능

## 운영 체크리스트

매일 모바일에서 확인:

- Telegram 알림 수신 여부
- TradingView Alert 활성 상태
- Binance Demo Futures 포지션
- `https://autocoin.auto-coin-bot.com/health`
- `/positions` 값과 Binance Demo 포지션 일치 여부

실전 전환 전:

- 최소 2주 이상 Demo 운영 기록 확인
- Binance Live API Key에 출금 권한 없음 확인
- `WEBHOOK_SECRET` 새로 생성
- `TELEGRAM_BOT_TOKEN` 노출 이력 있으면 재발급
- 처음 실전 리스크는 `RISK_PER_TRADE_PERCENT=0.3~0.5` 수준으로 낮춰 시작
- `.env`에서 `BINANCE_TESTNET=false` 전환 후 서비스 재시작

## 테스트

```bash
pytest
```

# BTC/ETH/XRP Binance Futures 5x 자동매매 봇

TradingView Alert를 FastAPI Webhook 서버로 받아 Binance USDT-M Futures에서 자동 주문하는 Python 봇입니다. 대상 종목은 `BTCUSDT`, `ETHUSDT`, `XRPUSDT`이며 기본 레버리지는 5배입니다.

기본값은 안전을 위해 `BINANCE_TESTNET=true`입니다. 이 값이 `true`이면 Binance Futures Demo Trading endpoint(`https://demo-fapi.binance.com`)를 사용합니다. 실전 주문은 `.env`에서 `BINANCE_TESTNET=false`로 명시했을 때만 사용합니다.

## 운영 원칙

이 프로젝트의 기준은 **Demo도 실전과 동일한 구조로 운영 검증**하는 것입니다. 연습용 임시 방식은 권장하지 않습니다.

- Demo와 Live는 API endpoint, API Key, 실제 자금 여부만 다릅니다.
- TradingView Alert, 고정 HTTPS Webhook URL, Telegram 모바일 알림, 리스크 제한, 주문/청산 흐름은 Demo와 Live에서 동일하게 유지합니다.
- 운영 확인은 모바일에서 가능해야 합니다. Telegram 모바일 알림과 TradingView 모바일 알림을 기준으로 상태를 확인합니다.
- PC에서 수동으로 curl을 날리거나, 매번 바뀌는 임시 URL을 수정하는 방식은 운영 기준으로 삼지 않습니다.
- 실전과 같은 Demo 운영을 위해 고정 HTTPS 주소와 항상 켜져 있는 서버를 권장합니다.

## 전체 흐름

```text
TradingView 전략/지표
→ Alert 발생
→ Webhook URL로 봇의 /webhook 호출
→ 봇이 secret, symbol, 리스크, 중복 진입 확인
→ Binance Futures Demo/Live 주문
→ 손절/분할 익절 reduce-only 주문 등록
→ SQLite 로그 저장
→ Telegram 알림
```

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

## 필수 설정 요약

`.env`는 공개 저장소에 올리면 안 됩니다. `.env.example`을 복사한 뒤 실제 값을 채웁니다.

```env
BINANCE_API_KEY=
BINANCE_API_SECRET=
BINANCE_TESTNET=true

WEBHOOK_SECRET=CHANGE_ME

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=0

SUPPORTED_SYMBOLS=BTCUSDT,ETHUSDT,XRPUSDT
SYMBOL_WEIGHTS=BTCUSDT:0.4,ETHUSDT:0.4,XRPUSDT:0.2
SYMBOL_LEVERAGES=BTCUSDT:5,ETHUSDT:5,XRPUSDT:5

DEFAULT_LEVERAGE=5
MAX_LEVERAGE=5
MAX_OPEN_POSITIONS=2
RISK_PER_TRADE_PERCENT=1.5
MAX_DAILY_LOSS_PERCENT=5
SHORT_RISK_MULTIPLIER=0.6
ATR_STOP_MULTIPLIER=1.5

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

## 환경변수별 설정 방법과 효과

| 항목 | 설정 방법 | 효과 |
| --- | --- | --- |
| `BINANCE_API_KEY` | Binance Demo Trading 또는 Live 계정의 API Key를 입력합니다. | 봇이 Binance Futures 계정 조회와 주문을 실행할 때 사용합니다. |
| `BINANCE_API_SECRET` | API 생성 직후 표시되는 Secret Key를 입력합니다. | Binance signed API 요청 서명에 사용합니다. 생성 후 다시 볼 수 없으니 안전하게 보관합니다. |
| `BINANCE_TESTNET` | Demo 운영은 `true`, 실전 운영은 `false`로 둡니다. | `true`면 `https://demo-fapi.binance.com`을 사용합니다. `false`면 실거래 Futures API를 사용하므로 매우 주의해야 합니다. |
| `WEBHOOK_SECRET` | 충분히 긴 랜덤 문자열을 넣고 TradingView Alert Message의 `secret`과 동일하게 맞춥니다. | 외부인이 임의로 `/webhook`에 주문 신호를 보내는 것을 막습니다. 노출되면 즉시 교체해야 합니다. |
| `TELEGRAM_BOT_TOKEN` | BotFather에서 발급한 봇 토큰을 입력합니다. | 주문 성공, 청산, 에러 알림을 Telegram으로 보냅니다. 노출되면 BotFather에서 재발급해야 합니다. |
| `TELEGRAM_CHAT_ID` | 봇에게 메시지를 보낸 뒤 `getUpdates`에서 chat id를 확인해 입력합니다. | 알림을 받을 Telegram 사용자 또는 채팅방을 지정합니다. |
| `SUPPORTED_SYMBOLS` | 쉼표로 거래 허용 종목을 입력합니다. 기본값은 `BTCUSDT,ETHUSDT,XRPUSDT`입니다. | 목록에 없는 symbol의 webhook은 거부됩니다. |
| `SYMBOL_WEIGHTS` | `BTCUSDT:0.4,ETHUSDT:0.4,XRPUSDT:0.2` 형식으로 입력합니다. | 종목별 최대 노출 비중을 제한합니다. XRP 비중을 작게 두는 식의 방어 설정입니다. |
| `SYMBOL_LEVERAGES` | `BTCUSDT:5,ETHUSDT:5,XRPUSDT:5` 형식으로 입력합니다. | 종목별 레버리지를 지정합니다. 없으면 `DEFAULT_LEVERAGE`를 사용합니다. |
| `DEFAULT_LEVERAGE` | 기본값 `5`를 사용합니다. | 별도 지정이 없는 종목의 기본 레버리지입니다. |
| `MAX_LEVERAGE` | 기본값 `5`를 사용합니다. | webhook이 더 높은 레버리지를 보내도 이 값을 넘으면 주문을 차단합니다. |
| `MAX_OPEN_POSITIONS` | Demo와 Live에서 동일하게 적용할 최대 동시 포지션 수를 입력합니다. 기본값은 `2`입니다. | 동시에 열 수 있는 포지션 수를 제한합니다. |
| `RISK_PER_TRADE_PERCENT` | Demo와 Live에서 동일하게 검증할 1회 거래 리스크를 입력합니다. 기본값은 `1.5`입니다. | 1회 거래에서 계좌 기준 감수할 최대 손실률입니다. ATR 손절폭과 함께 주문 수량을 계산합니다. |
| `MAX_DAILY_LOSS_PERCENT` | Demo와 Live에서 동일하게 적용할 하루 최대 손실률을 입력합니다. 기본값은 `5`입니다. | 하루 손실률이 이 값에 도달하면 신규 진입을 막습니다. |
| `SHORT_RISK_MULTIPLIER` | 기본값 `0.6`입니다. | 숏 진입 수량을 롱보다 보수적으로 줄입니다. |
| `ATR_STOP_MULTIPLIER` | 기본값 `1.5`입니다. | 손절가 계산에 사용합니다. LONG은 `entry - 1.5 * ATR`, SHORT은 `entry + 1.5 * ATR`입니다. |
| `DEFAULT_ORDER_TYPE` | 기본값 `limit`입니다. | 기본 진입 주문 방식을 정합니다. 실전은 슬리피지 방지를 위해 limit 우선입니다. |
| `ALLOW_MARKET_ENTRY` | 기본값 `false`입니다. | `true`일 때만 webhook의 market 진입을 허용합니다. 급등락 돌파 전략 외에는 `false` 권장입니다. |
| `ORDER_TIMEOUT_SECONDS` | 기본값 `30`입니다. | limit 진입 주문이 이 시간 안에 체결되지 않으면 자동 취소합니다. 체결되지 않은 주문에는 보호 주문을 깔지 않습니다. |
| `TAKE_PROFIT_1_PERCENT` / `TAKE_PROFIT_1_SIZE` | 기본값 `8`, `0.30`입니다. | 포지션 수익률 +8%에서 30% 청산 주문을 등록합니다. |
| `TAKE_PROFIT_2_PERCENT` / `TAKE_PROFIT_2_SIZE` | 기본값 `15`, `0.40`입니다. | 포지션 수익률 +15%에서 40% 청산 주문을 등록합니다. |
| `TRAILING_SIZE` | 기본값 `0.30`입니다. | 잔여 30% 추적 관리를 위한 비중입니다. 현재는 DB 추적 상태로 기록합니다. |
| `DATABASE_URL` | 기본값 `sqlite:///./data/trading_bot.db`입니다. | 신호, 주문, 포지션, 에러 로그를 저장합니다. |
| `LOG_FILE` | 기본값 `./logs/bot.log`입니다. | 운영 로그 파일 위치입니다. Telegram token은 로그 필터로 마스킹됩니다. |

## WEBHOOK_SECRET 생성과 교체

PowerShell에서 긴 랜덤 문자열을 생성합니다.

```powershell
[guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
```

`.env`에 넣습니다.

```env
WEBHOOK_SECRET=생성한_긴_문자열
```

TradingView Alert Message의 `"secret"`도 같은 값으로 바꿉니다.

```json
{
  "secret": "생성한_긴_문자열"
}
```

효과: 봇은 이 값이 맞는 webhook만 처리합니다. 값이 다르면 `401 Invalid secret`으로 거부합니다. 화면 공유, 로그, GitHub, 채팅에 노출되었다면 즉시 새 값으로 교체하세요.

## Binance Demo API Key 발급

Demo 매매 연습은 Live Binance API Key가 아니라 Demo Trading API Key를 사용합니다.

1. Demo API 관리 화면으로 이동합니다.

```text
https://demo.binance.com/en/my/settings/api-management
```

2. `Create API`를 누릅니다.
3. `System generated`를 선택합니다.
4. API 이름을 입력합니다. 예: `autocoin-demo-bot`.
5. 생성된 `API Key`, `Secret Key`를 `.env`에 입력합니다.

```env
BINANCE_API_KEY=Demo_API_Key
BINANCE_API_SECRET=Demo_Secret_Key
BINANCE_TESTNET=true
```

6. Demo Futures 화면에서 USDT 잔고를 확인합니다. 잔고가 없다면 `Reset Asset` 또는 Demo 자산 초기화 기능으로 충전합니다.

효과: `BINANCE_TESTNET=true`일 때 봇은 Demo Futures endpoint로만 주문합니다. Demo Key와 Live Key는 서로 호환되지 않습니다.

## Telegram Bot Token 발급과 재발급

### 새 봇 생성

1. Telegram에서 `@BotFather`를 엽니다.
2. `/newbot`을 입력합니다.
3. 봇 이름과 username을 정합니다.
4. BotFather가 발급한 token을 `.env`에 넣습니다.

```env
TELEGRAM_BOT_TOKEN=123456:ABC...
```

### Chat ID 확인

1. 만든 봇에게 아무 메시지를 보냅니다.
2. 브라우저에서 아래 주소를 엽니다.

```text
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates
```

3. 응답 JSON의 `chat.id` 값을 `.env`에 넣습니다.

```env
TELEGRAM_CHAT_ID=123456789
```

### Token 재발급

토큰이 화면, 로그, 채팅, GitHub에 노출되면 재발급하세요.

1. BotFather에서 `/mybots`를 입력합니다.
2. 대상 봇 선택
3. `API Token`
4. `Revoke current token` 또는 새 token 발급
5. `.env`의 `TELEGRAM_BOT_TOKEN` 교체
6. 서버 재시작

효과: Telegram 알림 권한을 새 토큰으로 이전하고, 기존 노출 토큰은 사용할 수 없게 만듭니다.

## 실행과 상태 확인

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

상태 확인:

```powershell
curl http://localhost:8000/health
```

기대 응답:

```json
{
  "status": "ok",
  "testnet": true,
  "paused": false,
  "supported_symbols": ["BTCUSDT", "ETHUSDT", "XRPUSDT"]
}
```

포지션 확인:

```powershell
curl http://localhost:8000/positions
```

Demo API Key가 정상이고 포지션이 없으면 아래처럼 보입니다.

```json
{
  "tracked": [],
  "exchange": []
}
```

## 고정 HTTPS Webhook 주소

TradingView는 내 PC의 `localhost`에 직접 접근할 수 없습니다. Demo와 Live를 같은 구조로 운영하려면 **고정 HTTPS 주소**를 사용합니다.

권장 순서:

```text
1. 클라우드 서버 또는 항상 켜져 있는 PC에 봇 실행
2. 고정 도메인 또는 ngrok static domain 연결
3. TradingView Webhook URL을 고정 주소로 설정
4. 모바일 Telegram 알림으로 주문/에러 확인
```

ngrok을 사용할 경우 무료 임시 주소가 아니라 static domain 또는 reserved domain을 사용합니다.

```powershell
ngrok http --domain=YOUR_STATIC_DOMAIN.ngrok.app 8000
```

TradingView에는 `/webhook`을 붙여 입력합니다.

```text
https://YOUR_STATIC_DOMAIN.ngrok.app/webhook
```

효과: TradingView Alert가 항상 같은 주소로 봇 서버에 도착합니다. 주소가 고정되어야 모바일로만 운영 상태를 확인할 수 있고, 매번 PC에서 Alert URL을 수정하지 않아도 됩니다.

## TradingView Alert 설정

TradingView 유료 플랜에서 Webhook Alert를 사용할 수 있습니다. 계정 2FA도 켜야 합니다.

1. 차트에서 전략 또는 지표를 설정합니다.
2. Alert 생성
3. Webhook URL 체크
4. Webhook URL에 아래 형식 입력

```text
https://xxxx.ngrok-free.app/webhook
```

5. Message 칸에 ENTRY 또는 EXIT JSON 입력

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
  "reason": "manual_or_strategy_exit",
  "price": 66300,
  "timestamp": "{{timenow}}"
}
```

중요:

- ENTRY에는 `price`와 `atr`가 반드시 필요합니다.
- `atr`는 TradingView Pine Script에서 계산한 숫자여야 합니다.
- `symbol`은 `BTCUSDT`, `ETHUSDT`, `XRPUSDT` 중 하나여야 합니다.
- `side`는 `LONG` 또는 `SHORT`입니다.
- `signal_id`는 중복되면 안 됩니다. `{{ticker}}-{{timenow}}-entry`처럼 고유하게 만드세요.

## Demo 시뮬레이션 운영 절차

Demo도 실전과 동일한 TradingView Alert 연동 기준으로 진행합니다. 수동 curl 주문이나 일회성 테스트 방식은 운영 기준으로 사용하지 않습니다.

1. `.env`에서 Demo와 Live에 동일하게 적용할 운영 값을 확정합니다.

```env
BINANCE_TESTNET=true
RISK_PER_TRADE_PERCENT=1.5
MAX_DAILY_LOSS_PERCENT=5
MAX_OPEN_POSITIONS=2
DEFAULT_ORDER_TYPE=limit
ALLOW_MARKET_ENTRY=false
```

2. 서버 실행 후 상태를 확인합니다.

```powershell
curl http://localhost:8000/health
curl http://localhost:8000/positions
```

3. 고정 HTTPS Webhook 주소를 준비합니다.

```powershell
ngrok http --domain=YOUR_STATIC_DOMAIN.ngrok.app 8000
```

4. TradingView Alert를 Demo 운영 종목 기준으로 연결합니다.
5. Telegram 모바일 알림이 오는지 확인합니다.
6. TradingView 모바일 앱에서도 Alert 상태를 확인합니다.
7. 매일 아래 항목을 기록합니다.

```text
거래 수
승률
평균 수익
평균 손실
최대 연속 손실
하루 손익
심볼별 손익
롱/숏별 손익
/logs 에러 여부
Binance 포지션과 /positions 일치 여부
손절/익절 조건부 주문 생성 여부
```

운영 중단:

```powershell
curl -X POST http://localhost:8000/pause
```

운영 재개:

```powershell
curl -X POST http://localhost:8000/resume
```

수동 청산:

```powershell
curl -X POST http://localhost:8000/close-position `
  -H "Content-Type: application/json" `
  -d '{"symbol":"BTCUSDT","reason":"manual"}'
```

효과: `pause`는 신규 진입만 막습니다. 이미 열린 포지션은 Binance에 등록된 손절/익절 주문 또는 수동 청산으로 관리해야 합니다. 모바일 운영 기준에서는 Telegram 알림을 보고 필요 시 모바일 브라우저 또는 서버 관리 앱에서 해당 API를 호출할 수 있게 준비합니다.

## 모바일 운영 기준

운영자는 PC 화면을 계속 켜두지 않고 모바일에서 상태를 확인할 수 있어야 합니다.

필수 모바일 확인 채널:

- Telegram 모바일 앱: 진입, 청산, 에러 알림
- TradingView 모바일 앱: Alert 활성 상태와 차트 조건 확인
- Binance 모바일 앱 또는 Demo 웹: 포지션과 주문 상태 확인

권장 서버 기준:

- 봇 서버는 항상 켜져 있어야 합니다.
- Webhook URL은 고정 HTTPS 주소여야 합니다.
- 서버 재시작 후 `/health`, `/positions`가 정상인지 확인해야 합니다.
- ngrok을 쓴다면 static domain을 사용하고, 무료 임시 URL을 운영 기준으로 삼지 않습니다.

## Demo와 실전 매매의 차이

| 구분 | Demo Trading | 실제 매매 |
| --- | --- | --- |
| 자금 | 가상 잔고 | 실제 자산 |
| API endpoint | `https://demo-fapi.binance.com` | Binance Live Futures endpoint |
| API Key | Demo API Key | Live Binance API Key |
| 손실 | 실제 손실 없음 | 실제 손실 발생 |
| 체결 환경 | 실제 시장과 비슷하지만 완전히 같지는 않음 | 실제 유동성, 슬리피지, 수수료 영향 |
| 심리 영향 | 낮음 | 높음 |
| 목적 | 시스템 안정성, 주문 흐름, 전략 신호 검증 | 소액부터 제한적으로 운용 |

Demo에서 확인해야 할 것은 단순한 연습이 아니라 **실전과 동일한 자동매매 운영 절차가 안전하게 반복되는지**입니다.

필수 확인:

- Webhook secret 불일치 시 주문 거부
- 중복 `signal_id` 거부
- 미체결 limit 주문 자동 취소
- 체결된 경우에만 DB 포지션 생성
- 손절/익절 reduce-only 주문 생성
- 수동 청산 시 남은 조건부 주문 취소
- 하루 손실 제한 작동
- Telegram 에러 알림 도착

실전 전환 기준:

```text
1. Demo에서 최소 2주 이상 운영
2. TradingView, Webhook, Telegram, Binance 주문 흐름이 모바일 확인 기준으로 유지
3. /positions와 Binance 화면 불일치가 없어야 함
4. /logs에 반복 에러가 없어야 함
5. 수동 청산, pause/resume이 정상 작동해야 함
6. Live 전환 시에도 Demo에서 검증한 설정값과 운영 흐름을 유지하되, 실제 자금 규모는 별도로 제한
```

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

## 테스트

```powershell
pytest
```

테스트는 Binance와 Telegram을 mock 처리하므로 실제 API Key 없이 실행됩니다.

## 실전 전 체크리스트

- README와 `.env.example` 기준으로 `.env` 정리
- `WEBHOOK_SECRET` 새로 생성
- Telegram Bot Token 노출 이력 있으면 재발급
- Binance Live API Key에는 출금 권한 없음
- 실전 전 `BINANCE_TESTNET=true`로 최소 2주 이상 Demo를 실전과 동일한 구조로 운영
- TradingView Alert, Webhook URL, Telegram 모바일 알림, Binance 주문 흐름이 Demo와 Live에서 동일
- 고정 HTTPS 주소 사용
- 모바일에서 진입/청산/에러를 확인할 수 있는 상태
- `BINANCE_TESTNET=false` 전환 후 최초에는 소액으로만 검증

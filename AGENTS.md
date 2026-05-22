# Project Operating Rules

이 프로젝트에서는 아래 운영 기준을 우선 적용한다.

1. 연습용 방식은 추천하지 않는다.
   - 임시 URL, 수동 curl 테스트, 일회성 PC 실행을 운영 기준으로 안내하지 않는다.
   - Demo도 실제 운영 전 검증 환경으로 보고 Live와 같은 구조로 설정한다.

2. Demo도 실전과 동일한 환경으로 설정하고 실행한다.
   - Demo와 Live의 차이는 API endpoint, API Key, 실제 자금 여부로 제한한다.
   - TradingView Alert, 고정 HTTPS Webhook URL, Telegram 모바일 알림, 리스크 제한, 주문/청산 흐름은 동일하게 유지한다.

3. 모바일로만 확인 가능하도록 자동매매를 구현한다.
   - 운영 확인은 Telegram 모바일 알림, TradingView 모바일 알림, Binance 모바일 앱 확인을 기준으로 한다.
   - PC 화면을 계속 봐야 하는 방식, 수동 curl 테스트, 매번 바뀌는 ngrok URL 갱신은 운영 기준으로 삼지 않는다.
   - 실전 기준 운영은 고정 HTTPS 주소와 항상 켜져 있는 서버를 전제로 한다.

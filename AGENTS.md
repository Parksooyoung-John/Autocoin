# Project Operating Rules

Use these rules for future work in this project.

## Trading Bot Operations

1. Do not recommend practice-only operating methods.
   - Do not treat temporary URLs, manual curl checks, or one-off local PC runs as the operating baseline.
   - Treat Demo as a production-like verification environment.

2. Demo must match Live structurally.
   - Demo and Live should differ only by API endpoint, API keys, and real-vs-demo funds.
   - TradingView alerts, fixed HTTPS webhook URL, Telegram mobile alerts, risk controls, and order/exit flow must remain the same.

3. The bot should be monitorable from mobile only.
   - Use Telegram mobile alerts, TradingView mobile alerts, Binance mobile app, and mobile browser health checks as the operating baseline.
   - Do not rely on keeping a PC screen open, manual curl tests, or rotating ngrok URLs.
   - Real operation assumes a fixed HTTPS URL and an always-on server.

## TradingView Pine Strategy Notes

1. Demo orders use the TradingView `indicator()` alert script, not the `strategy()` backtest script.
   - `strategy()` is for backtesting and parameter comparison only.
   - Demo/Live webhook operation must use `indicator()` with `alert()` JSON payloads.

2. Current Demo operating focus:
   - Use v5-LONG results as the current strategy reference.
   - Main allocation: `XRPUSDT` 4H LONG only, 50~60%.
   - Secondary allocation: `BTCUSDT` 1D LONG only, 40~50%.
   - `ETHUSDT` is excluded from default bot-supported symbols and Demo alerts until risk-adjusted results improve.
   - Server `.env` should use `SYMBOL_WEIGHTS=BTCUSDT:0.4,XRPUSDT:0.6`.

3. Current ATR stop setting:
   - ATR stop multiplier was changed from `2.0` to `2.5`.
   - Long stop basis: `entryPrice - (ATR * 2.5)`.
   - Server `.env` should use `ATR_STOP_MULTIPLIER=2.5`.
   - This is intended to reduce premature stop-outs in swing trades, while accepting wider stop distance and smaller risk-adjusted position size on the bot side.

4. Webhook compatibility:
   - Keep `signal` values as `ENTRY` and `EXIT` for the current FastAPI bot.
   - Use extra fields such as `exitType: EXIT_PARTIAL` or `exitType: EXIT_FULL` only as metadata unless the server is explicitly extended to process them.

## Make.com Content Automation

1. Do not mark a Make scenario as successful only because modules show green checks.
   - Confirm the final Notion page exists in the intended database.
   - Confirm the Notion page title, body, description, hashtags, and any generated asset links are actually visible in Notion.
   - Confirm ElevenLabs generated audio uses the cleaned TTS script, not the raw Claude response.

2. Keep three separate text versions in the scenario.
   - `raw_claude_text`: full Claude API output.
   - `notion_text`: formatted text for Notion, preserving sections and paragraphs.
   - `tts_text`: narration-only text for ElevenLabs, with headings, markdown, numbering noise, hashtags, and `null` removed.

3. Do not send raw Claude output directly to ElevenLabs.
   - Remove markdown headers, title candidates, thumbnail candidates, description, hashtags, separators, and literal `null`.
   - Preserve sentence breaks naturally.
   - Apply pronunciation normalization before ElevenLabs.

4. For Korean TTS pronunciation, use explicit normalization.
   - If ElevenLabs pronounces Korean names incorrectly, use a TTS-only phonetic replacement after testing.
   - Keep the original spelling in Notion text if desired; only change the TTS text.

5. Prefer stable section markers in Claude output.
   - Use markers such as `[TITLE]`, `[THUMBNAIL]`, `[SCRIPT]`, `[DESCRIPTION]`, `[HASHTAGS]`, and `[TTS_SCRIPT]`.
   - Avoid relying on loose markdown headings when parsing.

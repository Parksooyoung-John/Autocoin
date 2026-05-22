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
   - Apply pronunciation normalization before ElevenLabs, including Napoleon-related replacements if needed.

4. For Korean TTS pronunciation, use explicit normalization.
   - If ElevenLabs pronounces `나폴레옹` incorrectly as `나폴롱`, use a TTS-only replacement such as `나폴레온` or another tested phonetic spelling.
   - Keep the original spelling in Notion text if desired; only change the TTS text.

5. Prefer stable section markers in Claude output.
   - Use markers such as `[TITLE]`, `[THUMBNAIL]`, `[SCRIPT]`, `[DESCRIPTION]`, `[HASHTAGS]`, and `[TTS_SCRIPT]`.
   - Avoid relying on loose Korean markdown headings like `# 제목 후보 5개` when parsing.

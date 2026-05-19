"""
TradingView owns strategy calculation for this project.

The bot intentionally does not recalculate EMA/RSI/ATR/volume conditions. It
validates risk and execution safety after TradingView sends an ENTRY or EXIT
webhook.
"""

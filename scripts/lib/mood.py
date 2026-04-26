#!/usr/bin/env python3
"""Wave Surf — BTC mood checker. Returns market context for LONG/SHORT bots."""
from .api import fetch_json
import sys

BTC_MOOD_CRASH_THRESHOLD = -2.0
BTC_MOOD_BAD_THRESHOLD = -1.0
BTC_1H_CANDLES_TO_CHECK = 4


def check(bot_type="long"):
    """
    Check BTC 1h candles for market mood.
    bot_type="long" or "short" — flips logic for SHORT.
    Returns dict with btc_price, 4h_change_pct, mood, penalty, hard_block.
    """
    try:
        url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=5"
        data = fetch_json(url)
        if len(data) < 2:
            return {"btc_price": None, "4h_change_pct": 0, "mood": "unknown",
                    "penalty": 0, "hard_block": False, "hard_block_short": False}

        now_price = float(data[-1][4])
        candle_open_4h_ago = float(data[-min(len(data), BTC_1H_CANDLES_TO_CHECK + 1)][1])
        change_pct = (now_price - candle_open_4h_ago) / candle_open_4h_ago * 100

        if bot_type == "long":
            return _check_long(now_price, change_pct, data)
        else:
            return _check_short(now_price, change_pct, data)

    except Exception:
        return {"btc_price": None, "4h_change_pct": 0, "mood": "unknown",
                "penalty": 0, "hard_block": False, "hard_block_short": False}


def _check_long(now_price, change_pct, data):
    mood = "neutral"
    penalty = 0
    hard_block = False

    if change_pct <= BTC_MOOD_CRASH_THRESHOLD:
        mood = "crash"
        hard_block = True
        penalty = -50
    elif change_pct <= BTC_MOOD_BAD_THRESHOLD:
        mood = "bearish"
        penalty = -30
    elif change_pct > 0:
        mood = "bullish"

    red_candles = sum(1 for k in data[-BTC_1H_CANDLES_TO_CHECK:] if float(k[4]) < float(k[1]))
    if red_candles >= 3:
        mood = "slipping"
        penalty = max(penalty, -20)
        if red_candles == 4:
            mood = "freefall"
            hard_block = True
            penalty = -50

    return {
        "btc_price": round(now_price, 1),
        "4h_change_pct": round(change_pct, 2),
        "mood": mood,
        "penalty": penalty,
        "hard_block": hard_block,
        "hard_block_short": False,
        "red_candles_out_of_4": red_candles,
    }


def _check_short(now_price, change_pct, data):
    mood = "neutral"
    penalty = 0
    hard_block_short = False

    # SHORT: bullish BTC = bad for shorts
    if change_pct >= abs(BTC_MOOD_CRASH_THRESHOLD):
        mood = "strongly_bullish"
        hard_block_short = True
        penalty = -50
    elif change_pct >= 1.0:
        mood = "bullish"
        penalty = -30
    elif change_pct <= -1.0:
        mood = "bearish"  # good for shorts — no penalty
    elif change_pct <= -2.0:
        mood = "crashing"  # great for shorts

    green_candles = sum(1 for k in data[-BTC_1H_CANDLES_TO_CHECK:] if float(k[4]) > float(k[1]))
    if green_candles >= 3:
        penalty = max(penalty, -30)
        if green_candles == 4:
            mood = "bullish_avalanche"
            hard_block_short = True
            penalty = -50

    return {
        "btc_price": round(now_price, 1),
        "4h_change_pct": round(change_pct, 2),
        "mood": mood,
        "penalty": penalty,
        "hard_block": False,
        "hard_block_short": hard_block_short,
        "green_candles_out_of_4": green_candles,
    }

#!/usr/bin/env python3
"""Wave Surf — shared API helpers for Binance."""
import json, sys, time
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import quote

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_DIR / "data"
API_TIMEOUT = 10

EXCLUDED_SYMBOLS = {
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "DAIUSDT", "BUSDUSDT", "USDPUSDT",
}
LEVERAGED_PATTERNS = ["UP", "DOWN", "BULL", "BEAR", "BKRW",
                       "3L", "3S", "2L", "2S", "5L", "5S"]

_TRADABLE_SET = None


def fetch_json(url, timeout=API_TIMEOUT):
    with urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read())


def get_tradable_usdt_pairs():
    global _TRADABLE_SET
    if _TRADABLE_SET is not None:
        return _TRADABLE_SET
    try:
        info = fetch_json("https://api.binance.com/api/v3/exchangeInfo", 15)
        bad = {"BREAK", "PAUSE", "HALT"}
        _TRADABLE_SET = {
            s["symbol"] for s in info["symbols"]
            if s["symbol"].endswith("USDT") and s["status"] not in bad
        }
        return _TRADABLE_SET
    except Exception as e:
        print(f"WARNING: exchangeInfo failed ({e})", file=sys.stderr)
        _TRADABLE_SET = set()
        return _TRADABLE_SET


def is_valid_altooin(sym):
    if sym in EXCLUDED_SYMBOLS:
        return False
    for pat in LEVERAGED_PATTERNS:
        if pat in sym:
            return False
    return True


def get_spread_prices(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/bookTicker?symbol={symbol}"
        with urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
            bid = float(data["bidPrice"])
            ask = float(data["askPrice"])
            mid = (bid + ask) / 2
            spread_pct = (ask - bid) / mid * 100 if mid > 0 else 0
            return {"bid": bid, "ask": ask, "mid": mid, "spread_pct": round(spread_pct, 2)}
    except Exception:
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
            with urlopen(url, timeout=10) as resp:
                price = float(json.load(resp)["price"])
                return {"bid": price, "ask": price, "mid": price, "spread_pct": 0}
        except:
            return None


def get_order_book(symbol):
    try:
        url = f"https://api.binance.com/api/v3/depth?symbol={symbol}&limit=10"
        data = fetch_json(url)
        bids = sum(float(p) * float(q) for p, q in data["bids"])
        asks = sum(float(p) * float(q) for p, q in data["asks"])
        return round(bids / asks, 2) if asks > 0 else 1.0
    except Exception:
        return 1.0


def get_trades(symbol):
    try:
        url = f"https://api.binance.com/api/v3/trades?symbol={symbol}&limit=30"
        data = fetch_json(url)
        buy = sum(float(t["qty"]) for t in data if not t["isBuyerMaker"])
        sell = sum(float(t["qty"]) for t in data if t["isBuyerMaker"])
        return round(buy / sell, 2) if sell > 0 else 99.0
    except Exception:
        return 1.0

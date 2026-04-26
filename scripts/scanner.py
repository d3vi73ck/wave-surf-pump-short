#!/usr/bin/env python3
"""
Pump Rider — Scanner v3.1
🎯 Two-layer filtering:
  Layer 1 (1h candles): Quick volume spike + freshness check
  Layer 2 (5m candles): Real-time momentum check — only enter if buying NOW
  Saves order book + trades for Layer 1 passers only.
"""
import json, time
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import quote

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"

# ─── Thresholds ────────────────────────────────────────────────────────────
MAX_BASELINE_DAILY_VOLUME = 1_000_000
MIN_BASELINE_DAILY_VOLUME = 10_000
BASELINE_HOURS = 24
VOLUME_SPIKE_THRESHOLD = 6.0
MAX_PRICE_PUMP_PCT = 10.0
MIN_PRICE_MOVE_PCT = 1.0
MAX_CANDIDATES = 5
MAX_SPIKE_AGE_CANDLES = 1
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
        print(f"WARNING: exchangeInfo failed ({e})", file=__import__('sys').stderr)
        _TRADABLE_SET = set()
        return _TRADABLE_SET


def is_valid_altooin(sym):
    if sym in EXCLUDED_SYMBOLS:
        return False
    for pat in LEVERAGED_PATTERNS:
        if pat in sym:
            return False
    return True


def get_all_usdt_pairs():
    data = fetch_json("https://api.binance.com/api/v3/ticker/24hr")
    tradable = get_tradable_usdt_pairs()
    pairs = []
    for t in data:
        sym = t["symbol"]
        if sym.endswith("USDT") and is_valid_altooin(sym) and sym in tradable:
            try:
                vol = float(t["quoteVolume"])
                if MIN_BASELINE_DAILY_VOLUME <= vol <= MAX_BASELINE_DAILY_VOLUME:
                    pairs.append({
                        "symbol": sym,
                        "price": float(t["lastPrice"]),
                        "volume_24h": vol,
                    })
            except:
                pass
    return pairs


def check_1h_spike(symbol):
    """Check if a coin has a fresh volume spike in 1h candles."""
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={quote(symbol, safe='')}&interval=1h&limit={BASELINE_HOURS + 4}"
        data = fetch_json(url)
        if len(data) < 6:
            return None
        
        # Parse candles
        candles = []
        for k in data:
            candles.append({
                "open": float(k[1]),
                "close": float(k[4]),
                "volume_usd": float(k[5]) * float(k[4]),
            })
        
        # Baseline: exclude last 3 (to not inflate with spike)
        baseline_vols = [c["volume_usd"] for c in candles[:-3]]
        avg_hourly = sum(baseline_vols) / len(baseline_vols) if baseline_vols else 0
        if avg_hourly == 0:
            return None
        
        # Find max spike in last 3 candles
        max_ratio = 0
        spike_idx = -1
        for i in range(len(candles) - 3, len(candles)):
            ratio = candles[i]["volume_usd"] / avg_hourly
            if ratio > max_ratio:
                max_ratio = ratio
                spike_idx = i
        
        latest = candles[-1]
        spike_age = (len(candles) - 1) - spike_idx
        
        # Must have fresh spike
        if max_ratio < VOLUME_SPIKE_THRESHOLD or spike_age > MAX_SPIKE_AGE_CANDLES:
            return None
        
        # Price move in current candle
        pct = (latest["close"] - latest["open"]) / latest["open"] * 100
        if abs(pct) < MIN_PRICE_MOVE_PCT or abs(pct) > MAX_PRICE_PUMP_PCT:
            return None
        
        current_ratio = latest["volume_usd"] / avg_hourly if avg_hourly else 0
        streak = sum(1 for c in candles[-3:] if c["close"] > c["open"])
        
        return {
            "avg_hourly_vol_usd": round(avg_hourly),
            "max_vol_spike_ratio": round(max_ratio, 1),
            "current_vol_ratio": round(current_ratio, 1),
            "spike_age_candles": spike_age,
            "price_change_1h_pct": round(pct, 2),
            "candle_streak": streak,
        }
    except Exception:
        return None


def check_5m_momentum(symbol):
    """Check 5m candles for real-time momentum."""
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={quote(symbol, safe='')}&interval=5m&limit=6"
        data = fetch_json(url)
        if len(data) < 3:
            return None
        
        candles = [{"open": float(k[1]), "close": float(k[4]), "volume_usd": float(k[5]) * float(k[4])} for k in data]
        last, prev = candles[-1], candles[-2]
        
        baseline = sum(c["volume_usd"] for c in candles[:-2]) / max(len(candles) - 2, 1)
        vol_ratio = last["volume_usd"] / baseline if baseline > 0 else 0
        is_green = last["close"] > last["open"]
        streak = sum(1 for c in candles[-3:] if c["close"] > c["open"])
        chg = (last["close"] - last["open"]) / last["open"] * 100
        
        return {
            "last_5m_green": is_green,
            "last_two_5m_green": prev["close"] > prev["open"] and is_green,
            "5m_green_streak": streak,
            "5m_vol_ratio": round(vol_ratio, 1),
            "5m_price_change_pct": round(chg, 2),
        }
    except Exception:
        return None


def get_order_book(symbol):
    try:
        url = f"https://api.binance.com/api/v3/depth?symbol={quote(symbol, safe='')}&limit=10"
        data = fetch_json(url)
        bids = sum(float(p) * float(q) for p, q in data["bids"])
        asks = sum(float(p) * float(q) for p, q in data["asks"])
        return round(bids / asks, 2) if asks > 0 else 1.0
    except Exception:
        return 1.0


def get_trades(symbol):
    try:
        url = f"https://api.binance.com/api/v3/trades?symbol={quote(symbol, safe='')}&limit=30"
        data = fetch_json(url)
        buy = sum(float(t["qty"]) for t in data if not t["isBuyerMaker"])
        sell = sum(float(t["qty"]) for t in data if t["isBuyerMaker"])
        return round(buy / sell, 2) if sell > 0 else 99.0
    except Exception:
        return 1.0


def score_candidate(coin, spike, order_book_ratio, buy_sell_ratio, m5):
    """Score a candidate based on all signals."""
    score = 0
    
    # Volume spike (up to 40)
    vr = spike["max_vol_spike_ratio"]
    if vr >= 50: score += 40
    elif vr >= 30: score += 35
    elif vr >= 20: score += 30
    elif vr >= 10: score += 20
    else: score += 10
    
    # Tiny baseline bonus
    if coin["volume_24h"] < 50000 and vr > 20: score += 10
    
    # Fresh spike bonus
    if spike["spike_age_candles"] == 0: score += 10
    
    # 5m momentum bonus (active buying NOW)
    if m5 and m5["last_5m_green"] and m5["5m_vol_ratio"] > 1.5: score += 10
    
    # Price action (up to 25)
    if spike["price_change_1h_pct"] > 0:
        score += 15
        if spike["candle_streak"] >= 2: score += 10
    
    # Order book (up to 15)
    if order_book_ratio > 0.8: score += 15
    elif order_book_ratio > 0.5: score += 5
    
    # Trade flow (up to 20)
    if buy_sell_ratio > 2.0: score += 20
    elif buy_sell_ratio > 1.2: score += 10
    
    # Penalties
    if spike["price_change_1h_pct"] > 6: score -= 10
    if spike["price_change_1h_pct"] < 0 and vr > 10: score -= 15
    if order_book_ratio < 0.3: score -= 20
    if spike["price_change_1h_pct"] < -3: score -= 15
    
    # ⭐ v3.1: 5m hard caps
    if m5:
        if not m5["last_5m_green"] and m5["5m_green_streak"] < 1:
            score = min(score, 40)  # Below 50 threshold
        if m5["5m_price_change_pct"] < -1.5:
            score = min(score, 40)
    
    return score


def scan():
    result = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidates": [],
        "scanned_count": 0,
        "strategy": "v3_1_fresh_spike_5m",
    }
    
    all_pairs = get_all_usdt_pairs()[:100]  # Top 100 by 24h vol
    result["scanned_count"] = len(all_pairs)
    
    # ── Layer 1: Quick 1h spike filter ──────────────────────────────────
    layer1_passers = []
    for coin in all_pairs:
        spike = check_1h_spike(coin["symbol"])
        if spike:
            layer1_passers.append((coin, spike))
    
    # ── Layer 2: Deep dive on passers (max 15 to keep fast) ──────────────
    for coin, spike in layer1_passers[:15]:
        sym = coin["symbol"]
        order_book_ratio = get_order_book(sym)
        buy_sell_ratio = get_trades(sym)
        m5 = check_5m_momentum(sym)
        
        score = score_candidate(coin, spike, order_book_ratio, buy_sell_ratio, m5)
        
        candidate = {
            "symbol": sym,
            "price": round(coin["price"], 8),
            "volume_24h_usd": round(coin["volume_24h"]),
            "max_vol_spike_ratio": spike["max_vol_spike_ratio"],
            "current_vol_ratio": spike["current_vol_ratio"],
            "spike_age_candles": spike["spike_age_candles"],
            "price_change_1h_pct": spike["price_change_1h_pct"],
            "candle_streak": spike["candle_streak"],
            "score": score,
            "5m_momentum": m5,
            "order_book_ratio": order_book_ratio,
            "buy_sell_ratio": buy_sell_ratio,
        }
        result["candidates"].append(candidate)
    
    result["candidates"].sort(key=lambda c: c["score"], reverse=True)
    result["candidates"] = result["candidates"][:MAX_CANDIDATES]
    
    now = time.gmtime()
    result["weekend_mode"] = now.tm_wday >= 5
    result["note"] = "Weekend mode" if now.tm_wday >= 5 else "Regular session"
    
    with open(DATA_DIR / "scan_latest.json", "w") as f:
        json.dump(result, f, indent=2)
    return result


if __name__ == "__main__":
    print(json.dumps(scan(), indent=2))

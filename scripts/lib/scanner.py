#!/usr/bin/env python3
"""Wave Surf — Scanner + scorer for volume spikes (LONG and SHORT versions)."""
from .api import fetch_json, get_order_book, get_trades, get_tradable_usdt_pairs, is_valid_altooin, get_spread_prices
import sys

# ─── Constants ─────────────────────────────────────────────────────────
MAX_BASELINE_DAILY_VOLUME = 1_000_000
MIN_BASELINE_DAILY_VOLUME = 10_000
BASELINE_HOURS = 24
VOLUME_SPIKE_THRESHOLD = 6.0  # LONG: spike > 6x
VOLUME_DUMP_THRESHOLD = 5.0   # SHORT: spike > 5x (dump needs less)
MAX_PRICE_PUMP_PCT = 10.0
MIN_PRICE_MOVE_PCT = 1.0
MAX_CANDIDATES = 5
MAX_SPIKE_AGE_CANDLES = 1
API_TIMEOUT = 10


# ─── Candles ───────────────────────────────────────────────────────────

def check_1h_spike(symbol):
    """Check 1h candle for volume spike (LONG version: price up)."""
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit={BASELINE_HOURS + 4}"
        data = fetch_json(url)
        if len(data) < 6:
            return None
        candles = []
        for k in data:
            candles.append({
                "open": float(k[1]), "close": float(k[4]),
                "volume_usd": float(k[5]) * float(k[4]),
            })
        baseline_vols = [c["volume_usd"] for c in candles[:-3]]
        avg_hourly = sum(baseline_vols) / len(baseline_vols) if baseline_vols else 0
        if avg_hourly == 0:
            return None
        max_ratio = 0
        spike_idx = -1
        for i in range(len(candles) - 3, len(candles)):
            ratio = candles[i]["volume_usd"] / avg_hourly
            if ratio > max_ratio:
                max_ratio = ratio
                spike_idx = i
        latest = candles[-1]
        spike_age = (len(candles) - 1) - spike_idx
        if max_ratio < VOLUME_SPIKE_THRESHOLD or spike_age > MAX_SPIKE_AGE_CANDLES:
            return None
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
    """Check last 5m candles for momentum."""
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit=6"
        data = fetch_json(url)
        if len(data) < 3:
            return None
        candles = [{"open": float(k[1]), "close": float(k[4]),
                    "volume_usd": float(k[5]) * float(k[4])} for k in data]
        last, prev = candles[-1], candles[-2]
        baseline = sum(c["volume_usd"] for c in candles[:-2]) / max(len(candles) - 2, 1)
        vol_ratio = last["volume_usd"] / baseline if baseline > 0 else 0
        return {
            "last_5m_green": last["close"] > last["open"],
            "last_two_5m_green": prev["close"] > prev["open"] and last["close"] > last["open"],
            "5m_green_streak": sum(1 for c in candles[-3:] if c["close"] > c["open"]),
            "5m_vol_ratio": round(vol_ratio, 1),
            "5m_price_change_pct": round((last["close"] - last["open"]) / last["open"] * 100, 2),
        }
    except Exception:
        return None


# ─── Scanners ──────────────────────────────────────────────────────────

def get_all_usdt_pairs(max_pairs=100):
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
    return pairs[:max_pairs]


def score_long(coin, spike, order_book_ratio, buy_sell_ratio, m5):
    """Score a candidate for LONG entry (pump catching)."""
    score = 0
    vr = spike["max_vol_spike_ratio"]
    if vr >= 50: score += 40
    elif vr >= 30: score += 35
    elif vr >= 20: score += 30
    elif vr >= 10: score += 20
    else: score += 10
    if coin["volume_24h"] < 50000 and vr > 20: score += 10
    if spike["spike_age_candles"] == 0: score += 10
    if m5 and m5["last_5m_green"] and m5["5m_vol_ratio"] > 1.5: score += 10
    if spike["price_change_1h_pct"] > 0:
        score += 15
        if spike["candle_streak"] >= 2: score += 10
    if order_book_ratio > 0.8: score += 15
    elif order_book_ratio > 0.5: score += 5
    if buy_sell_ratio > 2.0: score += 20
    elif buy_sell_ratio > 1.2: score += 10
    # Penalties
    if spike["price_change_1h_pct"] > 6: score -= 10
    if spike["price_change_1h_pct"] < 0 and vr > 10: score -= 15
    if order_book_ratio < 0.3: score -= 20
    if spike["price_change_1h_pct"] < -3: score -= 15
    if m5:
        if not m5["last_5m_green"] and m5["5m_green_streak"] < 1:
            score = min(score, 40)
        if m5["5m_price_change_pct"] < -1.5:
            score = min(score, 40)
    return score


def score_short(coin, spike, order_book_ratio, buy_sell_ratio, m5):
    """Score a candidate for SHORT entry (dump catching, inverse logic)."""
    score = 0
    vr = spike["max_vol_spike_ratio"]
    # Volume spike (already pumped = ready to dump)
    if vr >= 30: score += 40
    elif vr >= 20: score += 35
    elif vr >= 10: score += 25
    else: score += 15
    # Short rewards momentum downturn
    if m5:
        if not m5["last_5m_green"]: score += 15
        if m5["5m_green_streak"] <= 1: score += 10
        if m5["5m_price_change_pct"] < 0: score += 10
    # Low buy/sell = sellers dominating (good for short)
    if buy_sell_ratio < 0.8: score += 20
    elif buy_sell_ratio < 1.0: score += 10
    else: score -= 10
    # Order book imbalance: more asks = downward pressure
    if order_book_ratio < 0.8: score += 10
    elif order_book_ratio > 1.5: score -= 15
    # Price already pumped significantly = more likely to dump
    if spike["price_change_1h_pct"] > 3: score += 10
    # Small cap bonus
    if coin["volume_24h"] < 50000 and vr > 15: score += 10
    # Fresh spike = good timing
    if spike["spike_age_candles"] == 0: score += 5
    # Penalties
    if m5 and m5["last_5m_green"] and m5["5m_vol_ratio"] > 2:
        score = min(score, 40)  # strong green momentum = squeeze risk
    if buy_sell_ratio > 1.5 and order_book_ratio > 1.2:
        score = max(score - 20, 0)  # buy walls = price won't dump
    if spike["price_change_1h_pct"] > 8:
        score -= 10  # too extended, might already have dumped
    return max(score, 0)


def run_long_scanner(max_pairs=100):
    """Scan for LONG entry candidates."""
    all_pairs = get_all_usdt_pairs(max_pairs)
    layer1 = []
    for coin in all_pairs:
        spike = check_1h_spike(coin["symbol"])
        if spike:
            layer1.append((coin, spike))
    candidates = []
    for coin, spike in layer1[:15]:
        sym = coin["symbol"]
        ob = get_order_book(sym)
        bs = get_trades(sym)
        m5 = check_5m_momentum(sym)
        sc = score_long(coin, spike, ob, bs, m5)
        candidates.append({
            "symbol": sym,
            "price": round(coin["price"], 8),
            "volume_24h_usd": round(coin["volume_24h"]),
            "score": sc,
            "max_vol_spike_ratio": spike["max_vol_spike_ratio"],
            "price_change_1h_pct": spike["price_change_1h_pct"],
            "buy_sell_ratio": bs,
            "order_book_ratio": ob,
            "5m_momentum": m5,
        })
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:MAX_CANDIDATES]


def run_short_scanner(max_pairs=100):
    """Scan for SHORT entry candidates (dump after pump)."""
    all_pairs = get_all_usdt_pairs(max_pairs)
    layer1 = []
    for coin in all_pairs:
        spike = check_1h_spike(coin["symbol"])
        if spike:
            layer1.append((coin, spike))
    candidates = []
    for coin, spike in layer1[:15]:
        sym = coin["symbol"]
        ob = get_order_book(sym)
        bs = get_trades(sym)
        m5 = check_5m_momentum(sym)
        sc = score_short(coin, spike, ob, bs, m5)
        candidates.append({
            "symbol": sym,
            "price": round(coin["price"], 8),
            "volume_24h_usd": round(coin["volume_24h"]),
            "score": sc,
            "max_vol_spike_ratio": spike["max_vol_spike_ratio"],
            "price_change_1h_pct": spike["price_change_1h_pct"],
            "buy_sell_ratio": bs,
            "order_book_ratio": ob,
            "5m_momentum": m5,
        })
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:MAX_CANDIDATES]

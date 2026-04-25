#!/usr/bin/env python3
"""
Pump Rider — Scanner
Scans Binance altcoins for volume spikes (early pump detection).
"""
import json, time, math
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import quote

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"

# Coins to watch: top ~50 liquid altcoins (USDT pairs, >$1M daily volume typically)
# We'll dynamically filter by volume > $500K daily
MIN_DAILY_VOLUME_USD = 500_000
VOLUME_SPIKE_THRESHOLD = 3.0  # 3x average hourly volume
MAX_PRICE_PUMP_PCT = 8.0  # skip if already pumped >8% in last hour
MIN_PRICE_MOVE_PCT = 0.5  # must be moving at least a little

def get_all_usdt_pairs():
    url = "https://api.binance.com/api/v3/ticker/24hr"
    with urlopen(url) as resp:
        data = json.loads(resp.read())
    pairs = []
    for t in data:
        sym = t["symbol"]
        if (sym.endswith("USDT") and 
            not any(x in sym for x in ["UP", "DOWN", "BULL", "BEAR", "BKRW"])):
            try:
                vol = float(t["quoteVolume"])
                if vol >= MIN_DAILY_VOLUME_USD:
                    pairs.append({
                        "symbol": sym,
                        "price": float(t["lastPrice"]),
                        "volume_24h": vol,
                        "change_24h": float(t["priceChangePercent"]),
                        "high_24h": float(t["highPrice"]),
                        "low_24h": float(t["lowPrice"]),
                    })
            except:
                pass
    return pairs

def get_1h_candles(symbol, limit=25):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={quote(symbol, safe='')}&interval=1h&limit={limit}"
        with urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        candles = []
        for k in data:
            candles.append({
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume_usd": float(k[5]) * float(k[4]),
                "close_time": int(k[6]),
            })
        return candles
    except Exception:
        return []

def get_order_book(symbol, limit=10):
    try:
        url = f"https://api.binance.com/api/v3/depth?symbol={quote(symbol, safe='')}&limit={limit}"
        with urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        bids = sum(float(p) * float(q) for p, q in data["bids"])
        asks = sum(float(p) * float(q) for p, q in data["asks"])
        ratio = bids / asks if asks > 0 else 1
        return {"bid_depth_usd": bids, "ask_depth_usd": asks, "bid_ask_ratio": ratio}
    except Exception:
        return {"bid_depth_usd": 0, "ask_depth_usd": 0, "bid_ask_ratio": 1.0}

def get_recent_trades(symbol, limit=30):
    try:
        url = f"https://api.binance.com/api/v3/trades?symbol={quote(symbol, safe='')}&limit={limit}"
        with urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        buy_vol = sum(float(t["qty"]) for t in data if not t["isBuyerMaker"])
        sell_vol = sum(float(t["qty"]) for t in data if t["isBuyerMaker"])
        total_vol = buy_vol + sell_vol
        return {
            "buy_volume": buy_vol,
            "sell_volume": sell_vol,
            "buy_sell_ratio": buy_vol / sell_vol if sell_vol > 0 else 99,
            "trades_count": len(data),
        }
    except Exception:
        return {"buy_volume": 0, "sell_volume": 0, "buy_sell_ratio": 1.0, "trades_count": 0}

def scan():
    """Main scan: find coins with volume spikes."""
    result = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidates": [],
        "scanned_count": 0,
    }
    
    coins = get_all_usdt_pairs()
    result["scanned_count"] = len(coins)
    
    for coin in coins:
        sym = coin["symbol"]
        
        # Get 1h candles for volume comparison
        candles = get_1h_candles(sym)
        if len(candles) < 3:
            continue
        
        volumes = [c["volume_usd"] for c in candles]
        avg_hourly_vol = sum(volumes[:-1]) / (len(volumes) - 1)  # exclude current candle
        latest_vol = volumes[-1]
        
        if avg_hourly_vol == 0:
            continue
        
        vol_ratio = latest_vol / avg_hourly_vol
        
        # Skip if volume isn't spiking enough
        if vol_ratio < VOLUME_SPIKE_THRESHOLD:
            continue
        
        # Check price move (is it actually pumping or just high volume sideways?)
        last_3 = candles[-3:]
        price_change_1h = (candles[-1]["close"] - candles[0]["open"]) / candles[0]["open"] * 100
        candle_streak = sum(1 for c in last_3 if c["close"] > c["open"])
        
        # Skip if already pumped too much
        if price_change_1h > MAX_PRICE_PUMP_PCT:
            continue
        
        # Skip if barely moving
        if abs(price_change_1h) < MIN_PRICE_MOVE_PCT:
            continue
        
        # Get order book + trades for deeper check
        order_book = get_order_book(sym)
        trades = get_recent_trades(sym)
        
        candidate = {
            "symbol": sym,
            "price": coin["price"],
            "volume_ratio": round(vol_ratio, 1),
            "price_change_1h_pct": round(price_change_1h, 2),
            "candle_streak": candle_streak,
            "order_book": order_book,
            "trades": trades,
            "score": 0,  # will compute below
        }
        
        # Scoring system
        score = 0
        # Volume spike intensity
        if vol_ratio >= 5: score += 30
        elif vol_ratio >= 3: score += 20
        
        # Price direction (positive = pumping)
        if price_change_1h > 0: score += 20
        if candle_streak >= 2: score += 15  # consecutive green
        
        # Order book health (needs bid support)
        if order_book["bid_ask_ratio"] > 0.8: score += 15
        elif order_book["bid_ask_ratio"] > 0.5: score += 5
        
        # Trade flow (buy pressure)
        if trades["buy_sell_ratio"] > 1.2: score += 20
        elif trades["buy_sell_ratio"] > 1.0: score += 10
        
        # Penalty for being too late
        if price_change_1h > 5: score -= 10
        if order_book["bid_ask_ratio"] < 0.3: score -= 20  # trap
        
        candidate["score"] = score
        result["candidates"].append(candidate)
    
    # Sort by score descending
    result["candidates"].sort(key=lambda c: c["score"], reverse=True)
    
    # Keep top 5
    result["candidates"] = result["candidates"][:5]
    
    print(json.dumps(result, indent=2))
    (DATA_DIR / "scan_latest.json").write_text(json.dumps(result, indent=2))
    return result

if __name__ == "__main__":
    scan()

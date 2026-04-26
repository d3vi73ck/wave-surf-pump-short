#!/usr/bin/env python3
"""
Wave Surf Pump SHORT — Trader v1
=================================
Inverse du bot LONG. Mise sur la DESCENTE après un pump.
Mêmes features v4: rescann, switch, stagnation exit, partial TP, BTC mood.
Ajoute: signals partagés avec le bot LONG pour coordination.
"""
import json, time, sys
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import quote

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"

# ─── Constants ─────────────────────────────────────────────────────────────
MIN_SCORE_TO_TRADE = 50        # minimum candidate score to enter
BINANCE_MAKER_FEE = 0.001
BINANCE_TAKER_FEE = 0.001

SWITCH_SCORE_THRESHOLD = 20
STAGNATION_MIN_ELAPSED = 3600
STAGNATION_BAND = 1.0
PARTIAL_TP_PCT = 2.5           # for SHORT: when price drops 2.5%
MAX_HOLD_SECONDS = 7200

# ─── Shared signals path (bots talk through this) ──────────────────────────
SHARED_SIGNALS_PATH = Path("/home/valkenor/Desktop/repo/wave-surf-pump/data/shared_signals.json")

# ─── BTC mood filter ──────────────────────────────────────────────────────
BTC_MOOD_CRASH_THRESHOLD = -2.0  # for SHORT: bearish BTC = good for shorts
BTC_MOOD_BAD_THRESHOLD = -1.0
BTC_1H_CANDLES_TO_CHECK = 4

# ─── Scanner thresholds ──────────────────────────────────────────────────
MAX_BASELINE_DAILY_VOLUME = 1_000_000
MIN_BASELINE_DAILY_VOLUME = 10_000
BASELINE_HOURS = 24
VOLUME_SPIKE_THRESHOLD = 6.0
MAX_PRICE_PUMP_PCT = 10.0
MIN_PRICE_MOVE_PCT = 1.0
MAX_CANDIDATES = 5
MAX_SPIKE_AGE_CANDLES = 1
EXCLUDED_SYMBOLS = {
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "DAIUSDT", "BUSDUSDT", "USDPUSDT",
}
LEVERAGED_PATTERNS = ["UP", "DOWN", "BULL", "BEAR", "BKRW",
                       "3L", "3S", "2L", "2S", "5L", "5S"]
API_TIMEOUT = 10

_TRADABLE_SET = None

# ─── API helpers (same as scanner) ────────────────────────────────────

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


def check_1h_spike(symbol):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={quote(symbol, safe='')}&interval=1h&limit={BASELINE_HOURS + 4}"
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
            "candle_streak": streak,  # SHORT: high streak = pumped already = ready to dump
        }
    except Exception:
        return None


def check_5m_momentum(symbol):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={quote(symbol, safe='')}&interval=5m&limit=6"
        data = fetch_json(url)
        if len(data) < 3:
            return None
        candles = [{"open": float(k[1]), "close": float(k[4]), "volume_usd": float(k[5]) * float(k[4])} for k in data]
        last, prev = candles[-1], candles[-2]
        baseline = sum(c["volume_usd"] for c in candles[:-2]) / max(len(candles) - 2, 1)
        vol_ratio = last["volume_usd"] / baseline if baseline > 0 else 0
        return {
            "last_5m_green": last["close"] > last["open"],  # SHORT: want RED (false)
            "last_two_5m_green": prev["close"] > prev["open"] and last["close"] > last["open"],
            "5m_green_streak": sum(1 for c in candles[-3:] if c["close"] > c["open"]),
            "5m_vol_ratio": round(vol_ratio, 1),
            "5m_price_change_pct": round((last["close"] - last["open"]) / last["open"] * 100, 2),
        }
    except Exception:
        return None


def get_order_book(symbol):
    """SHORT: wants ASK > BID (more sellers than buyers) = OB < 1"""
    try:
        url = f"https://api.binance.com/api/v3/depth?symbol={quote(symbol, safe='')}&limit=10"
        data = fetch_json(url)
        bids = sum(float(p) * float(q) for p, q in data["bids"])
        asks = sum(float(p) * float(q) for p, q in data["asks"])
        return round(bids / asks, 2) if asks > 0 else 1.0
    except Exception:
        return 1.0


def get_trades(symbol):
    """SHORT: wants SELLERS > buyers = b/s < 1"""
    try:
        url = f"https://api.binance.com/api/v3/trades?symbol={quote(symbol, safe='')}&limit=30"
        data = fetch_json(url)
        buy = sum(float(t["qty"]) for t in data if not t["isBuyerMaker"])
        sell = sum(float(t["qty"]) for t in data if t["isBuyerMaker"])
        return round(buy / sell, 2) if sell > 0 else 99.0
    except Exception:
        return 1.0


# ─── Scoring: INVERTED for SHORT ───────────────────────────────────────

def score_candidate(coin, spike, order_book_ratio, buy_sell_ratio, m5):
    """
    SHORT scoring:
    - High score = high chance of DUMP imminent
    - Rewards: high spike ratio (pumped a lot), red 5m candles, sellers dominating
    """
    score = 0

    # Volume spike = it pumped (up to 30)
    vr = spike["max_vol_spike_ratio"]
    if vr >= 50: score += 30
    elif vr >= 30: score += 25
    elif vr >= 20: score += 20
    elif vr >= 10: score += 15
    else: score += 5

    # Already pumped in current candle (up to 20)
    if spike["price_change_1h_pct"] > 0:
        score += 15  # SHORT: green on 1h = has pumped = ready to dump
        if spike["candle_streak"] >= 3:
            score += 15  # long streak = overextended
        elif spike["candle_streak"] >= 2:
            score += 10
        score += min(spike["price_change_1h_pct"] * 2, 10)  # +20 for +10% pump
    else:
        # Price is already falling — closer to dump
        score += 5

    # ⭐ 5m momentum: SHORT wants RED candles (dump starting)
    if m5:
        if not m5["last_5m_green"]:
            score += 15  # last candle red = dumping NOW
            if m5["5m_vol_ratio"] > 1.5:
                score += 10  # volume on the red candle = heavy selling
        if m5["5m_green_streak"] == 0:
            score += 10  # all last 3 candles red = confirmed dump
        if m5["5m_price_change_pct"] < -1:
            score += 15  # big red 5m candle

    # Order book: SHORT wants sellers > buyers = OB < 1.0
    if order_book_ratio < 0.5:
        score += 20  # HEAVY sell wall
    elif order_book_ratio < 0.8:
        score += 10
    elif order_book_ratio > 1.5:
        score -= 10  # buy wall = dangerous to short

    # Trade flow: SHORT wants b/s < 1 (more sellers)
    if buy_sell_ratio < 0.5:
        score += 20
    elif buy_sell_ratio < 0.8:
        score += 15
    elif buy_sell_ratio < 1.0:
        score += 10
    elif buy_sell_ratio > 2.0:
        score -= 15  # heavy buying = short squeeze risk

    # Penalties: don't short something that's still pumping hard
    if spike["price_change_1h_pct"] < 0:
        score -= 10  # already dumping, might be too late
    if m5 and m5["last_5m_green"] and m5["5m_vol_ratio"] > 2:
        score -= 20  # still pumping with volume = short squeeze incoming

    # ⭐ 5m hard caps for SHORT
    if m5:
        # If 5m is strongly green, it's too dangerous to short
        if m5["last_5m_green"] and m5["5m_price_change_pct"] > 2:
            score = min(score, 40)  # below threshold
        # If volume is dead, there's no dump momentum yet
        if m5["5m_vol_ratio"] < 0.3:
            score -= 10

    return score


def run_scanner():
    """Self-contained scan, returns sorted candidates list."""
    all_pairs = get_all_usdt_pairs(100)
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
        sc = score_candidate(coin, spike, ob, bs, m5)
        candidates.append({
            "symbol": sym,
            "price": round(coin["price"], 8),
            "volume_24h_usd": round(coin["volume_24h"]),
            "score": sc,
            "max_vol_spike_ratio": spike["max_vol_spike_ratio"],
            "price_change_1h_pct": spike["price_change_1h_pct"],
            "price_change_current_1h": spike["price_change_1h_pct"],
            "buy_sell_ratio": bs,
            "order_book_ratio": ob,
            "5m_momentum": m5,
        })
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:MAX_CANDIDATES]


def apply_btc_penalty(candidates, btc_mood):
    """
    BTC mood filter for SHORT:
    - Strong BTC = bad for shorts (everything pumps)
    - Weak BTC = good for shorts (everything dumps)
    """
    if not candidates:
        return candidates
    # For SHORT: hard block = BTC is STRONGLY BULLISH (opposite of LONG bot)
    if btc_mood.get("hard_block_short"):
        return []
    if btc_mood["penalty"] != 0:
        for c in candidates:
            c["score"] = max(0, c["score"] + btc_mood["penalty"])
        candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates


# ─── Price helpers ─────────────────────────────────────────────────────

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


def compute_pnl(ap, prices):
    """
    SHORT PnL: sell high (bid), buy back low (ask).
    Entry price = bid (we sold at bid).
    Exit price = ask (we buy back at ask).
    """
    if not prices:
        return None, 0

    # SHORT: entered by selling at bid, exits by buying at ask
    entry_sell_price = ap.get("entry_bid_price", ap["entry_price"])
    exit_buy_price = prices["ask"]

    # If we went SHORT: profit if exit < entry
    raw_pnl_pct = (entry_sell_price - exit_buy_price) / entry_sell_price * 100

    fee_pct = (BINANCE_MAKER_FEE + BINANCE_TAKER_FEE) * 100
    pnl_pct = raw_pnl_pct - fee_pct

    # Mid-based reference for trailing
    mid_pnl = (ap["entry_price"] - prices["mid"]) / ap["entry_price"] * 100

    return pnl_pct, mid_pnl


# ─── BTC mood ──────────────────────────────────────────────────────────

def check_btc_mood():
    """BTC mood check for SHORT — inverted logic."""
    try:
        url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=5"
        data = fetch_json(url)
        if len(data) < 2:
            return {"btc_price": None, "4h_change_pct": 0, "mood": "unknown", "penalty": 0, "hard_block_short": False}

        now_price = float(data[-1][4])
        candle_open_4h_ago = float(data[-min(len(data), BTC_1H_CANDLES_TO_CHECK + 1)][1])
        change_pct = (now_price - candle_open_4h_ago) / candle_open_4h_ago * 100

        mood = "neutral"
        penalty = 0
        hard_block_short = False

        # SHORT: bullish BTC = bad for shorts (hard block)
        if change_pct >= abs(BTC_MOOD_CRASH_THRESHOLD):  # +2% or more
            mood = "strongly_bullish"
            hard_block_short = True
            penalty = -50
        elif change_pct >= 1.0:
            mood = "bullish"
            penalty = -30
        elif change_pct <= -1.0:
            mood = "bearish"
            penalty = 0  # good for shorts
        elif change_pct <= -2.0:
            mood = "crashing"
            penalty = 0  # great for shorts

        # Count green 1h candles (bullish momentum = bad for shorts)
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
            "hard_block_short": hard_block_short,
            "green_candles_out_of_4": green_candles,
        }
    except Exception:
        return {"btc_price": None, "4h_change_pct": 0, "mood": "unknown", "penalty": 0, "hard_block_short": False}


# ─── Shared signals ────────────────────────────────────────────────────

def read_shared_signals():
    """Read signals from LONG bot's shared file."""
    if SHARED_SIGNALS_PATH.exists():
        try:
            return json.loads(SHARED_SIGNALS_PATH.read_text())
        except:
            return {"long_position": None, "signals": []}
    return {"long_position": None, "signals": []}


def write_short_signals(state, pos_check, fresh_candidates):
    """Write SHORT signals for the LONG bot to read."""
    ap = state.get("active_position")
    signals = {
        "short_position": {
            "symbol": ap["symbol"] if ap else None,
            "entry_price": ap["entry_price"] if ap else None,
            "pnl_pct": pos_check.get("pnl_pct") if pos_check else None,
            "elapsed_seconds": pos_check.get("elapsed_seconds") if pos_check else None,
        } if ap else None,
        "candidates": [{"symbol": c["symbol"], "score": c["score"]} for c in fresh_candidates[:3]],
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        short_path = PROJECT_DIR / "data" / "shared_signals_short.json"
        short_path.write_text(json.dumps(signals, indent=2))
    except:
        pass


# ─── Decision / Position checks ───────────────────────────────────────

def check_position(state, fresh_candidates):
    """Check SHORT position with exit reasons."""
    ap = state["active_position"]
    prices = get_spread_prices(ap["symbol"])
    if not prices:
        return ({"action": "error", "reason": "price_fetch_failed", "pnl_pct": 0}, None)

    pnl_pct, mid_pnl = compute_pnl(ap, prices)
    if pnl_pct is None:
        return ({"action": "error", "reason": "pnl_calc_failed", "pnl_pct": 0}, None)

    elapsed = time.time() - ap.get("opened_at_unix", 0)
    lowest_price = min(ap.get("lowest_price", ap["entry_price"]), prices["mid"])
    stop_pct = ap.get("stop_pct", -3.0)

    # Tighten stop as profit grows (price dropping)
    if mid_pnl >= 3: stop_pct = -2.0
    elif mid_pnl >= 5: stop_pct = -1.5

    should_exit = False
    reason = ""
    switch_target = None

    # 1) Stop loss (price going up against us)
    if pnl_pct <= stop_pct:
        should_exit = True
        reason = f"stop_loss_{stop_pct}%"

    # 2) Take profit (price dropped enough)
    elif pnl_pct >= 5:
        should_exit = True
        reason = "take_profit_5%"

    # 3) Hard timeout 2h
    elif elapsed > MAX_HOLD_SECONDS:
        should_exit = True
        reason = "time_expired_2h"

    # 4) Stagnation exit
    elif elapsed > STAGNATION_MIN_ELAPSED and abs(pnl_pct) <= STAGNATION_BAND:
        if fresh_candidates and fresh_candidates[0]["score"] >= MIN_SCORE_TO_TRADE:
            current_entry_score = ap.get("entry_score", 0)
            best_new_score = fresh_candidates[0]["score"]
            if best_new_score > current_entry_score + SWITCH_SCORE_THRESHOLD:
                should_exit = True
                reason = f"stagnation_switch_{fresh_candidates[0]['symbol']}_score{best_new_score}_vs_{current_entry_score}"
                switch_target = fresh_candidates[0]
            else:
                should_exit = False
                reason = "stagnation_but_no_better_option"

    # 5) Switch to better candidate
    if not should_exit and fresh_candidates and fresh_candidates[0]["score"] >= MIN_SCORE_TO_TRADE:
        current_entry_score = ap.get("entry_score", 0)
        best_new_score = fresh_candidates[0]["score"]
        if best_new_score > current_entry_score + SWITCH_SCORE_THRESHOLD and pnl_pct < 2:
            should_exit = True
            reason = f"switch_{fresh_candidates[0]['symbol']}_score{best_new_score}_vs_{current_entry_score}"
            switch_target = fresh_candidates[0]

    # 6) Partial TP
    if not should_exit and pnl_pct >= PARTIAL_TP_PCT:
        m5 = check_5m_momentum(ap["symbol"])
        if m5 and m5["last_5m_green"]:
            # Price dropped but last 5m is green (bounce starting) — take gain
            should_exit = True
            reason = f"partial_take_profit_{pnl_pct}%_5m_bounce"

    return ({
        "action": "exit" if should_exit else "hold",
        "reason": reason,
        "bid": prices["bid"],
        "ask": prices["ask"],
        "mid": prices["mid"],
        "spread_pct": prices["spread_pct"],
        "pnl_pct": round(pnl_pct, 2),
        "stop_pct": stop_pct,
        "lowest_price": lowest_price,
        "elapsed_seconds": int(elapsed),
        "entry_score": ap.get("entry_score", 0),
    }, switch_target)


# ─── Close / Open ──────────────────────────────────────────────────────

def close_position(state, pos_check, reason_suffix=""):
    ap = state["active_position"]
    entry = ap["entry_price"]
    exit_price = pos_check["ask"]  # SHORT: buy back at ask
    pnl_pct = pos_check["pnl_pct"]

    state["active_position"] = None
    state["total_trades"] = state.get("total_trades", 0) + 1
    if pnl_pct > 0:
        state["wins"] = state.get("wins", 0) + 1
    else:
        state["losses"] = state.get("losses", 0) + 1

    full_reason = pos_check["reason"] + (f"_{reason_suffix}" if reason_suffix else "")
    trades_path = DATA_DIR / "trades.csv"
    with open(trades_path, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ')},close,{ap['symbol']},{exit_price},{ap.get('entry_price',0)},{pos_check.get('spread_pct',0)},{pnl_pct},{full_reason}\n")

    return {
        "closed": True,
        "symbol": ap["symbol"],
        "exit_ask": exit_price,
        "pnl_pct": pnl_pct,
        "reason": full_reason,
    }


def open_position(state, candidate):
    prices = get_spread_prices(candidate["symbol"])
    entry_bid = prices["bid"] if prices else candidate["price"]  # SHORT: sell at bid
    entry_mid = prices["mid"] if prices else candidate["price"]
    size = 0.001  # paper

    state["active_position"] = {
        "symbol": candidate["symbol"],
        "side": "DOWN",
        "entry_price": entry_mid,
        "entry_bid_price": entry_bid,
        "entry_score": candidate["score"],
        "size": size,
        "lowest_price": entry_mid,
        "stop_pct": -3.0,
        "opened_at_unix": int(time.time()),
        "opened_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    return {
        "entered": True,
        "symbol": candidate["symbol"],
        "price_mid": entry_mid,
        "price_bid": entry_bid,
        "score": candidate["score"],
        "volume_24h_usd": candidate["volume_24h_usd"],
        "vol_spike_ratio": candidate["max_vol_spike_ratio"],
        "buy_sell_ratio": candidate.get("buy_sell_ratio", 0),
        "order_book_ratio": candidate.get("order_book_ratio", 0),
        "5m_momentum": candidate.get("5m_momentum"),
        "spread_at_entry": prices["spread_pct"] if prices else 0,
    }


# ─── Main ──────────────────────────────────────────────────────────────

def execute():
    state_path = DATA_DIR / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}

    result = {}

    # Check BTC mood
    btc_mood = check_btc_mood()
    result["btc_mood"] = btc_mood

    # Run scanner
    fresh_candidates = run_scanner()

    # Read LONG bot signals for context
    shared = read_shared_signals()
    result["long_signals"] = {
        "long_position": shared.get("long_position"),
        "long_candidates": shared.get("candidates", []),
    }

    # Apply BTC mood penalty
    fresh_candidates = apply_btc_penalty(fresh_candidates, btc_mood)

    # Save scan
    scan_output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidates": fresh_candidates,
        "scanned_count": 100,
        "strategy": "short_v1",
        "btc_mood": btc_mood,
    }
    (DATA_DIR / "scan_latest.json").write_text(json.dumps(scan_output, indent=2))
    result["scan_top3"] = [c["symbol"] for c in fresh_candidates[:3]]
    result["scan_top_scores"] = [c["score"] for c in fresh_candidates[:3]]

    # ── Check position ──
    if state.get("active_position"):
        pos_check, switch_target = check_position(state, fresh_candidates)
        result["position_check"] = pos_check

        if pos_check["action"] == "exit":
            close_result = close_position(state, pos_check)
            result.update(close_result)

            if switch_target:
                entry_info = open_position(state, switch_target)
                result["switch_entered"] = entry_info

        elif pos_check["action"] == "hold":
            state["active_position"]["lowest_price"] = min(
                state["active_position"].get("lowest_price", state["active_position"]["entry_price"]),
                pos_check.get("mid", 0)
            )
        # Write signals
        write_short_signals(state, pos_check, fresh_candidates)

    # ── Enter new ──
    if not state.get("active_position"):
        if fresh_candidates and fresh_candidates[0]["score"] >= MIN_SCORE_TO_TRADE:
            best = fresh_candidates[0]
            entry_info = open_position(state, best)
            result["entered"] = entry_info
            result["entry_reason"] = f"new_signal_{best['score']}"
        else:
            result["evaluation"] = {
                "action": "skip",
                "reason": f"no_candidate_above_{MIN_SCORE_TO_TRADE}" if fresh_candidates else "no_candidates",
            }
        # Write empty signals
        write_short_signals(state, None, fresh_candidates)

    # Save state
    state_path.write_text(json.dumps(state, indent=2))

    # Save trade result
    print(json.dumps(result, indent=2))
    (DATA_DIR / "trade_latest.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    execute()

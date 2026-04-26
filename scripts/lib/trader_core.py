#!/usr/bin/env python3
"""Wave Surf — Core trading logic shared by LONG and SHORT bots."""
import json, time
from pathlib import Path
from .api import get_spread_prices, fetch_json
from .scanner import check_5m_momentum

BINANCE_MAKER_FEE = 0.001
BINANCE_TAKER_FEE = 0.001

SWITCH_SCORE_THRESHOLD = 20
STAGNATION_MIN_ELAPSED = 3600
STAGNATION_BAND = 1.0
PARTIAL_TP_PCT = 2.5
MAX_HOLD_SECONDS = 7200
MIN_SCORE_TO_TRADE = 50


def compute_pnl_long(ap, prices):
    """LONG PnL: bought at ask, sold at bid."""
    if not prices:
        return None, 0
    entry_ask = ap.get("entry_ask_price", ap["entry_price"])
    exit_price = prices["bid"]
    raw_pnl_pct = (exit_price - entry_ask) / entry_ask * 100
    fee_pct = (BINANCE_MAKER_FEE + BINANCE_TAKER_FEE) * 100
    pnl_pct = raw_pnl_pct - fee_pct
    mid_pnl = (prices["mid"] - ap["entry_price"]) / ap["entry_price"] * 100
    return pnl_pct, mid_pnl


def compute_pnl_short(ap, prices):
    """SHORT PnL: sold at bid, buy back at ask."""
    if not prices:
        return None, 0
    entry_sell = ap.get("entry_bid_price", ap["entry_price"])
    exit_buy = prices["ask"]
    raw_pnl_pct = (entry_sell - exit_buy) / entry_sell * 100
    fee_pct = (BINANCE_MAKER_FEE + BINANCE_TAKER_FEE) * 100
    pnl_pct = raw_pnl_pct - fee_pct
    mid_pnl = (ap["entry_price"] - prices["mid"]) / ap["entry_price"] * 100
    return pnl_pct, mid_pnl


def check_position_long(state, fresh_candidates):
    """Check LONG position — same logic as before."""
    return _check_position(
        state, fresh_candidates, side="LONG",
        default_stop=-4.0, tp_pct=10,
        tp_partial_check=lambda m5: m5 and not m5["last_5m_green"],
    )


def check_position_short(state, fresh_candidates):
    """Check SHORT position — same logic as before."""
    return _check_position(
        state, fresh_candidates, side="SHORT",
        default_stop=-3.0, tp_pct=5,
        tp_partial_check=lambda m5: m5 and m5["last_5m_green"],
    )


def _check_position(state, fresh_candidates, side, default_stop, tp_pct, tp_partial_check):
    """Generic position check for LONG or SHORT."""
    ap = state["active_position"]
    prices = get_spread_prices(ap["symbol"])
    if not prices:
        return ({"action": "error", "reason": "price_fetch_failed", "pnl_pct": 0}, None)

    if side == "LONG":
        pnl_pct, mid_pnl = compute_pnl_long(ap, prices)
        extreme = max(ap.get("highest_price", ap["entry_price"]), prices["mid"])
    else:
        pnl_pct, mid_pnl = compute_pnl_short(ap, prices)
        extreme = min(ap.get("lowest_price", ap["entry_price"]), prices["mid"])

    if pnl_pct is None:
        return ({"action": "error", "reason": "pnl_calc_failed", "pnl_pct": 0}, None)

    elapsed = time.time() - ap.get("opened_at_unix", 0)
    stop_pct = ap.get("stop_pct", default_stop)

    # Tighten stop as profit grows
    if mid_pnl >= 5: stop_pct = -2.0
    elif mid_pnl >= 3: stop_pct = -3.0 if side == "LONG" else -2.0
    elif mid_pnl >= 2: stop_pct = stop_pct  # default (could tighten for SHORT)

    should_exit = False
    reason = ""
    switch_target = None

    # 1) Stop loss
    if pnl_pct <= stop_pct:
        should_exit = True
        reason = f"stop_loss_{stop_pct}%"

    # 2) Take profit
    elif pnl_pct >= tp_pct:
        should_exit = True
        reason = f"take_profit_{tp_pct}%"

    # 3) Hard timeout
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
        if m5 and tp_partial_check(m5):
            should_exit = True
            reason = f"partial_take_profit_{pnl_pct}%"

    result = {
        "action": "exit" if should_exit else "hold",
        "reason": reason,
        "bid": prices["bid"],
        "ask": prices["ask"],
        "mid": prices["mid"],
        "spread_pct": prices["spread_pct"],
        "pnl_pct": round(pnl_pct, 2),
        "stop_pct": stop_pct,
        "elapsed_seconds": int(elapsed),
        "entry_score": ap.get("entry_score", 0),
    }
    if side == "LONG":
        result["highest_price"] = extreme
    else:
        result["lowest_price"] = extreme
    return (result, switch_target)


def close_position(state, pos_check, data_dir, exit_side="bid"):
    """Paper-close position and log. exit_side='bid' for LONG, 'ask' for SHORT."""
    ap = state["active_position"]
    entry = ap["entry_price"]
    exit_price = pos_check[exit_side]
    pnl_pct = pos_check["pnl_pct"]

    state["active_position"] = None
    state["total_trades"] = state.get("total_trades", 0) + 1
    if pnl_pct > 0:
        state["wins"] = state.get("wins", 0) + 1
    else:
        state["losses"] = state.get("losses", 0) + 1

    trades_path = Path(data_dir) / "trades.csv"
    with open(trades_path, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ')},close,{ap['symbol']},{exit_price},{entry},{pos_check.get('spread_pct',0)},{pnl_pct},{pos_check['reason']}\n")

    return {
        "closed": True,
        "symbol": ap["symbol"],
        "exit_price": exit_price,
        "pnl_pct": pnl_pct,
        "reason": pos_check["reason"],
    }


def open_position_long(state, candidate):
    """Paper-enter a LONG position."""
    prices = get_spread_prices(candidate["symbol"])
    entry_ask = prices["ask"] if prices else candidate["price"]
    entry_mid = prices["mid"] if prices else candidate["price"]

    state["active_position"] = {
        "symbol": candidate["symbol"],
        "side": "UP",
        "entry_price": entry_mid,
        "entry_ask_price": entry_ask,
        "entry_score": candidate["score"],
        "size": 0.001,
        "highest_price": entry_mid,
        "stop_pct": -4.0,
        "opened_at_unix": int(time.time()),
        "opened_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    return {
        "entered": True,
        "symbol": candidate["symbol"],
        "price_mid": entry_mid,
        "price_ask": entry_ask,
        "score": candidate["score"],
        "volume_24h_usd": candidate["volume_24h_usd"],
        "vol_spike_ratio": candidate["max_vol_spike_ratio"],
        "buy_sell_ratio": candidate.get("buy_sell_ratio", 0),
        "order_book_ratio": candidate.get("order_book_ratio", 0),
        "5m_momentum": candidate.get("5m_momentum"),
        "spread_at_entry": prices["spread_pct"] if prices else 0,
    }


def open_position_short(state, candidate):
    """Paper-enter a SHORT position."""
    prices = get_spread_prices(candidate["symbol"])
    entry_bid = prices["bid"] if prices else candidate["price"]
    entry_mid = prices["mid"] if prices else candidate["price"]

    state["active_position"] = {
        "symbol": candidate["symbol"],
        "side": "DOWN",
        "entry_price": entry_mid,
        "entry_bid_price": entry_bid,
        "entry_score": candidate["score"],
        "size": 0.001,
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


def apply_btc_penalty(candidates, btc_mood):
    """Apply BTC mood penalty/filter to candidates based on mood dict."""
    if not candidates:
        return candidates
    if btc_mood.get("hard_block") or btc_mood.get("hard_block_short"):
        return []
    if btc_mood.get("penalty", 0) != 0:
        for c in candidates:
            c["score"] = max(0, c["score"] + btc_mood["penalty"])
        candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates

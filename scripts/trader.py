#!/usr/bin/env python3
"""
Pump Rider — Trader
Evaluates scanner results, manages positions, trails stops.
"""
import json, time
from pathlib import Path
from urllib.request import urlopen

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"

MIN_SCORE_TO_TRADE = 50  # minimum candidate score to enter

def evaluate_candidates(scan_result):
    """From the scan, decide if we should trade anything."""
    candidates = scan_result.get("candidates", [])
    
    if not candidates:
        return {"action": "skip", "reason": "no_candidates"}
    
    best = candidates[0]
    
    if best["score"] < MIN_SCORE_TO_TRADE:
        return {"action": "skip", "reason": f"best_score_{best['score']}_below_{MIN_SCORE_TO_TRADE}", "best": best}
    
    return {"action": "enter", "reason": "signal_detected", "target": best}

def get_current_price(symbol):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    with urlopen(url) as resp:
        return float(json.load(resp)["price"])

def check_position(state):
    """Check if active position should be closed."""
    ap = state.get("active_position")
    if not ap:
        return {"action": "none"}
    
    current_price = get_current_price(ap["symbol"])
    entry = ap["entry_price"]
    side = ap["side"]
    
    if side == "UP":
        pnl_pct = (current_price - entry) / entry * 100
    else:
        pnl_pct = (entry - current_price) / entry * 100
    
    # Trailing stop logic
    highest_price = max(ap.get("highest_price", entry), current_price)
    pnl_from_peak = (current_price - highest_price) / highest_price * 100 if side == "UP" else 0
    
    stop_pct = ap.get("stop_pct", -4.0)
    
    # Tighten stop as profit increases
    if pnl_pct >= 5:
        stop_pct = -2.0
    elif pnl_pct >= 3:
        stop_pct = -3.0
    
    should_exit = False
    reason = ""
    
    if pnl_pct <= stop_pct:
        should_exit = True
        reason = f"stop_loss_{stop_pct}%"
    elif pnl_pct >= 10:
        should_exit = True
        reason = "take_profit_10%"
    
    # Time exit after 2h
    elapsed = time.time() - ap.get("opened_at_unix", 0)
    if elapsed > 7200:
        should_exit = True
        reason = "time_expired_2h"
    
    return {
        "action": "exit" if should_exit else "hold",
        "reason": reason,
        "current_price": current_price,
        "pnl_pct": round(pnl_pct, 2),
        "stop_pct": stop_pct,
        "highest_price": highest_price,
        "elapsed_seconds": int(elapsed),
    }

def execute():
    """Main trader logic."""
    state_path = DATA_DIR / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    
    result = {}
    
    # Check existing position first
    if state.get("active_position"):
        pos_check = check_position(state)
        result["position_check"] = pos_check
        
        if pos_check["action"] == "exit":
            # Paper close
            entry = state["active_position"]["entry_price"]
            pnl_usd = (pos_check["current_price"] - entry) * state["active_position"]["size"]
            result["closed"] = True
            result["pnl_usd"] = round(pnl_usd, 2)
            result["pnl_pct"] = pos_check["pnl_pct"]
            
            # Update state
            state["active_position"] = None
            state["total_trades"] = state.get("total_trades", 0) + 1
            if pos_check["pnl_pct"] > 0:
                state["wins"] = state.get("wins", 0) + 1
            else:
                state["losses"] = state.get("losses", 0) + 1
            state_path.write_text(json.dumps(state, indent=2))
            
            # Log trade
            trades_path = DATA_DIR / "trades.csv"
            with open(trades_path, "a") as f:
                f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ')},close,{state['active_position']['symbol']},{pos_check['current_price']},,,{pos_check['pnl_pct']},{pos_check['reason']}\n")
    
    # If no position, scan for new entries
    if not state.get("active_position"):
        scan_path = DATA_DIR / "scan_latest.json"
        scan = json.loads(scan_path.read_text()) if scan_path.exists() else {"candidates": []}
        evaluation = evaluate_candidates(scan)
        result["evaluation"] = evaluation
        
        if evaluation["action"] == "enter":
            target = evaluation["target"]
            price = target["price"]
            size = 0.001  # paper trade, adjust later
            
            result["entry"] = {
                "symbol": target["symbol"],
                "price": price,
                "size": size,
            }
            
            state["active_position"] = {
                "symbol": target["symbol"],
                "side": "UP",
                "entry_price": price,
                "size": size,
                "highest_price": price,
                "stop_pct": -4.0,
                "opened_at_unix": int(time.time()),
                "opened_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            state_path.write_text(json.dumps(state, indent=2))
    
    print(json.dumps(result, indent=2))
    (DATA_DIR / "trade_latest.json").write_text(json.dumps(result, indent=2))
    return result

if __name__ == "__main__":
    execute()

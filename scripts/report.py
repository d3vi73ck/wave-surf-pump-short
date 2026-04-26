#!/usr/bin/env python3
"""Format pump bot report for Telegram output. Called by pump_bot.sh."""
import json, subprocess as sp, sys, os

data_dir = sys.argv[1]
trade = json.load(open(data_dir + "/trade_latest.json"))
state = json.load(open(data_dir + "/state.json"))
scan = json.load(open(data_dir + "/scan_latest.json"))
bot_type = sys.argv[2] if len(sys.argv) > 2 else "long"

# Silence holds when nothing changed
should_skip = False
if trade.get("position_check") and trade["position_check"]["action"] == "hold":
    # Check previous state
    skip_path = data_dir + "/.skip_cache.json"
    pc = trade["position_check"]
    pnl = round(pc.get("pnl_pct", 0), 2)
    sym = (state.get("active_position") or {}).get("symbol", "")
    previous = {}
    if os.path.exists(skip_path):
        try: previous = json.load(open(skip_path))
        except: pass
    if previous.get("symbol") == sym and previous.get("pnl") == pnl and previous.get("action") == "hold":
        should_skip = True
    # Also skip if there are no candidates AND we already know
    if not scan.get("candidates") and previous.get("symbol") == sym and previous.get("no_candidates"):
        should_skip = True
    json.dump({"symbol": sym, "pnl": pnl, "action": "hold", "no_candidates": not bool(scan.get("candidates"))}, open(skip_path, "w"))

if should_skip:
    sys.exit(0)

def _s(val):
    """Round score to int if float."""
    if isinstance(val, float):
        return round(val)
    return val

# ── BTC Mood ──
btc = trade.get("btc_mood", {})
if btc.get("btc_price"):
    emoji = {"crash":"U0001f480","bearish":"U0001f427","freefall":"U0001f4c9",
             "bullish":"U0001f7e2","slipping":"U26a0ufe0f","neutral":"U26aa","unknown":"U2753"}
    e = emoji.get(btc.get("mood","unknown"), "U2753")
    e_chr = chr(int(e[1:],16)) if e.startswith("U") else e
    print(f"{e_chr} BTC {btc['btc_price']}$ | 4h: {btc.get('4h_change_pct',0):+.2f}% | mood={btc.get('mood','?')}")
    if btc.get("hard_block_short") and bot_type == "short":
        print("   HARD BLOCK: BTC bullish, no shorts allowed")
    if trade.get("btc_penalty_applied"):
        print(f"   Penalty applied: {btc.get('penalty',0)} pts")

# ── LONG signal (for SHORT reports) ──
if bot_type == "short":
    long_sig = trade.get("long_signals", {})
    long_pos = long_sig.get("long_position")
    if long_pos:
        print(f"LONG bot holds: {long_pos['symbol']} @ {long_pos.get('pnl_pct','?')}%")

# ── Scanner summary ──
print(f"Scan: {len(scan.get('candidates',[]))} candidates")
for c in scan.get("candidates", [])[:3]:
    m5 = c.get("5m_momentum", {}) or {}
    mm = ""
    if m5:
        g = "G" if m5.get("last_5m_green") else "R"
        mm = f" 5m:{g}{m5.get('5m_vol_ratio',0):.1f}x"
    print(f"  {c['symbol']:12s} score={_s(c['score']):>3d}  vol={c.get('max_vol_spike_ratio',0):>5.1f}x b/s={c.get('buy_sell_ratio',0):>5.1f} ba={c.get('order_book_ratio',0):>5.2f}{mm}")
if len(scan.get("candidates",[])) > 3:
    print(f"  ... and {len(scan['candidates'])-3} more")

# ── Trade action ──
if trade.get("closed"):
    print(f"Closed: {trade['symbol']} | {trade['pnl_pct']}% | {trade.get('reason','')}")
    if trade.get("switch_entered"):
        e = trade["switch_entered"]
        print(f"Switched to {e['symbol']} @ ${e['price_mid']} | score={_s(e['score'])}")
    elif trade.get("entered"):
        e = trade["entered"]
        print(f"New entry: {e['symbol']} @ ${e['price_mid']} | score={_s(e['score'])} | vol={e['vol_spike_ratio']}x")
elif trade.get("position_check"):
    pc = trade["position_check"]
    if pc["action"] == "exit":
        print(f"Exit: {pc['pnl_pct']}% | {pc.get('reason','')}")
    else:
        held = pc.get("elapsed_seconds",0)
        label = f" ({held//60}m {held%60}s)" if held else ""
        escore = _s(pc.get("entry_score","?"))
        stype = "SHORT " if bot_type == "short" else ""
        print(f"Holding {stype}: {pc['pnl_pct']}% | stop={pc['stop_pct']}% | entry_score={escore}{label}")
        if pc.get("reason") and pc["reason"] != "":
            print(f"  -> {pc['reason']}")
elif trade.get("entered"):
    e = trade["entered"]
    stype = " SHORT" if bot_type == "short" else ""
    print(f"Entered{stype}: {e['symbol']} @ ${e['price_mid']} | score={_s(e['score'])} | vol={e['vol_spike_ratio']}x | spread={e.get('spread_at_entry',0)}%")
elif trade.get("evaluation"):
    ev = trade["evaluation"]
    print(f"Skip: {ev.get('reason','')}")
else:
    print("No action")

# ── Timeline ──
tl = sp.run(["python3", data_dir + "/../scripts/timeline.py", data_dir], capture_output=True, text=True)
if tl.stdout.strip():
    print()
    print(tl.stdout.strip())

# ── Stats ──
print()
wr = round(state.get("wins",0) / max(state.get("total_trades",0), 1) * 100)
print(f"{state.get('total_trades',0)} trades | {state.get('wins',0)}W / {state.get('losses',0)}L ({wr}% WR)")
pos = state.get("active_position")
if pos:
    opened = pos.get("opened_at","?")
    pnl_label = ""
    pc = trade.get("position_check", {}) or {}
    if pc.get("pnl_pct") is not None:
        pnl_label = f" ({pc['pnl_pct']:+.2f}%)"
    escore = _s(pos.get("entry_score","?"))
    print(f"Position: {pos['symbol']} @ ${pos['entry_price']} (score={escore}){pnl_label} opened {opened}")

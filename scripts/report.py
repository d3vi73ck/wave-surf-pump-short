#!/usr/bin/env python3
"""Formatted report for Wave Surf Pump."""
import json
import os
import sys

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

try:
    trade = json.load(open(os.path.join(DATA_DIR, "trade_latest.json")))
    state = json.load(open(os.path.join(DATA_DIR, "state.json")))
    scan = json.load(open(os.path.join(DATA_DIR, "scan_latest.json")))
except FileNotFoundError as e:
    print(f"Data file missing: {e}")
    sys.exit(0)

# Scanner summary
candidates = scan.get("candidates", [])
print(f'\nScan: {len(candidates)} candidates found')
for c in candidates[:3]:
    m5 = c.get("5m_momentum") or {}
    vol_ratio = c.get("max_vol_spike_ratio", 0)
    bsr = c.get("buy_sell_ratio", 0)
    obr = c.get("order_book_ratio", 0)
    mm = ""
    if m5:
        indicator = "G" if m5.get("last_5m_green") else "R"
        mm = f" 5m:{indicator}x{str(m5.get('5m_vol_ratio',0))}"
    sym = c.get("symbol", "???")
    sc = c.get("score", 0)
    print(f"  {sym:12s} score={sc:3d}  vol={vol_ratio:>5.1f}x b/s={bsr:>5.1f} ba={obr:>5.2f}{mm}")
if len(candidates) > 3:
    print(f"  ... and {len(candidates)-3} more")

# Trade action
if trade.get("closed"):
    sym = trade.get("symbol", "?")
    pnl = trade.get("pnl_pct", "?")
    reason = trade.get("reason", "")
    print(f"\nClosed: {sym} | {pnl}% | {reason}")
    if trade.get("switch_entered"):
        e = trade["switch_entered"]
        print(f"Switched -> {e['symbol']} @ ${e['price_mid']} | score={e['score']}")
    elif trade.get("entered"):
        e = trade["entered"]
        print(f"New entry: {e['symbol']} @ ${e['price_mid']} | score={e['score']} | vol={e['vol_spike_ratio']}x")
elif trade.get("position_check"):
    pc = trade["position_check"]
    if pc["action"] == "exit":
        print(f"\nExit: {pc.get('pnl_pct','?')}% | {pc.get('reason','')}")
    else:
        held = pc.get("elapsed_seconds", 0)
        label = f"({held//60}m {held%60}s)" if held else ""
        print(f"\nHolding: {pc['pnl_pct']}% | stop={pc['stop_pct']}% | entry_score={pc.get('entry_score','?')} {label}")
        if pc.get("reason"):
            print(f"  -> {pc['reason']}")
elif trade.get("entered"):
    e = trade["entered"]
    print(f"\nEntered: {e['symbol']} @ ${e['price_mid']} | score={e['score']} | vol={e['vol_spike_ratio']}x | spread={e['spread_at_entry']}%")
elif trade.get("evaluation"):
    ev = trade["evaluation"]
    print(f"\nSkip: {ev.get('reason','')}")
else:
    print("\nNo action")

# Stats
print()
print(f"Stats: {state.get('total_trades',0)} trades | {state.get('wins',0)}W / {state.get('losses',0)}L")
pos = state.get("active_position")
if pos:
    opened = pos.get("opened_at", "?")
    print(f"Position: {pos['symbol']} @ ${pos['entry_price']} (score={pos.get('entry_score','?')}) opened {opened}")

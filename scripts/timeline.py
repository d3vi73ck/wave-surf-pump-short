#!/usr/bin/env python3
"""Print trade timeline from CSV for bot reports."""
import json, sys
from pathlib import Path

data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd() / "data"
state = json.loads((data_dir / "state.json").read_text())
trades_csv = data_dir / "trades.csv"

lines = []
with open(trades_csv) as f:
    for raw in f.read().strip().splitlines():
        parts = raw.split(",")
        if len(parts) >= 7 and parts[0] != "timestamp":
            ts = parts[0][11:16]
            sym = parts[2]
            pnl = float(parts[6])
            reason = parts[7].replace("_", " ")[:28] if len(parts) > 7 else ""
            arrow = "✅" if pnl > 0 else ("❌" if pnl < 0 else "⚪")
            lines.append(f"{arrow} {ts} {sym:8s} {pnl:>+6.2f}%  {reason}")

active_sym = state.get("active_position", {}).get("symbol", "")
active_pnl = ""
if active_sym:
    # quick pnl from trade_latest if available
    try:
        tl = json.loads((data_dir / "trade_latest.json").read_text())
        pc = tl.get("position_check", {}) or {}
        hold_pnl = pc.get("pnl_pct", "")
        active_pnl = f" (now: {hold_pnl}%)" if hold_pnl else ""
    except: pass

if lines:
    print("─── Timeline ───")
    for l in lines[-6:]:  # last 6
        print(l)
    if active_sym:
        print(f"▸ {active_sym} active{active_pnl}")

#!/usr/bin/env bash
#
# pump_bot.sh — Wave Surf Pump Orchestrator
# Runs scanner + trader in sequence and prints a concise report.
#
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "🌊 Wave Surf Pump — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "──────────────────────────────────────────"

# 1. Scan
echo "🔍 Scanning top altcoins for volume spikes..."
cd "$DIR"
python3 "$DIR/scripts/scanner.py"
SCAN_EXIT=$?
if [ $SCAN_EXIT -ne 0 ]; then
    echo "❌ Scanner failed (exit $SCAN_EXIT)"
    exit $SCAN_EXIT
fi

# Show candidate summary
CANDIDATES=$(python3 -c "
import json
data = json.load(open('$DIR/data/scan_latest.json'))
print(f'Scanned: {data[\"scanned_count\"]} coins')
print(f'Candidates: {len(data[\"candidates\"])}')
for c in data[\"candidates\"]:
    print(f'  {c[\"symbol\"]:12s} score={c[\"score\"]:3d}  vol_ratio={c[\"volume_ratio\"]:>5.1f}x  price_chg={c[\"price_change_1h_pct\"]:>6.2f}%  buy/sell={c[\"trades\"][\"buy_sell_ratio\"]:>5.1f}  bid_ask={c[\"order_book\"][\"bid_ask_ratio\"]:>5.2f}')
")
echo "$CANDIDATES"

# 2. Trade
echo ""
echo "💰 Running trader..."
python3 "$DIR/scripts/trader.py"

TRADE_SUMMARY=$(python3 -c "
import json
trade = json.load(open('$DIR/data/trade_latest.json'))
if trade.get('position_check'):
    pc = trade['position_check']
    if pc['action'] == 'exit':
        print(f'📤 Closed: {pc[\"pnl_pct\"]}% | {pc[\"reason\"]}')
    else:
        print(f'🏁 Holding: {pc[\"pnl_pct\"]}% | stop={pc[\"stop_pct\"]}% | {pc.get(\"reason\",\"active\")}')
elif trade.get('evaluation'):
    ev = trade['evaluation']
    if ev['action'] == 'enter':
        t = ev['target']
        print(f'🚀 Entering: {t[\"symbol\"]} @ \${t[\"price\"]} | score={t[\"score\"]}')
    elif ev['action'] == 'skip':
        print(f'⏭️  Skip: {ev[\"reason\"]}')
else:
    print('ℹ️  No action')
print('')
# State summary
state = json.load(open('$DIR/data/state.json'))
print(f'📊 Stats: {state.get(\"total_trades\",0)} trades | {state.get(\"wins\",0)}W / {state.get(\"losses\",0)}L')
pos = state.get('active_position')
if pos:
    print(f'📌 Position: {pos[\"symbol\"]} @ \${pos[\"entry_price\"]} (opened {pos.get(\"opened_at\",\"?\")})')
")
echo "$TRADE_SUMMARY"

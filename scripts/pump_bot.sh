#!/usr/bin/env bash
#
# pump_bot.sh — Wave Surf Pump SHORT v1
# Shorts the dump after the pump. Same smart features as LONG v4.
#
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="$DIR/data"

echo " Wave Surf Pump SHORT v1 — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "──────────────────────────────────────────"

cd "$DIR"
timeout 120 python3 "$DIR/scripts/trader.py"

python3 -c "
import json, subprocess as sp
DATA = '$DATA_DIR'
trade = json.load(open(DATA + '/trade_latest.json'))
state = json.load(open(DATA + '/state.json'))
scan = json.load(open(DATA + '/scan_latest.json'))

# BTC Mood
btc = trade.get('btc_mood', {})
if btc.get('btc_price'):
    emoji = {'crash':'💀','bearish':'🐻','freefall':'📉','bullish':'🟢','slipping':'⚠️','neutral':'⚪','unknown':'❓'}
    e = emoji.get(btc.get('mood','unknown'),'❓')
    print(f'\\n{e} BTC {btc[\"btc_price\"]}\$ | 4h: {btc.get(\"4h_change_pct\",0):+.2f}% | mood={btc.get(\"mood\",\"?\")}')
    if btc.get('hard_block_short'):
        print(f'   HARD BLOCK: BTC bullish, no shorts allowed')
    if trade.get('btc_penalty_applied'):
        print(f'   Penalty applied: {btc.get(\"penalty\",0)} pts')

# Long bot signal
long_sig = trade.get('long_signals', {})
long_pos = long_sig.get('long_position')
if long_pos:
    print(f'\\n LONG bot holds: {long_pos[\"symbol\"]} @ {long_pos.get(\"pnl_pct\",\"?\")}%')

# Scanner summary
print(f'\\nScan: {len(scan.get(\"candidates\",[]))} dump candidates')
for c in scan.get('candidates', [])[:3]:
    m5 = c.get('5m_momentum', {}) or {}
    mm = ''
    if m5:
        g = 'G' if m5.get('last_5m_green') else 'R'
        mm = f' 5m:{g}{m5.get(\"5m_vol_ratio\",0):.1f}x'
    print(f'  {c[\"symbol\"]:12s} score={c[\"score\"]:3d}  vol={c.get(\"max_vol_spike_ratio\",0):>5.1f}x b/s={c.get(\"buy_sell_ratio\",0):>5.1f} ba={c.get(\"order_book_ratio\",0):>5.2f}{mm}')
if len(scan.get('candidates',[])) > 3:
    print(f'  ... and {len(scan[\"candidates\"])-3} more')

# Trade action
if trade.get('closed'):
    print(f'\\nClosed SHORT: {trade[\"symbol\"]} | {trade[\"pnl_pct\"]}% | {trade.get(\"reason\",\"\")}')
    if trade.get('switch_entered'):
        e = trade['switch_entered']
        print(f'Switched -> {e[\"symbol\"]} @ \${e[\"price_mid\"]} | score={e[\"score\"]}')
    elif trade.get('entered'):
        e = trade['entered']
        print(f'New entry: {e[\"symbol\"]} @ \${e[\"price_mid\"]} | score={e[\"score\"]} | vol={e[\"vol_spike_ratio\"]}x')
elif trade.get('position_check'):
    pc = trade['position_check']
    if pc['action'] == 'exit':
        print(f'\\nSHORT exit: {pc[\"pnl_pct\"]}% | {pc.get(\"reason\",\"\")}')
    else:
        held = pc.get('elapsed_seconds',0)
        label = f'({held//60}m {held%60}s)' if held else ''
        print(f'\\nHolding SHORT: {pc[\"pnl_pct\"]}% | stop={pc[\"stop_pct\"]}% | entry_score={pc.get(\"entry_score\",\"?\")} {label}')
        if pc.get('reason') and pc['reason'] != '':
            print(f'  -> {pc[\"reason\"]}')
elif trade.get('entered'):
    e = trade['entered']
    print(f'\\nEntered SHORT: {e[\"symbol\"]} @ \${e[\"price_mid\"]} | score={e[\"score\"]} | b/s={e.get(\"buy_sell_ratio\",0)}')
elif trade.get('evaluation'):
    ev = trade['evaluation']
    print(f'\\nSkip short: {ev.get(\"reason\",\"\")}')
else:
    print('\\nNo short action')

# Timeline
tl = sp.run(['python3', '$DIR/scripts/timeline.py', DATA], capture_output=True, text=True)
if tl.stdout.strip():
    print()
    print(tl.stdout.strip())

# Stats
print()
print(f'Stats: {state.get(\"total_trades\",0)} trades | {state.get(\"wins\",0)}W / {state.get(\"losses\",0)}L')
pos = state.get('active_position')
if pos:
    opened = pos.get('opened_at','?')
    pnl_label = ''
    pc = trade.get('position_check', {}) or {}
    if pc.get('pnl_pct') is not None:
        pnl_label = f' ({pc[\"pnl_pct\"]:+.2f}%)'
    print(f'Position: SHORT {pos[\"symbol\"]} @ \${pos[\"entry_price\"]} (score={pos.get(\"entry_score\",\"?\")}){pnl_label} opened {opened}')
" || true

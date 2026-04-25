# Wave Surf Pump — AgentSkill

## Description
Pump-and-dump detection bot for Binance altcoins. Scans for early volume spikes (>3x average), validates with order book health and buy pressure, enters with trailing stop. Paper trading only. Runs every 5 minutes.

## When to use
- User mentions "pump", "dump", "wave surf", "pump rider", "altcoin scanner"
- Task involves Binance trading bots, volume spike detection, or crypto market scanning
- Checking pump bot status or recent trades

## Location
```
/home/valkenor/Desktop/repo/wave-surf-pump/
```

## Quick Commands
```bash
# Manual scan + trade
cd /home/valkenor/Desktop/repo/wave-surf-pump
./scripts/pump_bot.sh

# Check status
cat data/state.json

# Check latest scan candidates
python3 -c "import json; d=json.load(open('data/scan_latest.json')); print(f'Scanned: {d[\"scanned_count\"]} coins | {len(d[\"candidates\"])} candidates'); [print(f'  {c[\"symbol\"]:12s} score={c[\"score\"]:3d} vol={c[\"volume_ratio\"]:>4.1f}x chg={c[\"price_change_1h_pct\"]:>5.2f}%') for c in d['candidates']]"

# View trade log
cat data/trades.csv
```

## Parameters
| Parameter | Value |
|-----------|-------|
| Volume spike threshold | 3x avg hourly vol |
| Max entry price pump | <8% in last hour |
| Min score to trade | 50/100 |
| Trailing stop initial | -4% |
| Trailing stop (profit >3%) | -3% |
| Trailing stop (profit >5%) | -2% |
| Take profit | +10% |
| Max hold time | 2 hours |
| Paper size | 0.001 units |

## Scoring
- Volume spike >5x: +30 | >3x: +20
- Price up: +20 | Green candles (2+): +15
- Bid/ask >0.8: +15 | >0.5: +5
- Buy/sell >1.2: +20 | >1.0: +10
- Penalties: price >5%: -10 | bid/ask <0.3: -20

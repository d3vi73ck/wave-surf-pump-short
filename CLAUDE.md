# Wave Surf Pump — Project Context

## Overview
Pump-and-dump detection bot. Scans Binance altcoins for early volume spikes and rides them with a trailing stop. Paper trading only.

## Structure
```
wave-surf-pump/
├── scripts/
│   ├── scanner.py        — Binance scan every 5min, score candidates 0-100
│   ├── trader.py         — Entry/exit logic, trailing stop, paper trades
│   ├── pump_bot.sh       — Orchestrator (scanner + trader + report)
│   └── init_db.py        — Initialize empty coins_db.json
├── data/
│   ├── state.json        — Current position, trade stats
│   ├── trades.csv        — Historical trade log
│   ├── scan_latest.json  — Last scan results
│   ├── trade_latest.json — Last trade decision
│   └── coins_db.json     — Historical volume baselines per coin
├── CLAUDE.md
└── skills/
    └── wave-surf-pump/
        └── SKILL.md
```

## Key Parameters
- **Volume spike threshold:** 3x average hourly volume
- **Max price pump to enter:** <8% in last hour
- **Min price move:** 0.5%
- **Min score to trade:** 50/100
- **Trailing stop:** -4% initial, tightens to -3% at +3% profit, -2% at +5% profit
- **Take profit:** +10%
- **Time exit:** 2 hours max
- **Paper trade size:** 0.001 units

## Scoring System (0-100)
- Volume spike 5x+: +30 | 3x+: +20
- Positive price change: +20
- Consecutive green candles (2+): +15
- Order book bid/ask >0.8: +15 | >0.5: +5
- Buy/sell ratio >1.2: +20 | >1.0: +10
- Penalties: price >5%: -10 | bid/ask <0.3: -20 (trap)

## Cron
Runs every 5 minutes via OpenClaw cron. The AI reviews the scan, applies judgment, and can override the mechanical pick.

## Commands
```bash
# Manual run
./scripts/pump_bot.sh

# View state
cat data/state.json

# View trades
cat data/trades.csv

# View latest scan
cat data/scan_latest.json
```

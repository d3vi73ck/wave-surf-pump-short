# Wave Surf Pump — Project Context

## 🎯 Core Objective
**Make money.** Every decision serves this goal. The bot exists to generate profit — not to trade for the sake of trading, not to be technically perfect. Every entry, hold, skip, or rotation is evaluated against one question: *"Does this maximize expected profit?"*

**Key principles:**
- Capital preservation matters — avoiding losses is as important as catching wins
- Opportunity cost is real — holding a flat position blocks better opportunities
- Small losses are acceptable if the new opportunity has significantly higher upside
- A skipped trade is better than a losing trade
- Over time, protect the account first, grow it second

## Overview
**Pump Rider v3** — Updated scanner that detects FRESH volume spikes only. 
Focuses on coins with small baselines ($10K-$1M daily volume) that suddenly spike **6x-50x+** in hourly volume.

🎯 **The idea:** Find a coin doing $50K/day that suddenly does $500K in one hour → jump in early → ride the pump → exit before dump.

## Key Changes v2 → v3
- 🩸 **FIXED the main loss pattern**: buying into old spikes that already peaked
- ✅ **Spike freshness filter**: only enters if the spike is in the current OR last 1h candle
- ✅ **Rejects stale pumps**: if the biggest volume candle is 2+ hours old, skip
- ✅ **Bonus points** for spikes happening in the CURRENT candle (+10 score)
- ✅ Baseline excludes the 3 most recent candles (cleaner avg, not inflated by spike)
- ✅ Scanner outputs `spike_age_candles` so agents can verify freshness
- 🕐 **5m candle fine filter** (v3.1): checks last 3 five-minute candles for real-time momentum
  - Last 5m candle must be green (price going up NOW)
  - 5m crash > -1.5% = hard reject
  - Bad 5m momentum caps score at 40 (below 50 trade threshold)

## Key Changes v1 → v2
- ❌ Removed $500K minimum daily volume (was missing early pumps)
- ❌ Stopped scanning top 50 (was looking at already-big coins)
- ✅ New range: $10K - $1M daily volume (small but active)
- ✅ Volume spike threshold: 6x (was 3x — higher = more explosive)
- ✅ Score rewards massive spike ratios from tiny baselines
- ✅ Excludes BTC/ETH/BNB/SOL/XRP + stablecoins + leveraged tokens
- ✅ Scans top 100 by volume within the new range

## Structure
```
wave-surf-pump/
├── scripts/
│   ├── scanner.py        — v2: Binance scan every 5min, score candidates
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

## Key Parameters (v3)
- **Baseline volume range:** $10K - $1M daily
- **Volume spike threshold:** 6x average hourly volume
- **Max price pump to enter:** <10% in last hour
- **Min price move:** 1%
- **Min score to trade:** 50/100
- **Spike freshness:** Only enter if spike candle is current or last (age ≤ 1)
- **Baseline method:** Excludes last 3 candles to avoid spike inflation
- **Trailing stop:** -4% initial, tightens to -3% at +3% profit, -2% at +5% profit
- **Take profit:** +10%
- **Time exit:** 2 hours max

## Scoring System (0-100)
| Signal | Points |
|---|---|
| Volume spike 50x+ | 40 |
| Volume spike 30x+ | 35 |
| Volume spike 20x+ | 30 |
| Volume spike 10x+ | 20 |
| Volume spike 6x+ | 10 |
| Positive price change | 15 |
| Consecutive green candles | 10 |
| Spike in current candle (fresh) | 10 |
| Active 5m buying (green + vol) | 10 |
| Tiny baseline + massive spike | 10 |
| Order book bid/ask >0.8 | 15 |
| Buy/sell ratio >2.0 | 20 |
| Buy/sell ratio >1.2 | 10 |
| **Penalties** | |
| Price >6% (late) | -10 |
| High vol + dropping price | -15 |
| Order book trap (<0.3) | -20 |
| Price dumping (<-3%) | -15 |
| Spike age >1 candle (stale) | auto-reject |
| 5m candle red + no green streak | score cap 40 |
| 5m crash > -1.5% | auto-reject |

## Agent Review Rules

### Weekend Handling
- The scanner outputs `weekend_mode: true` as a flag for awareness
- **DO NOT** use weekend as a reason to skip strong signals
- Judge each candidate on its merit: volume spike, order book, buy pressure
- Weekend weekend flag only for context in reporting — not as a dealbreaker
- A 70+ score with clean order book and organic buys is a trade regardless of day

### Multi-Position Logic
- Currently single position only (one trade at a time)
- When holding a position and a new strong candidate appears:
  - Evaluate: is the new signal significantly stronger than the current position?
  - If current position is flat/neutral (<2% move) and new candidate scores 70+, consider closing current to rotate into the new play
  - If current position has good momentum (>3% profit), hold and skip
  - Never hold more than one position (for now)

### Override Authority
- You can override the mechanical scanner's score
- If a score 50+ candidate has: buy/sell >1.5 AND organic trade distribution AND healthy order book → enter even if score is borderline
- If score is high (70+) but the data shows trap signs (equal buy/sell, repeating sizes, thin books) → skip regardless of score

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

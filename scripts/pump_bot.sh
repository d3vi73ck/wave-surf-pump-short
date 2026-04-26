#!/usr/bin/env bash
#
# pump_bot.sh — Wave Surf Pump SHORT v1
# Shorts the dump after the pump. Same smart features as LONG v4.
#
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="$DIR/data"

echo "🔻 Wave Surf Pump SHORT — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "──────────────────────────────────────────"

cd "$DIR"
timeout 120 python3 "$DIR/scripts/trader.py"
python3 "$DIR/scripts/report.py" "$DATA_DIR" "short"

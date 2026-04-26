#!/usr/bin/env python3
"""
Wave Surf Pump — SHORT Trader v1.2
====================================
Inverse of LONG bot. Shoots the dump after the pump.
Reads LONG signals to avoid same-symbol conflicts.
"""
import json, time, sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"

sys.path.insert(0, str(PROJECT_DIR))
from scripts.lib import api as _api
from scripts.lib import mood as _mood
from scripts.lib import scanner as _scanner
from scripts.lib import signals as _signals
from scripts.lib import trader_core as _core

MIN_SCORE_TO_TRADE = 50


def execute():
    state_path = DATA_DIR / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    result = {}

    # BTC mood (short mode)
    btc_mood = _mood.check(bot_type="short")
    result["btc_mood"] = btc_mood

    # Scanner (short mode)
    fresh_candidates = _scanner.run_short_scanner(100)
    fresh_candidates = _core.apply_btc_penalty(fresh_candidates, btc_mood)

    # Read LONG bot signals for conflict detection
    shared = _signals.read_long_signals()
    result["long_signals"] = {
        "long_position": shared.get("long_position"),
        "long_candidates": shared.get("candidates", []),
    }

    scan_output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidates": fresh_candidates,
        "scanned_count": 100,
        "strategy": "short_v12",
        "btc_mood": btc_mood,
    }
    (DATA_DIR / "scan_latest.json").write_text(json.dumps(scan_output, indent=2))
    result["scan_top3"] = [c["symbol"] for c in fresh_candidates[:3]]
    result["scan_top_scores"] = [c["score"] for c in fresh_candidates[:3]]

    long_sym = (shared.get("long_position") or {}).get("symbol") if shared else None

    # Check current position with LONG conflict detection
    if state.get("active_position"):
        pos_check, switch_target = _core.check_position_short(state, fresh_candidates)
        ap_sym = state["active_position"]["symbol"]

        # Force exit if LONG entered our symbol
        if long_sym and ap_sym == long_sym and pos_check["action"] != "exit":
            pos_check["action"] = "exit"
            pos_check["reason"] = f"conflict_LONG_entered_{long_sym}_pnl_{pos_check.get('pnl_pct',0)}%"
            switch_target = None

        result["position_check"] = pos_check

        if pos_check["action"] == "exit":
            close_result = _core.close_position(state, pos_check, DATA_DIR, exit_side="ask")
            result.update(close_result)

            if switch_target:
                if long_sym and switch_target["symbol"] == long_sym:
                    result["evaluation"] = {"action": "skip", "reason": f"conflict_LONG_holds_{long_sym}"}
                else:
                    entry_info = _core.open_position_short(state, switch_target)
                    result["switch_entered"] = entry_info
        else:
            state["active_position"]["lowest_price"] = min(
                state["active_position"].get("lowest_price", state["active_position"]["entry_price"]),
                pos_check.get("mid", 0))

        _signals.write_short_signals(state, pos_check, fresh_candidates, PROJECT_DIR)

    # Enter new position (no active + conflict check)
    if not state.get("active_position"):
        if fresh_candidates and fresh_candidates[0]["score"] >= MIN_SCORE_TO_TRADE:
            best = fresh_candidates[0]
            if long_sym and best["symbol"] == long_sym:
                result["evaluation"] = {"action": "skip", "reason": f"conflict_LONG_holds_{long_sym}"}
            else:
                entry_info = _core.open_position_short(state, best)
                result["entered"] = entry_info
                result["entry_reason"] = f"new_signal_{best['score']}"
        else:
            result["evaluation"] = {"action": "skip",
                "reason": f"no_candidate_above_{MIN_SCORE_TO_TRADE}" if fresh_candidates else "no_candidates"}
        _signals.write_short_signals(state, None, fresh_candidates, PROJECT_DIR)

    # Save
    state_path.write_text(json.dumps(state, indent=2))
    print(json.dumps(result, indent=2))
    (DATA_DIR / "trade_latest.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    execute()

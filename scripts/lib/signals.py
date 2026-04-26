#!/usr/bin/env python3
"""Wave Surf — Shared signals between LONG and SHORT bots."""
import json, time
from pathlib import Path
from .scanner import check_5m_momentum

LONG_SIGNALS_PATH = Path("/home/valkenor/Desktop/repo/wave-surf-pump/data/shared_signals.json")


def read_long_signals():
    """Read signals from LONG bot's shared file."""
    if LONG_SIGNALS_PATH.exists():
        try:
            return json.loads(LONG_SIGNALS_PATH.read_text())
        except:
            return {"long_position": None, "candidates": []}
    return {"long_position": None, "candidates": []}


def write_long_signals(state, pos_check, fresh_candidates):
    """Write LONG bot signals for SHORT bot."""
    ap = state.get("active_position")
    signal = None
    if ap and pos_check:
        try:
            from .scanner import check_5m_momentum
            m5 = check_5m_momentum(ap["symbol"])
        except:
            m5 = None
        signal = {
            "symbol": ap["symbol"],
            "entry_price": ap["entry_price"],
            "entry_score": ap.get("entry_score", 0),
            "pnl_pct": pos_check.get("pnl_pct"),
            "elapsed_seconds": pos_check.get("elapsed_seconds"),
            "5m_momentum": m5,
            "stop_pct": pos_check.get("stop_pct"),
        }
    signals = {
        "long_position": signal,
        "candidates": [{"symbol": c["symbol"], "score": c["score"]} for c in fresh_candidates[:3]],
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        LONG_SIGNALS_PATH.write_text(json.dumps(signals, indent=2))
    except:
        pass


def write_short_signals(state, pos_check, fresh_candidates, project_dir):
    """Write SHORT bot signals for LONG bot."""
    ap = state.get("active_position")
    signals = {
        "short_position": {
            "symbol": ap["symbol"] if ap else None,
            "entry_price": ap["entry_price"] if ap else None,
            "pnl_pct": pos_check.get("pnl_pct") if pos_check else None,
            "elapsed_seconds": pos_check.get("elapsed_seconds") if pos_check else None,
        } if ap else None,
        "candidates": [{"symbol": c["symbol"], "score": c["score"]} for c in fresh_candidates[:3]],
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        short_path = Path(project_dir) / "data" / "shared_signals_short.json"
        short_path.write_text(json.dumps(signals, indent=2))
    except:
        pass

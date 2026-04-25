#!/usr/bin/env python3
"""
coins_db.json initializer — creates empty volume baselines file.
"""
import json
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
DB_PATH = DATA_DIR / "coins_db.json"

if not DB_PATH.exists():
    db = {
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "coins": {}
    }
    DB_PATH.write_text(json.dumps(db, indent=2))
    print(f"Created empty coins_db.json at {DB_PATH}")
else:
    print(f"coins_db.json already exists")

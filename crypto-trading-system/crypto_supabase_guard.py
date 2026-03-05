#!/usr/bin/env python3
"""
crypto_supabase_guard.py — F8: Supabase write guard with retry + alert
Owner: Alfred | Created: 2026-03-01

Every Supabase write goes through this guard. On failure: retry 3x with
exponential backoff, then return failure status for caller to go DEFENSIVE.
"""

import os
import time
import json
from datetime import datetime, timezone

try:
    from supabase import create_client
except ImportError:
    create_client = None

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds

_client = None

def _get_client():
    global _client
    if _client is None and create_client and SUPABASE_KEY:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client

def guarded_insert(table: str, data: dict) -> dict:
    """Insert with retry. Returns {"ok": True, "data": ...} or {"ok": False, "error": ...}"""
    client = _get_client()
    if not client:
        return {"ok": False, "error": "No Supabase client available"}

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            result = client.table(table).insert(data).execute()
            if result.data:
                return {"ok": True, "data": result.data}
            else:
                last_error = f"Empty response on attempt {attempt+1}"
        except Exception as e:
            last_error = str(e)

        if attempt < MAX_RETRIES - 1:
            time.sleep(BACKOFF_BASE ** (attempt + 1))

    return {
        "ok": False,
        "error": f"Failed after {MAX_RETRIES} retries: {last_error}",
        "table": table,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "GO_DEFENSIVE"
    }

def guarded_upsert(table: str, data: dict, on_conflict: str = "id") -> dict:
    """Upsert with retry."""
    client = _get_client()
    if not client:
        return {"ok": False, "error": "No Supabase client available"}

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            result = client.table(table).upsert(data, on_conflict=on_conflict).execute()
            if result.data:
                return {"ok": True, "data": result.data}
            else:
                last_error = f"Empty response on attempt {attempt+1}"
        except Exception as e:
            last_error = str(e)

        if attempt < MAX_RETRIES - 1:
            time.sleep(BACKOFF_BASE ** (attempt + 1))

    return {
        "ok": False,
        "error": f"Failed after {MAX_RETRIES} retries: {last_error}",
        "table": table,
        "action": "GO_DEFENSIVE"
    }

def guarded_update(table: str, data: dict, match: dict) -> dict:
    """Update with retry."""
    client = _get_client()
    if not client:
        return {"ok": False, "error": "No Supabase client available"}

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            q = client.table(table).update(data)
            for k, v in match.items():
                q = q.eq(k, v)
            result = q.execute()
            return {"ok": True, "data": result.data}
        except Exception as e:
            last_error = str(e)

        if attempt < MAX_RETRIES - 1:
            time.sleep(BACKOFF_BASE ** (attempt + 1))

    return {
        "ok": False,
        "error": f"Failed after {MAX_RETRIES} retries: {last_error}",
        "table": table,
        "action": "GO_DEFENSIVE"
    }


if __name__ == "__main__":
    print("crypto_supabase_guard.py — Supabase write guard")
    print(f"  URL: {SUPABASE_URL}")
    print(f"  Key configured: {'yes' if SUPABASE_KEY else 'NO'}")
    print(f"  Max retries: {MAX_RETRIES}")
    print(f"  Backoff base: {BACKOFF_BASE}s")
    print("  Status: READY")

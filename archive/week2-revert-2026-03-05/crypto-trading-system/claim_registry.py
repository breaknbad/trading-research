#!/usr/bin/env python3
"""
Claim Registry — Prevents duplicate module builds across bots.

Before building ANY new module, call claim(). If another bot already
claimed it, you get BLOCKED. First-come, first-served.

Usage:
  from claim_registry import claim, get_claims, is_claimed
  result = claim("alfred", "crypto_new_module.py")  # {"claimed": True} or {"claimed": False, "owner": "vex"}
  claims = get_claims()  # Full registry
"""

import json
import os
from datetime import datetime, timezone

REGISTRY_FILE = os.path.join(os.path.dirname(__file__), "data", "claim_registry.json")


def _load() -> dict:
    if os.path.exists(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save(registry: dict):
    os.makedirs(os.path.dirname(REGISTRY_FILE), exist_ok=True)
    with open(REGISTRY_FILE, "w") as f:
        json.dump(registry, f, indent=2)


def claim(bot_id: str, module_name: str) -> dict:
    """Claim a module. Returns {"claimed": True} if successful, or {"claimed": False, "owner": "..."} if taken."""
    registry = _load()
    key = module_name.lower().strip()
    bot_id = bot_id.lower().strip()

    if key in registry and registry[key]["owner"] != bot_id:
        return {
            "claimed": False,
            "owner": registry[key]["owner"],
            "claimed_at": registry[key]["claimed_at"],
            "message": f"BLOCKED — {module_name} already claimed by {registry[key]['owner']}",
        }

    registry[key] = {
        "owner": bot_id,
        "claimed_at": datetime.now(timezone.utc).isoformat(),
    }
    _save(registry)
    return {"claimed": True, "owner": bot_id, "module": module_name}


def release(bot_id: str, module_name: str) -> dict:
    """Release a claim (only the owner can release)."""
    registry = _load()
    key = module_name.lower().strip()
    bot_id = bot_id.lower().strip()

    if key not in registry:
        return {"released": False, "message": "Not claimed"}
    if registry[key]["owner"] != bot_id:
        return {"released": False, "message": f"Owned by {registry[key]['owner']}, not {bot_id}"}

    del registry[key]
    _save(registry)
    return {"released": True, "module": module_name}


def is_claimed(module_name: str) -> dict:
    """Check if a module is claimed."""
    registry = _load()
    key = module_name.lower().strip()
    if key in registry:
        return {"claimed": True, **registry[key]}
    return {"claimed": False}


def get_claims(bot_id: str = None) -> dict:
    """Get all claims, optionally filtered by bot."""
    registry = _load()
    if bot_id:
        return {k: v for k, v in registry.items() if v["owner"] == bot_id.lower()}
    return registry


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        bot = sys.argv[1]
        claims = get_claims(bot)
        print(f"{bot}'s claims: {len(claims)}")
        for module, info in claims.items():
            print(f"  {module} — claimed {info['claimed_at']}")
    else:
        claims = get_claims()
        print(f"Total claims: {len(claims)}")
        for module, info in claims.items():
            print(f"  {module} → {info['owner']} ({info['claimed_at']})")

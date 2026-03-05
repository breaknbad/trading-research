"""bot_config.py — Auto-detect bot identity from hostname or env.

Usage in any script:
    from bot_config import BOT_ID, BOT_IDS
"""
import os, socket

_HOST_MAP = {
    "Matthews-MacBook-Pro": "tars",
    "matthewharfmann": "tars",
    "Sheridans-MacBook-Pro": "alfred",
    "sheridanskala": "alfred",
    "Marks-MacBook-Pro": "eddie_v",
    "markmatuska": "eddie_v",
    "Kents-MacBook-Pro": "vex",
    "kentharfmann": "vex",
}

_USER_MAP = {
    "matthewharfmann": "tars",
    "sheridanskala": "alfred",
    "markmatuska": "eddie_v",
    "kentharfmann": "vex",
}

def detect_bot_id():
    """Detect bot identity from BOT_ID env var, username, or hostname."""
    # Explicit env override
    if os.getenv("BOT_ID"):
        return os.getenv("BOT_ID")
    # Username match
    user = os.getenv("USER", "")
    if user in _USER_MAP:
        return _USER_MAP[user]
    # Hostname match
    hostname = socket.gethostname()
    for key, bot in _HOST_MAP.items():
        if key.lower() in hostname.lower():
            return bot
    return "unknown"

BOT_ID = detect_bot_id()
# Bot IDs including crypto variant
BOT_IDS = [BOT_ID, f"{BOT_ID}_crypto"]

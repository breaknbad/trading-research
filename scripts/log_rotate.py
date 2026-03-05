#!/usr/bin/env python3
"""log_rotate.py — Truncate logs over 500KB to last 200 lines.
Runs daily via launchd. Prevents unbounded log growth.
"""
import os, glob

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIRS = [
    os.path.join(WORKSPACE, "logs"),
    os.path.join(WORKSPACE, "trading-research", "logs"),
]
MAX_BYTES = 500_000  # 500KB
KEEP_LINES = 200

for d in LOG_DIRS:
    for f in glob.glob(os.path.join(d, "*.log")):
        try:
            if os.path.getsize(f) > MAX_BYTES:
                with open(f, 'r') as fh:
                    lines = fh.readlines()
                with open(f, 'w') as fh:
                    fh.writelines(lines[-KEEP_LINES:])
                print(f"✂️ Trimmed {os.path.basename(f)} to {KEEP_LINES} lines")
        except Exception as e:
            print(f"⚠️ Error rotating {f}: {e}")

print("✅ Log rotation complete")

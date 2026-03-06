#!/usr/bin/env python3
"""meeting_enforcer.py — Never miss a meeting again.

Fires 2 min before scheduled meetings. Posts agenda + pings owner.
If owner doesn't post within 5 min, next bot in speaking order takes over.

Speaking order: Vex → TARS → Alfred → Eddie
"""

import json
import os
from datetime import datetime

MEETINGS = {
    "pre_market": {"time": "09:00", "tz": "ET", "owner": "Vex", "backup": "TARS",
                    "agenda": "Pre-market brief: regime, overnight moves, trade tickets, factor scores"},
    "after_market": {"time": "17:00", "tz": "CT", "owner": "TARS", "backup": "Vex",
                      "agenda": "EOD review: P&L, velocity blocks, missed trades, protocol fixes"},
    "midnight": {"time": "23:00", "tz": "CT", "owner": "Eddie", "backup": "Vex",
                  "agenda": "Midnight DA: books, strategy, unlimited rounds, factor updates"},
}


def format_reminder(meeting_name, meeting):
    """Format the meeting reminder post."""
    lines = [
        f"⏰ **{meeting_name.upper()} MEETING** — Starting in 2 minutes",
        f"**Owner:** {meeting['owner']} (backup: {meeting['backup']})",
        f"**Agenda:** {meeting['agenda']}",
        "",
        f"Speaking order: Vex → TARS → Alfred → Eddie",
        f"",
        f"{meeting['owner']}: You have 5 min to open. If silent, {meeting['backup']} takes over."
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    meeting = sys.argv[1] if len(sys.argv) > 1 else "after_market"
    if meeting in MEETINGS:
        print(format_reminder(meeting, MEETINGS[meeting]))
    else:
        print(f"Unknown meeting: {meeting}. Options: {list(MEETINGS.keys())}")

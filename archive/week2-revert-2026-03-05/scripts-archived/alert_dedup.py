#!/usr/bin/env python3
"""
alert_dedup.py — Alert deduplication layer for market_watcher.

Groups raw alerts within a 60s window that share a ticker or are causally
related (e.g., big_move + rsi_extreme on same ticker = one incident).

Reads:
  - alerts.json (raw alerts from market_watcher)

Outputs:
  - alerts_deduped.json (deduplicated incidents)

Each incident contains:
  - id: unique incident ID
  - root_cause: label describing the incident
  - severity: CRITICAL / HIGH / MEDIUM
  - alerts: list of constituent raw alerts
  - timestamp: earliest alert timestamp in the group
  - tickers: list of tickers involved

Usage:
  python3 alert_dedup.py                                    # defaults
  python3 alert_dedup.py --input alerts.json --output alerts_deduped.json
  python3 alert_dedup.py --window 90                        # 90s grouping window

Can be called by market_watcher after writing raw alerts, or run standalone.
Pure Python, no external dependencies beyond stdlib.
"""

import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [alert_dedup] %(levelname)s %(message)s", stream=sys.stderr)
log = logging.getLogger("alert_dedup")

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = SCRIPT_DIR / "alerts.json"
DEFAULT_OUTPUT = SCRIPT_DIR / "alerts_deduped.json"

# Causal relationship map: alert types that merge into a single incident
CAUSAL_GROUPS = {
    frozenset({"big_move", "rsi_extreme"}): "momentum_spike",
    frozenset({"big_move", "volume_spike"}): "breakout",
    frozenset({"rsi_extreme", "volume_spike"}): "climax_move",
    frozenset({"big_move", "rsi_extreme", "volume_spike"}): "climax_breakout",
    frozenset({"liquidation", "big_move"}): "liquidation_cascade",
    frozenset({"funding_extreme", "big_move"}): "funding_driven_move",
    frozenset({"price_divergence", "big_move"}): "divergence_breakout",
}

# Severity escalation rules
SEVERITY_ORDER = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}

# Alert types that auto-escalate to certain severities
TYPE_SEVERITY = {
    "liquidation": "CRITICAL",
    "liquidation_cascade": "CRITICAL",
    "climax_breakout": "CRITICAL",
    "big_move": "HIGH",
    "funding_extreme": "HIGH",
    "rsi_extreme": "MEDIUM",
    "volume_spike": "MEDIUM",
    "price_divergence": "MEDIUM",
}


def parse_timestamp(ts):
    """Parse ISO timestamp string to epoch seconds."""
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.timestamp()
        except Exception:
            return 0.0
    return 0.0


def get_ticker(alert):
    """Extract ticker from alert (various field names)."""
    for key in ("ticker", "symbol", "pair", "asset"):
        v = alert.get(key)
        if v:
            return v.upper()
    return None


def get_alert_type(alert):
    """Extract alert type."""
    for key in ("type", "alert_type", "kind", "signal"):
        v = alert.get(key)
        if v:
            return v.lower()
    return "unknown"


def get_severity(alert):
    """Extract or infer severity."""
    sev = alert.get("severity", "").upper()
    if sev in SEVERITY_ORDER:
        return sev
    # Infer from type
    atype = get_alert_type(alert)
    return TYPE_SEVERITY.get(atype, "MEDIUM")


def max_severity(sevs):
    """Return highest severity from a list."""
    best = "MEDIUM"
    for s in sevs:
        if SEVERITY_ORDER.get(s, 0) > SEVERITY_ORDER.get(best, 0):
            best = s
    return best


def find_root_cause(alert_types):
    """Determine root cause label from a set of alert types."""
    types = frozenset(alert_types)
    # Check exact and subset matches
    best_match = None
    best_size = 0
    for pattern, label in CAUSAL_GROUPS.items():
        if pattern <= types and len(pattern) > best_size:
            best_match = label
            best_size = len(pattern)
    if best_match:
        return best_match
    # Single type
    if len(types) == 1:
        return next(iter(types))
    return "+".join(sorted(types))


def make_incident_id(alerts, timestamp):
    """Deterministic incident ID from constituent alerts."""
    raw = json.dumps([a.get("id", str(i)) for i, a in enumerate(alerts)], sort_keys=True) + str(timestamp)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def group_alerts(alerts, window_sec=60):
    """Group alerts into incidents by ticker + time window + causal relationships."""
    if not alerts:
        return []

    # Sort by timestamp
    for a in alerts:
        a["_ts"] = parse_timestamp(a.get("timestamp", a.get("time", a.get("created_at", 0))))
    alerts.sort(key=lambda a: a["_ts"])

    # Group by ticker first, then by time window
    ticker_groups = {}
    no_ticker = []
    for a in alerts:
        t = get_ticker(a)
        if t:
            ticker_groups.setdefault(t, []).append(a)
        else:
            no_ticker.append(a)

    incidents = []

    for ticker, group in ticker_groups.items():
        # Merge alerts within window_sec of each other
        clusters = []
        current = [group[0]]
        for a in group[1:]:
            if a["_ts"] - current[0]["_ts"] <= window_sec:
                current.append(a)
            else:
                clusters.append(current)
                current = [a]
        clusters.append(current)

        for cluster in clusters:
            types = {get_alert_type(a) for a in cluster}
            sevs = [get_severity(a) for a in cluster]
            root_cause = find_root_cause(types)
            sev = max_severity(sevs)

            # Escalate severity based on root cause
            rc_sev = TYPE_SEVERITY.get(root_cause)
            if rc_sev and SEVERITY_ORDER.get(rc_sev, 0) > SEVERITY_ORDER.get(sev, 0):
                sev = rc_sev

            earliest_ts = min(a["_ts"] for a in cluster)
            # Clean internal fields before output
            clean = [{k: v for k, v in a.items() if not k.startswith("_")} for a in cluster]

            inc_id = make_incident_id(clean, earliest_ts)
            incidents.append({
                "id": inc_id,
                "root_cause": root_cause,
                "severity": sev,
                "tickers": [ticker],
                "alerts": clean,
                "alert_count": len(clean),
                "timestamp": datetime.fromtimestamp(earliest_ts, tz=timezone.utc).isoformat(),
            })

    # Non-ticker alerts each become their own incident
    for a in no_ticker:
        clean = {k: v for k, v in a.items() if not k.startswith("_")}
        inc_id = make_incident_id([clean], a["_ts"])
        incidents.append({
            "id": inc_id,
            "root_cause": get_alert_type(a),
            "severity": get_severity(a),
            "tickers": [],
            "alerts": [clean],
            "alert_count": 1,
            "timestamp": datetime.fromtimestamp(a["_ts"], tz=timezone.utc).isoformat(),
        })

    # Sort incidents by severity (desc) then timestamp
    incidents.sort(key=lambda i: (-SEVERITY_ORDER.get(i["severity"], 0), i["timestamp"]))
    return incidents


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Alert deduplication layer")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Path to raw alerts.json")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output path")
    parser.add_argument("--window", type=int, default=60, help="Grouping window in seconds")
    args = parser.parse_args()

    try:
        with open(args.input) as f:
            raw = json.load(f)
    except FileNotFoundError:
        log.error("Input file not found: %s", args.input)
        sys.exit(1)
    except json.JSONDecodeError as e:
        log.error("Invalid JSON in %s: %s", args.input, e)
        sys.exit(1)

    # Handle both list of alerts and dict with "alerts" key
    if isinstance(raw, dict):
        alerts = raw.get("alerts", [])
    elif isinstance(raw, list):
        alerts = raw
    else:
        log.error("Unexpected format in %s", args.input)
        sys.exit(1)

    log.info("Read %d raw alerts from %s", len(alerts), args.input)
    incidents = group_alerts(alerts, window_sec=args.window)
    log.info("Grouped into %d incidents (window=%ds)", len(incidents), args.window)

    result = {
        "incidents": incidents,
        "incident_count": len(incidents),
        "raw_alert_count": len(alerts),
        "dedup_ratio": round(len(incidents) / max(len(alerts), 1), 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Atomic write
    output_path = Path(args.output)
    tmp_path = output_path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        os.replace(str(tmp_path), str(output_path))
        log.info("Wrote %s (%d incidents from %d alerts)", output_path.name, len(incidents), len(alerts))
    except Exception as e:
        log.error("Failed to write output: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()

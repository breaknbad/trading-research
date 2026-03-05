#!/usr/bin/env python3
"""
news_dedup.py - Deduplicate news headlines by clustering similar stories.

Reads headline objects from a JSON file (argument) or stdin, clusters
duplicates using Jaccard similarity on normalized title tokens, extracts
ticker symbols, and outputs clustered JSON.

Input format (JSON array):
    [{"source": "...", "title": "...", "url": "...", "timestamp": "..."}, ...]

Output format:
    {
      "clusters": [
        {
          "canonical": {"source": "...", "title": "...", "url": "...", "timestamp": "..."},
          "sources": [{"source": "...", "title": "...", "url": "...", "timestamp": "..."}],
          "tickers": ["AAPL", "MSFT"],
          "count": 3
        }
      ],
      "total_headlines": 10,
      "total_clusters": 4
    }

Usage:
    python3 news_dedup.py headlines.json
    cat headlines.json | python3 news_dedup.py
"""

import json
import re
import sys
from collections import OrderedDict

# Similarity threshold for clustering
JACCARD_THRESHOLD = 0.6

# Prefixes to strip from headlines before comparison
STRIP_PREFIXES = [
    r"^breaking\s*:\s*",
    r"^just in\s*:\s*",
    r"^update\s*:\s*",
    r"^exclusive\s*:\s*",
    r"^report\s*:\s*",
    r"^developing\s*:\s*",
    r"^alert\s*:\s*",
    r"^watch\s*:\s*",
    r"^live\s*:\s*",
    r"^opinion\s*:\s*",
    r"^analysis\s*:\s*",
]

# Common English stop words to optionally filter (not removed by default
# to preserve meaning, but available if needed)
TICKER_PATTERN = re.compile(r'\$([A-Z]{1,5})\b')
# Also match standalone uppercase 1-4 letter words that look like tickers
# but only well-known ones to avoid false positives
KNOWN_TICKERS = {
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "NVDA",
    "AMD", "INTC", "NFLX", "DIS", "BA", "JPM", "GS", "MS", "BAC",
    "WFC", "C", "V", "MA", "PYPL", "SQ", "COIN", "HOOD", "PLTR",
    "SNOW", "CRM", "ORCL", "IBM", "UBER", "LYFT", "ABNB", "DASH",
    "SPOT", "ROKU", "ZM", "DOCU", "NET", "CRWD", "DDOG", "MDB",
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "DOT", "AVAX",
    "SPY", "QQQ", "IWM", "DIA", "VIX", "TLT", "GLD", "SLV",
    "XOM", "CVX", "COP", "OXY", "LMT", "RTX", "NOC", "GD",
    "PFE", "JNJ", "UNH", "MRK", "ABBV", "LLY", "BMY", "GILD",
    "WMT", "TGT", "COST", "HD", "LOW", "NKE", "SBUX", "MCD",
    "F", "GM", "RIVN", "LCID", "NIO", "LI", "XPEV",
    "ARM", "SMCI", "MRVL", "AVGO", "QCOM", "MU", "LRCX", "AMAT",
}


def normalize_title(title):
    """Normalize a headline for comparison.

    - Lowercase
    - Strip common prefixes (Breaking:, etc.)
    - Remove punctuation
    - Return word set
    """
    t = title.lower().strip()
    for prefix in STRIP_PREFIXES:
        t = re.sub(prefix, "", t, flags=re.IGNORECASE)
    # Remove punctuation
    t = re.sub(r"[^\w\s]", " ", t)
    # Split into words, filter empties
    words = [w for w in t.split() if len(w) > 1]
    return set(words)


def jaccard_similarity(set_a, set_b):
    """Compute Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def extract_tickers(title):
    """Extract ticker symbols from a headline.

    Matches $TICKER patterns and known uppercase ticker words.
    """
    tickers = set()
    # Explicit $TICKER mentions
    for match in TICKER_PATTERN.finditer(title):
        tickers.add(match.group(1))
    # Check for known tickers as standalone words
    words = re.findall(r'\b([A-Z]{1,5})\b', title)
    for w in words:
        if w in KNOWN_TICKERS:
            tickers.add(w)
    return sorted(tickers)


def cluster_headlines(headlines):
    """Cluster headlines by Jaccard similarity on normalized titles.

    Returns list of clusters, each with a canonical headline, sources, and tickers.
    """
    if not headlines:
        return []

    # Precompute normalized word sets
    normalized = [(h, normalize_title(h.get("title", ""))) for h in headlines]
    used = [False] * len(normalized)
    clusters = []

    for i, (headline_i, words_i) in enumerate(normalized):
        if used[i]:
            continue
        # Start new cluster
        cluster_members = [headline_i]
        cluster_tickers = set(extract_tickers(headline_i.get("title", "")))
        used[i] = True

        for j in range(i + 1, len(normalized)):
            if used[j]:
                continue
            headline_j, words_j = normalized[j]
            if jaccard_similarity(words_i, words_j) > JACCARD_THRESHOLD:
                cluster_members.append(headline_j)
                cluster_tickers.update(extract_tickers(headline_j.get("title", "")))
                used[j] = True

        # Pick canonical: earliest timestamp, or first if no timestamps
        canonical = cluster_members[0]
        for m in cluster_members[1:]:
            if m.get("timestamp", "") and (
                not canonical.get("timestamp", "") or
                m["timestamp"] < canonical["timestamp"]
            ):
                canonical = m

        clusters.append({
            "canonical": canonical,
            "sources": cluster_members,
            "tickers": sorted(cluster_tickers),
            "count": len(cluster_members),
        })

    return clusters


def dedup(headlines):
    """Main dedup function. Returns the output dict."""
    clusters = cluster_headlines(headlines)
    return {
        "clusters": clusters,
        "total_headlines": len(headlines),
        "total_clusters": len(clusters),
    }


def main():
    """Entry point: read from file arg or stdin, dedup, print JSON."""
    raw = None
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        try:
            with open(filepath, "r") as f:
                raw = f.read()
        except FileNotFoundError:
            print(f"Error: file not found: {filepath}", file=sys.stderr)
            sys.exit(1)
        except IOError as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        if sys.stdin.isatty():
            print("Usage: python3 news_dedup.py <headlines.json>", file=sys.stderr)
            print("   or: cat headlines.json | python3 news_dedup.py", file=sys.stderr)
            sys.exit(1)
        raw = sys.stdin.read()

    try:
        headlines = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(headlines, list):
        print("Error: expected a JSON array of headline objects", file=sys.stderr)
        sys.exit(1)

    result = dedup(headlines)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

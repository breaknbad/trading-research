#!/usr/bin/env python3
"""News/Sentiment Scanner — dumb loop, no AI.
Runs every 5 min via launchd. Scans headlines, pulls Fear & Greed, writes to alerts.json + fleet_signals.
"""
import json, os, sys, time, urllib.request, urllib.error, re
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bot_config import BOT_ID

# --- Config ---
WORKSPACE = os.environ.get("WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")

ALERTS_PATH = os.path.join(WORKSPACE, "alerts.json")
STATE_PATH = os.path.join(WORKSPACE, "scripts", "sentiment_state.json")
LOG_PATH = os.path.join(WORKSPACE, "logs", "news_sentiment_scanner.log")

# Watchlist — tickers we care about
WATCHLIST = ["BTC", "ETH", "SOL", "AVAX", "LINK", "SUI", "ARB",
             "SPY", "QQQ", "XLE", "GDX", "GLD", "AMZN", "XLV", "EFA", "EWC"]

# Keyword sentiment classification
BULLISH_KEYWORDS = [
    "surge", "rally", "soar", "jump", "breakout", "bullish", "upgrade",
    "beat expectations", "all-time high", "ath", "recovery", "green",
    "buy signal", "accumulation", "inflow", "approval", "partnership",
    "adoption", "institutional", "etf approved", "rate cut", "dovish",
    "stimulus", "fed pivot"
]
BEARISH_KEYWORDS = [
    "crash", "plunge", "dump", "selloff", "sell-off", "bearish", "downgrade",
    "miss expectations", "low", "decline", "red", "sell signal", "outflow",
    "hack", "exploit", "breach", "ban", "regulation", "lawsuit", "sec",
    "default", "recession", "rate hike", "hawkish", "tariff", "sanctions",
    "war", "attack", "crisis", "bankruptcy", "liquidat"
]
URGENT_KEYWORDS = [
    "crash", "halt", "circuit breaker", "black swan", "flash crash",
    "emergency", "war", "attack", "sanctions", "default", "bankrupt",
    "exploit", "hack", "rug pull"
]

def log(msg):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    with open(LOG_PATH, "a") as f:
        f.write(line)
    print(line.strip())

def fetch_json(url, headers=None, timeout=10):
    try:
        req = urllib.request.Request(url, headers=headers or {})
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read())
    except Exception as e:
        log(f"Fetch error {url}: {e}")
        return None

def load_state():
    if os.path.exists(STATE_PATH):
        try:
            return json.load(open(STATE_PATH))
        except:
            pass
    return {"last_headlines": [], "last_fng": None, "last_run": None}

def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)

def load_alerts():
    if os.path.exists(ALERTS_PATH):
        try:
            data = json.load(open(ALERTS_PATH))
            if isinstance(data, list):
                return [a for a in data if isinstance(a, dict)]
            return []
        except:
            pass
    return []

def save_alerts(alerts):
    with open(ALERTS_PATH, "w") as f:
        json.dump(alerts, f, indent=2)

def classify_headline(title):
    """Simple keyword-based sentiment. Returns (sentiment, score, is_urgent)."""
    lower = title.lower()
    bull_hits = sum(1 for kw in BULLISH_KEYWORDS if kw in lower)
    bear_hits = sum(1 for kw in BEARISH_KEYWORDS if kw in lower)
    urgent = any(kw in lower for kw in URGENT_KEYWORDS)

    if bull_hits > bear_hits:
        return "bullish", min(bull_hits * 20, 100), urgent
    elif bear_hits > bull_hits:
        return "bearish", min(bear_hits * 20, 100), urgent
    return "neutral", 0, urgent

def find_ticker_in_text(text, tickers):
    """Find which watchlist tickers appear in text."""
    upper = text.upper()
    found = []
    for t in tickers:
        # Match whole word
        if re.search(rf'\b{re.escape(t)}\b', upper):
            found.append(t)
    return found

def fetch_fear_greed():
    """Fetch crypto Fear & Greed Index."""
    data = fetch_json("https://api.alternative.me/fng/?limit=1")
    if data and "data" in data and len(data["data"]) > 0:
        entry = data["data"][0]
        return {
            "value": int(entry.get("value", 50)),
            "label": entry.get("value_classification", "Neutral"),
            "timestamp": entry.get("timestamp")
        }
    return None

def search_news(query, count=5):
    """Search news via Brave Search API. Falls back to empty on failure."""
    if not BRAVE_API_KEY:
        log("No BRAVE_API_KEY — skipping news search")
        return []
    url = f"https://api.search.brave.com/res/v1/news/search?q={urllib.request.quote(query)}&count={count}&freshness=pd"
    headers = {"Accept": "application/json", "Accept-Encoding": "gzip", "X-Subscription-Token": BRAVE_API_KEY}
    data = fetch_json(url, headers)
    if data and "results" in data:
        return [{"title": r.get("title", ""), "url": r.get("url", ""), "description": r.get("description", "")} for r in data["results"]]
    return []

def write_fleet_signal(signal_type, ticker, direction, score, message, metadata=None):
    """Write a signal to fleet_signals table."""
    if not SUPABASE_KEY:
        log("No SUPABASE_KEY — skipping fleet_signals write")
        return
    payload = json.dumps({
        "bot_id": BOT_ID,
        "signal_type": signal_type,
        "ticker": ticker,
        "direction": direction,
        "score": score,
        "message": message,
        "metadata": json.dumps(metadata or {}),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    }).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/fleet_signals",
        data=payload,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        },
        method="POST"
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        log(f"Signal written: {signal_type} {ticker} {direction} score={score}")
    except Exception as e:
        log(f"fleet_signals write error: {e}")

def run_scan():
    state = load_state()
    alerts = load_alerts()
    now = datetime.now(timezone.utc).isoformat()
    new_alerts = []
    seen_titles = set(state.get("last_headlines", []))

    # 1. Fear & Greed Index
    fng = fetch_fear_greed()
    if fng:
        log(f"Fear & Greed: {fng['value']} ({fng['label']})")
        prev = state.get("last_fng")
        # Alert on extreme values or big swings
        if fng["value"] <= 20:
            new_alerts.append({
                "source": "news_sentiment_scanner",
                "severity": "high",
                "type": "sentiment",
                "message": f"Extreme Fear: F&G Index at {fng['value']} ({fng['label']})",
                "timestamp": now
            })
            write_fleet_signal("risk_off", "CRYPTO", "bearish", fng["value"],
                             f"Extreme Fear: F&G at {fng['value']}", {"fng": fng})
        elif fng["value"] >= 80:
            new_alerts.append({
                "source": "news_sentiment_scanner",
                "severity": "medium",
                "type": "sentiment",
                "message": f"Extreme Greed: F&G Index at {fng['value']} ({fng['label']})",
                "timestamp": now
            })
            write_fleet_signal("alert", "CRYPTO", "cautious", fng["value"],
                             f"Extreme Greed: F&G at {fng['value']}", {"fng": fng})
        if prev and abs(fng["value"] - prev) >= 15:
            new_alerts.append({
                "source": "news_sentiment_scanner",
                "severity": "medium",
                "type": "sentiment",
                "message": f"F&G swing: {prev} → {fng['value']} ({abs(fng['value']-prev)} point move)",
                "timestamp": now
            })
        state["last_fng"] = fng["value"]

    # 2. News scan — batch queries to reduce API calls
    queries = [
        "crypto bitcoin ethereum market news",
        "stock market breaking news SPY",
        "oil energy gold commodities news"
    ]
    all_headlines = []
    for q in queries:
        results = search_news(q, count=5)
        all_headlines.extend(results)
        time.sleep(0.5)  # Rate limit

    # 3. Classify headlines
    new_titles = []
    for headline in all_headlines:
        title = headline["title"]
        if title in seen_titles:
            continue
        new_titles.append(title)

        sentiment, score, urgent = classify_headline(title)
        tickers = find_ticker_in_text(title + " " + headline.get("description", ""), WATCHLIST)

        if sentiment == "neutral" and not urgent:
            continue

        log(f"  [{sentiment.upper()} {score}] {title[:80]}...")

        if urgent:
            new_alerts.append({
                "source": "news_sentiment_scanner",
                "severity": "critical",
                "type": "news",
                "sentiment": sentiment,
                "score": score,
                "tickers": tickers,
                "headline": title[:200],
                "url": headline.get("url", ""),
                "timestamp": now
            })

        if score >= 40 or urgent:
            for ticker in (tickers or ["MARKET"]):
                write_fleet_signal(
                    "opportunity" if sentiment == "bullish" else "risk_off",
                    ticker,
                    sentiment,
                    score,
                    title[:200],
                    {"url": headline.get("url", ""), "urgent": urgent}
                )

        if sentiment != "neutral" and score >= 60:
            new_alerts.append({
                "source": "news_sentiment_scanner",
                "severity": "high" if score >= 80 else "medium",
                "type": "news",
                "sentiment": sentiment,
                "score": score,
                "tickers": tickers,
                "headline": title[:200],
                "timestamp": now
            })

    # 4. Update state
    state["last_headlines"] = list(seen_titles | set(new_titles))[-100:]  # Keep last 100
    state["last_run"] = now

    # 5. Merge alerts (keep existing non-expired, add new)
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    fresh_alerts = [a for a in alerts if a.get("timestamp", "") > cutoff]
    fresh_alerts.extend(new_alerts)
    save_alerts(fresh_alerts)
    save_state(state)

    log(f"Scan complete: {len(all_headlines)} headlines, {len(new_alerts)} new alerts, F&G={fng['value'] if fng else 'N/A'}")

if __name__ == "__main__":
    if "--loop" in sys.argv:
        log("Starting news/sentiment scanner loop (5 min interval)")
        while True:
            try:
                run_scan()
            except Exception as e:
                log(f"Scan error: {e}")
            time.sleep(300)  # 5 min
    else:
        run_scan()

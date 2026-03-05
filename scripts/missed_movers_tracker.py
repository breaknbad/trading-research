#!/usr/bin/env python3
"""
Alfred — Missed Movers Tracker
Daily scan: top movers vs our positions. Log what we missed and WHY.
Feeds back into SHIL for permanent pattern detection.
Runs post-market (equities) and every 6h (crypto).
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

WORKSPACE = Path(__file__).parent.parent
CREDS_FILE = Path.home() / ".supabase_trading_creds"
FINNHUB_KEY_FILE = Path.home() / ".finnhub_key"

# Top crypto to track
CRYPTO_TICKERS = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "DOGE-USD", "ADA-USD",
                  "DOT-USD", "LINK-USD", "MATIC-USD", "XRP-USD"]

# Top equity watchlist (expand over time)
EQUITY_TICKERS = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "AMD", "META",
                  "AMZN", "GOOGL", "SMCI", "ARM", "PLTR", "COIN", "MSTR"]

def load_creds():
    creds = {}
    if CREDS_FILE.exists():
        for line in CREDS_FILE.read_text().strip().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                creds[k.strip()] = v.strip()
    return creds

def load_finnhub_key():
    if FINNHUB_KEY_FILE.exists():
        return FINNHUB_KEY_FILE.read_text().strip()
    return None

def supabase_query(creds, table, params=""):
    url = f"{creds['SUPABASE_URL']}/rest/v1/{table}?{params}"
    req = urllib.request.Request(url, headers={
        "apikey": creds["SUPABASE_ANON_KEY"],
        "Authorization": f"Bearer {creds['SUPABASE_ANON_KEY']}",
        "Content-Type": "application/json"
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

def supabase_insert(creds, table, data):
    url = f"{creds['SUPABASE_URL']}/rest/v1/{table}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "apikey": creds["SUPABASE_ANON_KEY"],
        "Authorization": f"Bearer {creds['SUPABASE_ANON_KEY']}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status
    except Exception as e:
        return {"error": str(e)}

def get_crypto_prices():
    """Get current crypto prices from CoinGecko."""
    ids = "bitcoin,ethereum,solana,avalanche-2,dogecoin,cardano,polkadot,chainlink,matic-network,ripple"
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        
        ticker_map = {
            "bitcoin": "BTC-USD", "ethereum": "ETH-USD", "solana": "SOL-USD",
            "avalanche-2": "AVAX-USD", "dogecoin": "DOGE-USD", "cardano": "ADA-USD",
            "polkadot": "DOT-USD", "chainlink": "LINK-USD", "matic-network": "MATIC-USD",
            "ripple": "XRP-USD"
        }
        
        results = []
        for cg_id, ticker in ticker_map.items():
            if cg_id in data:
                results.append({
                    "ticker": ticker,
                    "price": data[cg_id].get("usd", 0),
                    "change_24h_pct": data[cg_id].get("usd_24h_change", 0)
                })
        return sorted(results, key=lambda x: abs(x["change_24h_pct"]), reverse=True)
    except Exception as e:
        print(f"  ❌ CoinGecko error: {e}")
        return []

def get_our_positions(creds):
    """Get all open positions across alfred + alfred_crypto."""
    positions = {}
    for bot in ["alfred", "alfred_crypto"]:
        trades = supabase_query(creds, "trades",
            f"bot_id=eq.{bot}&status=eq.open&select=ticker,quantity,entry_price,side")
        if isinstance(trades, list):
            for t in trades:
                positions[t.get("ticker", "").upper()] = {
                    "bot": bot,
                    "side": t.get("side", "LONG"),
                    "entry": t.get("entry_price", 0),
                    "qty": t.get("quantity", 0)
                }
    return positions

def analyze_missed(movers, positions):
    """Compare top movers against our positions."""
    missed = []
    caught = []
    
    for m in movers:
        ticker = m["ticker"]
        change = m["change_24h_pct"]
        
        if abs(change) < 3.0:  # Only care about 3%+ moves
            continue
            
        if ticker in positions:
            pos = positions[ticker]
            direction_match = (change > 0 and pos["side"] == "LONG") or \
                            (change < 0 and pos["side"] == "SHORT")
            caught.append({
                "ticker": ticker,
                "move_pct": round(change, 2),
                "had_position": True,
                "right_direction": direction_match,
                "entry": pos["entry"],
                "status": "✅ CAUGHT" if direction_match else "⚠️ WRONG SIDE"
            })
        else:
            missed.append({
                "ticker": ticker,
                "move_pct": round(change, 2),
                "price": m["price"],
                "had_position": False,
                "status": "❌ MISSED",
                "potential_gain_pct": round(abs(change), 2)
            })
    
    return caught, missed

def generate_report(caught, missed):
    """Generate and save missed movers report."""
    now = datetime.now()
    report = {
        "timestamp": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "caught": caught,
        "missed": missed,
        "total_movers": len(caught) + len(missed),
        "catch_rate_pct": round(len(caught) / max(len(caught) + len(missed), 1) * 100, 1),
        "biggest_miss": max(missed, key=lambda x: x["potential_gain_pct"]) if missed else None,
        "total_missed_alpha_pct": round(sum(m["potential_gain_pct"] for m in missed), 2)
    }
    
    # Save to file
    report_dir = WORKSPACE / "reports"
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / f"missed_movers_{now.strftime('%Y%m%d_%H%M')}.json"
    report_path.write_text(json.dumps(report, indent=2))
    
    # Also save latest
    latest_path = WORKSPACE / "missed_movers_latest.json"
    latest_path.write_text(json.dumps(report, indent=2))
    
    return report

def main():
    print(f"Alfred Missed Movers Tracker — {datetime.now().strftime('%Y-%m-%d %H:%M:%S ET')}")
    print("=" * 50)
    
    creds = load_creds()
    if not creds.get("SUPABASE_URL"):
        print("ERROR: No Supabase credentials")
        sys.exit(1)
    
    # Get data
    print("\n📊 Fetching crypto prices...")
    movers = get_crypto_prices()
    if movers:
        print(f"  Top movers (24h):")
        for m in movers[:5]:
            direction = "🟢" if m["change_24h_pct"] > 0 else "🔴"
            print(f"    {direction} {m['ticker']}: {m['change_24h_pct']:+.1f}% (${m['price']:,.2f})")
    
    print("\n📋 Checking our positions...")
    positions = get_our_positions(creds)
    print(f"  Open positions: {list(positions.keys()) if positions else 'None'}")
    
    print("\n🎯 Analyzing missed movers (3%+ threshold)...")
    caught, missed = analyze_missed(movers, positions)
    
    report = generate_report(caught, missed)
    
    # Summary
    print(f"\n{'='*50}")
    print(f"📈 Caught: {len(caught)} moves")
    for c in caught:
        print(f"  {c['status']} {c['ticker']} {c['move_pct']:+.1f}%")
    
    print(f"\n❌ Missed: {len(missed)} moves")
    for m in missed:
        print(f"  {m['status']} {m['ticker']} {m['move_pct']:+.1f}% (${m['price']:,.2f})")
    
    print(f"\n🎯 Catch rate: {report['catch_rate_pct']}%")
    if report['biggest_miss']:
        print(f"💰 Biggest miss: {report['biggest_miss']['ticker']} {report['biggest_miss']['move_pct']:+.1f}%")
    print(f"📊 Total missed alpha: {report['total_missed_alpha_pct']}%")
    
    # Push to Supabase system_issues if catch rate is bad
    if report['catch_rate_pct'] < 50 and (len(caught) + len(missed)) > 0:
        issue = {
            "bot": "ALFRED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "category": "performance_anomaly",
            "severity": "WARN",
            "description": f"Missed movers catch rate {report['catch_rate_pct']}% — missed {len(missed)} moves of 3%+",
            "auto_fixable": False,
            "fix_applied": None,
            "status": "open"
        }
        supabase_insert(creds, "system_issues", issue)
    
    return report

if __name__ == "__main__":
    main()

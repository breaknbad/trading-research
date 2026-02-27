# Anomaly Detection & Alert System
> Continuous monitoring. No anomaly ignored or deferred.

## Alert Tiers

### 🔴 CRITICAL (Immediate Action — Pre-Programmed Response)
| Trigger | Threshold | Auto-Response |
|---------|-----------|---------------|
| Stop breach | Price crosses stop level | Immediate sell, notify team |
| VIX spike | >15% intraday move | Suspend new buys, tighten all stops to 1% |
| Position gap | >3% adverse move on single position | Review thesis, sell if no catalyst justifies hold |
| Liquidity gap | Bid-ask spread >2x normal | Suspend trading on ticker |
| Execution failure | Trade rejected or data mismatch | Halt trading on ticker until verified |
| Correlation inversion | Two correlated positions diverge >2% | Flag both, review thesis immediately |

### 🟡 WARNING (Review Within 5 Minutes)
| Trigger | Threshold | Response |
|---------|-----------|----------|
| Sentiment divergence | Price action contradicts sentiment read | Flag for team, no new entries in sector |
| Put/call shift | >20% shift in ratio on held ticker | Document, tighten stop |
| Congressional cluster | 3+ members trading same sector same direction | Alert team, evaluate as trade signal |
| Volume anomaly | >2x average daily volume on held position | Investigate cause, document |
| Regime drift | Indicators shifting between tiers | Prepare CIP tier transition plan |

### 🟢 MONITOR (Log and Track)
| Trigger | Threshold | Response |
|---------|-----------|----------|
| Factor drift | Single factor effectiveness drops >10% in session | Document in factor sheet |
| Minor correlation shift | <2% divergence from expected | Log, review at EOD |
| Execution delay | >5 min between signal identification and trade | Document cause in feedback loop |
| Data staleness | Price data >5 min old during market hours | Re-fetch before any action |

## Alert Format
```
[YYYY-MM-DD HH:MM ET] [🔴/🟡/🟢] [TYPE] [TICKER/SYSTEM] [DETAIL] [ACTION TAKEN]
```

## Escalation
- 🔴 → Post to #capital immediately, execute pre-programmed response, no waiting for consensus
- 🟡 → Post to #capital within 5 min, team reviews, consensus on action
- 🟢 → Log in daily feedback file, review at midnight meeting

## Operational Anomalies (Non-Price)
- Bot goes quiet >20 min during market hours → Backup bot takes over scanning (TARS backs Eddie)
- Price source conflict between bots → Halt, verify on Yahoo Finance, corrected bot acknowledges
- DB integrity issue (phantom trades, duplicate entries) → Immediate audit by TARS, no trading on affected ticker until clean

---
*Created: 2026-02-24 | Effective: 2026-02-25 market open*

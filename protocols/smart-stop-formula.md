# Smart Stop Formula v1
## "Fast + Loud = Hold. Slow + Quiet = Bail."

### The 2-Check Stop System

When a position dips past -1% from entry:

**CHECK 1: Speed** — How fast did it drop?
- Look at the last 2 hours of price action
- **FAST** (>1% drop in 2h) → rebound 67% of the time
- **SLOW** (<1% drop in 2h) → fades 54% of the time

**CHECK 2: Volume** — Is it loud or quiet?
- Compare current hour volume to 24h average
- **LOUD** (volume >1.5x average) → panic selling, tends to snap back
- **QUIET** (volume <1.5x average) → distribution, smart money leaving

### The Grid

| Speed | Volume | Action | Stop |
|-------|--------|--------|------|
| FAST | LOUD | **HOLD** — widen stop to 3.5% | 3.5% |
| FAST | QUIET | **HOLD** — keep standard stop | 2.5% |
| SLOW | LOUD | **WATCH** — tighten to 2% | 2.0% |
| SLOW | QUIET | **EXIT** — tighten to 1.5% or sell | 1.5% |

### Asset Modifier
- **BTC**: +0.5% to all stops (recovers 63% from deep dips)
- **ETH/LINK**: use grid as-is
- **SOL/alts**: -0.5% from all stops (fades 56% of the time)
- **Stocks**: use grid as-is (apply during market hours only)

### Examples
- BTC drops 2% in 1 hour on huge volume → FAST+LOUD → hold, stop at 4.0% (3.5% + 0.5% BTC bonus)
- SOL drifts down 1.5% over 4 hours, low volume → SLOW+QUIET → exit or stop at 1.0% (1.5% - 0.5% alt penalty)
- ETH flash dips 1.5% in 30 min, normal volume → FAST+QUIET → hold, stop at 2.5%

### Integration
`trailing_stop.py` checks speed + volume every cycle and adjusts stops per this grid.
No manual intervention needed. Formula runs automatically.

---
*Built from 30 days of hourly data, 700+ dip events across BTC/ETH/SOL. Mar 5, 2026.*

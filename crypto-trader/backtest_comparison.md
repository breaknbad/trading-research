# Crypto Mean Reversion Backtest Comparison

**Strategy:** Bollinger Bands + RSI Mean Reversion
**Period:** 90 days (Nov 24, 2025 → Feb 22, 2026)
**Timeframe:** 1-hour candles | **Stop Loss:** 3%
**Data Source:** Coinbase Public API

## Summary Table (Ranked by Total Return)

| Rank | Pair | Total Return | Max Drawdown | Sharpe Ratio | Win Rate | Total Trades |
|------|------|-------------|-------------|-------------|----------|-------------|
| 1 | POL-USD | -4.81% | 23.98% | -0.21 | 27.3% | 22 |
| 2 | NEAR-USD | -21.10% | 30.62% | -2.08 | 18.2% | 22 |
| 3 | BTC-USD | -22.15% | 28.47% | -3.88 | 31.6% | 19 |
| 4 | SOL-USD | -26.04% | 35.64% | -3.22 | 15.0% | 20 |
| 5 | XRP-USD | -28.90% | 30.62% | -4.29 | 19.0% | 21 |
| 6 | ARB-USD | -29.14% | 38.57% | -2.58 | 12.0% | 25 |
| 7 | LINK-USD | -29.24% | 32.70% | -4.79 | 11.8% | 17 |
| 8 | DOT-USD | -30.98% | 38.96% | -3.85 | 16.7% | 24 |
| 9 | ETH-USD | -35.28% | 36.10% | -5.54 | 17.4% | 23 |
| 10 | AVAX-USD | -40.03% | 42.67% | -5.96 | 8.7% | 23 |

## Key Observations

### Market Context
This 90-day period (late Nov 2025 – late Feb 2026) was a **brutal downtrend** across crypto. Every single pair lost money with mean reversion — the strategy kept buying dips that kept dipping. The massive stop-loss cascades in late January and early February tell the story.

### Best Performer: POL-USD (-4.81%)
- **By far the least bad** — nearly breakeven despite the bear market
- Highest profit factor (0.95) and best Sharpe (-0.21)
- Larger average wins (+7.60%) helped offset the losses
- Lower-cap alts with higher volatility gave bigger mean reversion bounces

### Worst Performer: AVAX-USD (-40.03%)
- 21 out of 23 trades hit stop loss — only 8.7% win rate
- Deepest drawdown at 42.67%
- Relentless downtrend with almost no mean reversion bounces

### Notable Findings
- **BTC-USD** had the **highest win rate** (31.6%) but still lost 22% — wins were too small relative to the 3% stop losses
- **ARB-USD** had the highest average win (+11.49%) but only won 3 out of 25 trades
- **POL-USD and NEAR-USD** showed the most mean-reversion-friendly behavior
- All Sharpe ratios are deeply negative — no pair was profitable in this regime

### Strategy Assessment
Mean reversion is a **wrong-regime strategy** for sustained downtrends. The 3% stop loss gets triggered repeatedly during trending moves, while the upside capture on bounces can't compensate. This strategy would likely perform much better in a **ranging/sideways market**.

### Recommendations
1. **Add a trend filter** (e.g., 50-period SMA direction) — don't take long mean reversion trades in a downtrend
2. **POL-USD and NEAR-USD** are the best candidates if deploying mean reversion on crypto
3. **Consider wider stops or shorter holding periods** to reduce stop-loss cascades
4. **Backtest a bull/sideways period** for comparison — the strategy's edge likely appears in different regimes

---
*Generated: 2026-02-22 00:36 EST*

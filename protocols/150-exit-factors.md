# 150 Exit Factors — When to Dump
> Built per Mark directive 2026-02-26: "When to dump. What criteria. 150 factors."
> Companion to `150-factors.md` (entry factors)

---

## ROUND 1: Stop Loss & Risk Management Exits (1–30)
*The non-negotiable mechanical exits. These fire automatically — no discretion, no "let me wait and see."*

**#1: Hard Stop — 2% Loss from Entry**
Type: Mechanical
Priority: ABSOLUTE
Mechanism: Price drops 2% from entry. Period. This is the foundation of the entire system. Every dollar saved by a stop is a dollar available for the next trade. No stop = no system.
Action: Auto-sell at market when price crosses -2% from entry. No moving stops down. Ever.

**#2: Trailing Stop — Price Retreats from High Water Mark**
Type: Mechanical
Priority: HIGH
Mechanism: Once a position is profitable, a trailing stop locks in gains. For scouts: 2% trail. For confirms: 1.5% trail. For conviction: 1.5% trail from peak. The trail only moves UP, never down.
Action: Monitor high water mark every 30 seconds. When price drops trail % from peak, sell at market.

**#3: Daily Circuit Breaker — Portfolio Down 5%**
Type: Mechanical
Priority: ABSOLUTE
Mechanism: If total portfolio drops 5% in a single day, ALL new entries are frozen and all positions are evaluated for immediate exit. This prevents catastrophic drawdown from compounding losses.
Action: Close all positions with <1% buffer to their stop. Freeze new entries for the remainder of the day.

**#4: Sector Concentration Breach — >30% in One Sector**
Type: Mechanical
Priority: HIGH
Mechanism: If a winning position grows or new adds push one sector above 30% of portfolio, the excess must be trimmed. Concentration kills portfolios when sectors rotate.
Action: Trim the weakest position in the over-concentrated sector until exposure drops below 30%.

**#5: Position Size Breach — >10% of Portfolio**
Type: Mechanical
Priority: HIGH
Mechanism: If a winning position grows beyond 10% of portfolio value, trim to 10%. Success creates risk — a 10% position that doubles is now 18% of your book and a single-stock risk.
Action: Sell shares to bring position back to 10% of current portfolio value.

**#6: Time Stop — Scout Not Profitable After 3 Days**
Type: Mechanical
Priority: MEDIUM
Mechanism: A scout trade is a hypothesis test. If price hasn't confirmed the thesis within 3 trading days (hasn't moved meaningfully in your direction), the thesis is wrong or the timing is off. Capital sitting idle is capital not working.
Action: Exit scouts that are flat or slightly negative after 3 full trading days. Redeploy into higher-conviction setups.

**#7: Time Stop — Confirm Not +5% After 5 Days**
Type: Mechanical
Priority: MEDIUM
Mechanism: A confirmed trade should be working. If it hasn't generated +5% within a week, the momentum thesis has stalled. Don't let a confirm decay into a "hope" trade.
Action: Exit confirms not up at least 5% after 5 trading days unless a clear catalyst is upcoming (earnings within 2 days).

**#8: End-of-Day Sweep — Inverse/Leveraged ETFs**
Type: Mechanical
Priority: ABSOLUTE
Mechanism: Inverse and leveraged ETFs suffer from daily rebalancing decay. Holding overnight compounds tracking error and creates phantom losses. SQQQ, TQQQ, UVXY, etc. MUST be sold before close.
Action: Auto-sell all inverse/leveraged ETF positions at 3:45 PM. No exceptions. No "I think it'll gap my way."

**#9: Earnings Freeze — Exit Before Binary Event**
Type: Mechanical
Priority: HIGH
Mechanism: Holding through earnings is a coin flip. The factor engine already screens for this on entry, but if a position you hold has earnings TONIGHT or TOMORROW, exit before the report unless conviction is 8+/10.
Action: Exit positions with earnings within 24 hours. Exception only for conviction-tier positions with a defined thesis on the earnings outcome.

**#10: Correlation Spike Exit — Your Positions All Move Together**
Type: Systematic
Priority: MEDIUM
Mechanism: If 4+ of your positions drop simultaneously (correlation spike), you're not diversified — you have one big bet expressed through multiple tickers. A correlated drawdown means the macro thesis is breaking.
Action: When 4+ positions are red simultaneously by >1%, exit the weakest 2 immediately. You're over-exposed to a single risk factor.

**#11: VWAP Rejection — Price Fails to Reclaim VWAP**
Type: Technical
Priority: MEDIUM
Mechanism: VWAP is the institutional fair price. If your position drops below VWAP and fails to reclaim it within 30 minutes, institutions are selling, not buying. You're on the wrong side of the flow.
Action: If price drops below VWAP and two consecutive 5-minute candles close below it, tighten stop to -1% from current price.

**#12: Volume Climax Sell — Huge Volume on Red Candle**
Type: Technical
Priority: HIGH
Mechanism: When a position you hold prints a massive red candle (>3x average volume), it's institutional distribution. Someone large is getting out. They know something or they've changed their mind. Either way, don't be the last one holding.
Action: If a red candle prints with >3x average volume and drops >2% intraday, exit at least half the position immediately.

**#13: Gap Down Through Stop — Slippage Exit**
Type: Mechanical
Priority: ABSOLUTE
Mechanism: If a stock gaps below your stop on the open (overnight news, earnings miss), you can't get your stop price. The temptation is to "wait for a bounce." Don't. Gaps that open below stops continue lower 65% of the time.
Action: Sell at market within the first 5 minutes. Do not wait for a bounce. The gap IS the information.

**#14: Thesis Invalidation — Original Reason No Longer True**
Type: Discretionary
Priority: HIGH
Mechanism: You bought CRM because of earnings momentum. Then guidance disappoints. The thesis is dead — it doesn't matter if price hasn't hit your stop yet. A dead thesis is an exit signal even at breakeven.
Action: When the original reason for the trade is invalidated (catalyst fails, thesis breaks), exit regardless of current P&L. The price will eventually reflect the broken thesis.

**#15: Momentum Exhaustion — Three Drives Pattern**
Type: Technical
Priority: MEDIUM
Mechanism: Three consecutive pushes to new highs with each push weaker (smaller move, less volume) = exhaustion. The third push traps the last buyers. If your position just made its third weakening push higher, take profits.
Action: After three drives, sell 50-75% of position. Keep a small runner with a tight trailing stop.

**#16: RSI Bearish Divergence at Overbought**
Type: Technical
Priority: MEDIUM
Mechanism: Price makes a new high but RSI makes a lower high (divergence). Momentum is fading even as price stretches. This precedes pullbacks 76% of the time. Don't ride the final exhaustion candle.
Action: When RSI diverges bearishly while above 70, sell half and trail the rest at 1%.

**#17: Sector Rotation Out — Relative Strength Breaking Down**
Type: Systematic
Priority: MEDIUM
Mechanism: If your stock's sector is losing relative strength vs SPY (rolling over on RS line), institutional money is rotating elsewhere. Individual stocks rarely fight sector outflows for long.
Action: When sector RS vs SPY turns negative (below 0 on 20-day rate of change), exit the weakest name in that sector. Tighten stops on all sector names.

**#18: Market Regime Shift — Risk-On to Risk-Off**
Type: Macro
Priority: HIGH
Mechanism: When VIX crosses above 25, credit spreads widen, and bonds rally simultaneously, the market regime has shifted. Positions entered during risk-on conditions get destroyed in risk-off. Speed of recognition = survival.
Action: When 2+ of the following trigger: VIX >25, HY spreads widen >50bps in a week, 10Y yield drops >15bps in a day → sell all scout positions, tighten all stops to 1%.

**#19: Failed Breakout — Price Reverses Back Below Resistance**
Type: Technical
Priority: HIGH
Mechanism: You bought the breakout above resistance. Price pushed through, then fell back below within 2 sessions. The breakout failed. Failed breakouts become powerful moves in the opposite direction.
Action: If price closes back below the breakout level, exit immediately. Don't give it "one more day." Failed breakouts accelerate downward as breakout buyers become trapped longs.

**#20: Bid Disappearing — Level 2 Shows Thin Support**
Type: Microstructure
Priority: MEDIUM
Mechanism: If you're watching Level 2 and see bids pulling away (order book thinning below current price), market makers and institutions are stepping back. When the floor disappears, the next leg is down.
Action: If bid depth drops to <50% of normal while your position is flat/red, tighten stop to -0.5% from current price.

**#21: Dark Pool Distribution — Large Blocks Hitting Bid**
Type: Microstructure
Priority: HIGH
Mechanism: Large block prints (>$500K) hitting the bid indicate institutional selling. If you see 3+ large blocks hit the bid in an hour on your position, someone is distributing. Don't be the bag they're handing off.
Action: On 3+ bid-side blocks in an hour, sell 50% immediately. Trail the rest at 1%.

**#22: Options Market Warning — Put Volume Spike**
Type: Derivatives
Priority: MEDIUM
Mechanism: When put volume on your stock spikes to >3x the average daily put volume, informed traders are buying protection. They may be hedging or making directional bets on a decline. The options market often leads the equity market.
Action: When put volume exceeds 3x average, tighten stops. If combined with declining price, exit 50%.

**#23: Insider Selling Cluster**
Type: Fundamental
Priority: HIGH
Mechanism: When 3+ insiders sell within the same week, they're signaling collectively that the stock is overvalued relative to their private knowledge. One insider selling = normal diversification. Three = conviction that price is too high.
Action: On insider selling clusters (3+ in a week), exit or reduce by 50% regardless of technical picture. Insiders know their business better than your chart.

**#24: Analyst Downgrade from Buy to Sell**
Type: Fundamental
Priority: MEDIUM
Mechanism: A downgrade from Buy all the way to Sell (skipping Hold) is rare and signals a dramatic thesis change. The analyst's models blew up. Price targets get slashed 30%+. Institutional clients act on these immediately.
Action: On a multi-notch downgrade (Buy→Sell or Overweight→Underweight), sell at market. Don't wait for "the market to absorb it."

**#25: Earnings Miss + Guidance Cut (Double Negative)**
Type: Event
Priority: ABSOLUTE
Mechanism: Missing earnings AND cutting guidance is the worst fundamental combo. It means the past was worse than expected AND the future will be too. These stocks drop 10-30% and rarely bounce quickly.
Action: If your position misses earnings AND cuts guidance, sell at the open. Do not average down. Do not "wait for support." The knife is still falling.

**#26: Stop Run Recovery Failure**
Type: Technical
Priority: MEDIUM
Mechanism: Price dips below a key level (your stop area), triggering stops, then fails to recover above that level within 30 minutes. This means the stop run wasn't just a wick — real sellers showed up. The support is genuinely broken.
Action: If price breaks below support, bounces, but then fails to reclaim the level, exit on the second failure. First break might be a stop hunt. Second break is real.

**#27: Friday Afternoon Close — Swing Risk**
Type: Calendar
Priority: MEDIUM
Mechanism: Holding over the weekend exposes you to 64 hours of uncontrollable risk (geopolitics, earnings, news). If a position is only marginally profitable or you have low conviction, exiting Friday afternoon reduces weekend gap risk.
Action: On Friday at 3:00 PM, review all positions. Exit any scout positions that aren't clearly trending. Tighten trailing stops on everything else to 1%.

**#28: Liquidity Dry-Up — Volume Drops >60% from Entry Day**
Type: Microstructure
Priority: MEDIUM
Mechanism: If volume on your position drops >60% from when you entered, liquidity is disappearing. The move that attracted you has lost interest. Exiting a low-volume position is harder — wider spreads, more slippage.
Action: If trailing 3-day average volume drops below 40% of entry-day volume, exit within 2 days. Don't get trapped in a position you can't sell quickly.

**#29: Opportunity Cost — Better Setup Elsewhere**
Type: Portfolio
Priority: MEDIUM
Mechanism: Capital in a flat or slowly decaying position is capital NOT in a new high-conviction setup. If your factor engine scores a new opportunity at 8/10 but you have no cash because you're holding three 5/10 positions, the math is obvious.
Action: When a new 8+/10 setup appears and you're >80% deployed, cut your lowest-conviction current position to fund it. Upgrade constantly.

**#30: Drawdown From Peak — Position Down 50% from Its Best**
Type: Mechanical
Priority: HIGH
Mechanism: If a position that was once up 10% is now only up 5% (gave back 50% of gains), it's telling you the move is over. Protecting profits is not about maximizing — it's about not turning winners into losers.
Action: If a position gives back more than 50% of its peak unrealized gain, exit. A stock that was +$500 and is now +$250 is warning you it's headed to $0 or worse.

---

## ROUND 2: Technical & Price Action Exits (31–60)
*What the chart is telling you about when the move is over.*

**#31: Death Cross (50-Day Crosses Below 200-Day)**
Type: Technical
Priority: MEDIUM
Mechanism: The death cross signals a long-term trend change from bullish to bearish. While lagging, it captures major regime shifts. Positions held through death crosses suffer average drawdowns of 15-20%.
Action: On a death cross, exit all non-conviction positions in that name. Conviction positions get 1% trailing stops. Don't fight the primary trend.

**#32: Close Below 200-Day Moving Average**
Type: Technical
Priority: HIGH
Mechanism: The 200-day MA is the line between bull and bear for institutional investors. Many funds have mandates requiring them to reduce exposure when stocks close below their 200-day. You don't want to hold when institutions are forced sellers.
Action: On the first daily close below the 200-day MA, reduce by 50%. On a second consecutive close below, exit fully.

**#33: Bearish Engulfing Candle on High Volume**
Type: Technical
Priority: MEDIUM
Mechanism: A bearish engulfing candle (open above prior close, close below prior open) on above-average volume is one of the most reliable reversal signals. It says: buyers tried, sellers overwhelmed them.
Action: On a bearish engulfing candle with >1.5x average volume, sell 50%. If the next candle also closes red, exit fully.

**#34: Evening Star / Three Black Crows**
Type: Technical
Priority: MEDIUM
Mechanism: Three consecutive bearish candles after an uptrend (three black crows) or the evening star reversal pattern signal that selling pressure is sustained, not just a one-day dip. The trend has reversed.
Action: Exit on the close of the third consecutive red candle if each closes near its low. The pattern is strongest when each candle's close is lower than the prior candle's low.

**#35: MACD Bearish Cross Below Zero Line**
Type: Technical
Priority: MEDIUM
Mechanism: MACD crossing bearish (signal line crossing above MACD line) while BOTH are below zero = downtrend confirmed and accelerating. Bullish MACD crosses below zero are weak; bearish crosses below zero are strong.
Action: If MACD crosses bearish while below zero on the daily chart, exit. Don't try to catch a bounce — momentum is decisively negative.

**#36: Bollinger Band Breakdown (Close Below Lower Band)**
Type: Technical
Priority: MEDIUM
Mechanism: A close below the lower Bollinger Band means the stock is trading >2 standard deviations below its mean. While this can be a bounce setup, in a downtrend it signals acceleration. Context matters: downtrend + BB break = run; uptrend + BB break = bounce.
Action: In a downtrending stock (below 50-day MA), a close below the lower BB = exit. In an uptrending stock, it's a potential add point.

**#37: Volume Profile Gap Down — Falling Through Air**
Type: Technical
Priority: HIGH
Mechanism: Volume profile shows where most trading occurred. If price drops into a volume gap (area with very little historical trading), there's no support until the next high-volume node. Price falls through "air pockets" rapidly.
Action: If price enters a low-volume zone below a high-volume node, exit immediately. There's no natural buying support until the next volume cluster, which could be 5-10% lower.

**#38: Anchored VWAP from Catalyst Broken**
Type: Technical
Priority: HIGH
Mechanism: The VWAP anchored from the catalyst that made you buy represents the average cost of everyone who bought for the same reason. When price breaks below this VWAP, the average catalyst buyer is losing money. They'll sell, creating more pressure.
Action: When price closes below the anchored VWAP from your entry catalyst, the catalyst thesis is being unwound. Exit.

**#39: Rising Wedge / Ascending Triangle Breakdown**
Type: Technical
Priority: MEDIUM
Mechanism: A rising wedge (higher highs and higher lows, converging) typically resolves with a breakdown. Ascending triangles with declining volume also tend to fail. These are "fake strength" patterns — price is rising but conviction is declining.
Action: On a breakdown below the lower trendline of a rising wedge, exit immediately. Target is typically the base of the wedge.

**#40: Head and Shoulders Completion (Neckline Break)**
Type: Technical
Priority: HIGH
Mechanism: The head and shoulders is the most reliable reversal pattern in technical analysis (~75% success rate). When the neckline breaks, the measured move target equals the distance from head to neckline. Institutional algorithms trade this mechanically.
Action: If your position completes a head and shoulders pattern and breaks the neckline, exit on the break. Don't wait for a retest — many don't get one.

**#41: ADX Declining from Above 40 (Trend Exhaustion)**
Type: Technical
Priority: MEDIUM
Mechanism: ADX above 40 = strong trend. ADX declining from above 40 = the trend is losing steam. This doesn't mean reversal immediately, but it means the easy money in the trend is done. Choppy price action follows.
Action: When ADX peaks above 40 and starts declining, take profits on 50% of the position. The trend continuation bets get harder from here.

**#42: Parabolic SAR Flip**
Type: Technical
Priority: MEDIUM
Mechanism: Parabolic SAR flipping from below price (bullish) to above price (bearish) is a mechanical trend-following exit signal. It accelerates with the trend, so it exits quickly when momentum reverses.
Action: When SAR dots flip above price on the daily chart, exit. Simple, mechanical, removes emotion.

**#43: Fibonacci Extension Reached (1.618 or 2.618)**
Type: Technical
Priority: MEDIUM
Mechanism: Fibonacci extensions measure where trends typically exhaust. 1.618 is a common profit target; 2.618 is the max extension. Moves that reach these levels have "fulfilled their measured move" and often reverse or consolidate.
Action: Take 50% profit at the 1.618 extension. Exit fully at 2.618 or if any reversal candle prints at these levels.

**#44: Gap Fill Completion**
Type: Technical
Priority: LOW
Mechanism: Stocks that gap up tend to eventually fill that gap (return to the pre-gap price). If your position gapped up on entry and price is now filling back toward the gap level, the move is unwinding.
Action: If price fills >75% of the gap that triggered your entry, exit. The gap enthusiasm is gone.

**#45: Double Top / Triple Top Formation**
Type: Technical
Priority: HIGH
Mechanism: Price tests the same high 2-3 times and fails each time = double/triple top. Each failure confirms sellers at that level. The probability of breaking through decreases with each attempt. If it couldn't break on 3 tries, it won't.
Action: After a failed second test of a high, sell 50%. After a third test fails, exit fully. The neckline break often accelerates the decline.

**#46: Bearish Island Reversal**
Type: Technical
Priority: HIGH
Mechanism: Price gaps up, trades above the gap for 1-3 days, then gaps back down below the initial gap. The island of trading above is "stranded" — everyone who bought there is now trapped. One of the most bearish patterns.
Action: On an island reversal, exit immediately on the gap down. This pattern has a >80% follow-through rate to the downside.

**#47: Lower High Confirmed (Trend Shift)**
Type: Technical
Priority: MEDIUM
Mechanism: In an uptrend, the first lower high is a warning. The first lower low confirms the trend has changed. Most traders wait for both; by then they've given back significant gains.
Action: On the first confirmed lower high (price bounces but doesn't reach the prior high), reduce by 50%. On a lower low, exit fully.

**#48: On-Balance Volume (OBV) Divergence**
Type: Technical
Priority: MEDIUM
Mechanism: Price making new highs while OBV makes lower highs = distribution. Someone is selling into the rally. OBV divergence is one of the most reliable volume-based exit signals because it's hard to fake real money flow.
Action: When OBV diverges from price for 5+ days, begin exiting. The smart money is already gone.

**#49: Intraday VWAP Rejection x3**
Type: Technical
Priority: MEDIUM
Mechanism: If your position tests VWAP from below 3 times intraday and gets rejected each time, institutions are selling every bounce to fair value. Three rejections = the day is done for this name.
Action: After the third VWAP rejection, exit the intraday position. Don't hope for a fourth attempt — the sellers are committed.

**#50: Relative Weakness vs Sector (Lagging)**
Type: Technical
Priority: MEDIUM
Mechanism: If your stock is red while its sector ETF is green, something is wrong with YOUR stock specifically. Sector-level strength should lift all boats. If your name is sinking while the sector floats, there's a stock-specific problem.
Action: When your position underperforms its sector ETF by >2% for 2 consecutive days, exit. The market is telling you something about this specific company.

**#51: Opening Range Breakdown**
Type: Technical
Priority: MEDIUM
Mechanism: If the first 15-minute candle sets the high of the day and price breaks below the opening range low, the session is bearish for this name. 70% of the time, opening range breakdowns lead to further downside.
Action: If holding a day trade and price breaks below the 15-minute opening range low with volume, exit. The day's direction is decided.

**#52: Close Below Prior Day's Low**
Type: Technical
Priority: MEDIUM
Mechanism: A close below the prior day's low expands the range downward and traps yesterday's buyers. It signals that sellers have taken control and the prior day's support is broken.
Action: On a close below the prior day's low (not just a wick), tighten stop to -1% from the close. Two consecutive closes below prior day's lows = exit.

**#53: Key Support Level Break (Prior Swing Low)**
Type: Technical
Priority: HIGH
Mechanism: Prior swing lows are natural support. When a stock breaks below a swing low that held previously, the "staircase" of higher lows is broken. Every buyer who bought the prior dip is now underwater.
Action: Exit when price closes below the most recent swing low. This is where "buy the dip" becomes "the trend has changed."

**#54: High-Volume Reversal Candle (Shooting Star / Gravestone)**
Type: Technical
Priority: MEDIUM
Mechanism: A shooting star (long upper wick, small body, at the top of an uptrend) on high volume = buyers pushed higher but sellers overwhelmed them and pushed price back down. The upper wick represents rejected higher prices.
Action: On a shooting star with >2x average volume at or near the high of a trend, sell 50%. If the next candle is also red, exit fully.

**#55: Tick Chart Divergence (Lower Highs on Tick)**
Type: Microstructure
Priority: LOW
Mechanism: On tick charts (every trade), lower highs in the tick count while price pushes higher = fewer participants driving the move. The rally is getting thinner. Professional day traders use this for precise exit timing.
Action: On day trades, exit when tick chart highs diverge from price highs. Precision timing for intraday exits.

**#56: After-Hours Bad News on Holding**
Type: Event
Priority: HIGH
Mechanism: When bad news breaks after hours on a stock you hold (downgrade, investigation, product recall, key executive departure), the AH price reaction understates the opening damage. Pre-market sellers pile in.
Action: If your holding has material negative AH news, sell at the first pre-market opportunity or at the open. Don't wait for "the market to sort it out."

**#57: Sector ETF Death Cross**
Type: Technical
Priority: MEDIUM
Mechanism: When the sector ETF your stock belongs to prints a death cross, the entire sector is entering a bearish regime. Individual stocks rarely escape sector gravity.
Action: When the sector ETF's 50-day crosses below its 200-day, exit or significantly reduce all positions in that sector within 5 days.

**#58: Index Breaks Key Support (SPY Below 200-Day)**
Type: Macro/Technical
Priority: HIGH
Mechanism: When SPY closes below its 200-day MA, the market's primary trend has shifted bearish. 70% of stocks follow the index. Your position is swimming against a tidal wave.
Action: When SPY closes below 200-day MA, reduce all long exposure by 50%. Go to maximum defensive posture. This is not a dip to buy — it's a regime change.

**#59: Multiple Timeframe Divergence (Daily Bearish, Weekly Still Bullish)**
Type: Technical
Priority: MEDIUM
Mechanism: When the daily chart turns bearish but the weekly is still bullish, the stock is entering a pullback within an uptrend. The question is: is it a dip or a reversal? The weekly chart answers that in 1-2 weeks.
Action: On daily bearish signal within weekly uptrend, reduce by 50% and set a stop at the weekly support level. If weekly also turns, exit fully.

**#60: Realized Volatility Spike (>2x 30-Day Average)**
Type: Quantitative
Priority: MEDIUM
Mechanism: When a stock's realized volatility doubles from its 30-day average, the regime has changed from "stable trend" to "volatile mess." Trend-following stops get whipsawed in high-vol regimes.
Action: When realized vol doubles, widen stops slightly (to avoid whipsaw) but REDUCE position size by 50%. Your per-share risk stays constant but total exposure drops.

---

## ROUND 3: Fundamental & Earnings Exits (61–90)
*When the business story changes — exit signals from the fundamentals, not just the chart.*

**#61: Earnings Miss — Revenue AND EPS Below Estimates**
Type: Fundamental
Priority: HIGH
Mechanism: A double miss (revenue + EPS) means demand is weaker than expected AND margins are worse. The full story is deteriorating. These stocks average -7% on the report day and -12% over the next 30 days.
Action: Exit on the open following a double miss. No averaging down.

**#62: Guidance Cut — Q1 or Full Year Lowered**
Type: Fundamental
Priority: HIGH
Mechanism: Management lowering guidance is the strongest sell signal from fundamentals. They know their business — if they're warning you, believe them. Stocks that cut guidance underperform by 15% over 6 months.
Action: Exit immediately on guidance cuts. Even if the stock doesn't drop much initially — the estimate revisions cascade over the next 2-4 weeks.

**#63: Gross Margin Compression >200bps**
Type: Fundamental
Priority: MEDIUM
Mechanism: Gross margin compression means the company is losing pricing power or facing input cost inflation. This is the QUALITY of earnings declining. Revenue can grow but if margins compress, earnings eventually fall.
Action: Exit growth stocks that show >200bps gross margin compression QoQ. For value stocks, tighten stops. NVDA's 75%→71% margin drop was an early warning.

**#64: Revenue Deceleration (YoY Growth Rate Declining)**
Type: Fundamental
Priority: MEDIUM
Mechanism: Decelerating revenue growth — even if still positive — often precedes multiple compression. A company growing 30% that decelerates to 20% gets repriced lower, even though 20% is still "good." The market pays for acceleration.
Action: When YoY revenue growth rate declines for 2 consecutive quarters, reduce position by 50%. The market reprices deceleration harshly.

**#65: Free Cash Flow Turns Negative**
Type: Fundamental
Priority: HIGH
Mechanism: A profitable company that starts burning cash is either investing aggressively (bullish) or losing operational control (bearish). Without a clear investment narrative, negative FCF means the business model is breaking.
Action: If FCF turns negative without an announced investment cycle (new factory, acquisition integration), exit. Cash burn without purpose = exit.

**#66: Debt Covenant Breach Risk (Leverage Ratio Spiking)**
Type: Fundamental
Priority: HIGH
Mechanism: When debt/EBITDA rises toward covenant limits (often 4-5x), the company faces restricted distributions, higher interest rates, or forced asset sales. Equity holders get wiped when covenants breach.
Action: Exit when net debt/EBITDA rises above 4x for companies with significant debt. Monitor quarterly. This leads to credit downgrades.

**#67: Key Customer Loss**
Type: Fundamental
Priority: ABSOLUTE
Mechanism: If a company with >20% revenue from one customer loses that customer, it's a 20%+ revenue cliff. The stock will reprice immediately to the new revenue base.
Action: On news of key customer loss or non-renewal, exit immediately at market. The repricing is violent and immediate.

**#68: CFO Resignation**
Type: Fundamental
Priority: HIGH
Mechanism: CFOs don't resign in the middle of a good story. They resign when they see problems coming or disagree with how management is handling the numbers. CFO departures preceded accounting scandals at Enron, WorldCom, and dozens of smaller companies.
Action: On unexpected CFO resignation (not planned succession), exit 50-100% depending on other factors. Especially exit if the company also has high accruals or unusual accounting.

**#69: Auditor Change (Red Flag)**
Type: Fundamental
Priority: HIGH
Mechanism: Switching auditors is one of the strongest accounting red flags. Companies change auditors when they want someone less strict, or when the auditor refuses to sign off on questionable practices.
Action: On an unexpected auditor change (especially from Big 4 to smaller firm), exit within a week. This precedes restatements and SEC investigations.

**#70: Inventory Build-Up (Inventory Growing Faster Than Revenue)**
Type: Fundamental
Priority: MEDIUM
Mechanism: When inventory grows faster than revenue for 2+ quarters, the company is building up unsold goods. This leads to markdowns, margin compression, and eventual write-offs. Classic warning sign in retail and manufacturing.
Action: Track inventory/revenue ratio. Two consecutive quarters of rising ratio = reduce or exit. Especially dangerous in seasonal businesses.

**#71: Same-Store Sales Decline (Comps Negative)**
Type: Fundamental
Priority: HIGH
Mechanism: Negative comps in retail/restaurants means existing locations are losing traffic or ticket size. New store growth can't compensate forever. Negative comps for 2+ quarters usually leads to store closures and restructuring.
Action: Exit retail/restaurant positions on the second quarter of negative comps.

**#72: Credit Rating Downgrade**
Type: Fundamental
Priority: HIGH
Mechanism: A credit downgrade increases borrowing costs and can trigger covenant issues. For investment-grade companies, a downgrade from BBB to BB ("fallen angel") forces many institutional holders to sell, creating a cascade.
Action: On a credit downgrade, exit or reduce. On a fallen angel downgrade (IG to HY), exit immediately — forced selling is incoming.

**#73: Short Interest Spike (>5% Increase in Two Weeks)**
Type: Fundamental
Priority: MEDIUM
Mechanism: Rapidly rising short interest means informed short sellers are making a thesis bet against the company. While shorts can be wrong, a sudden increase suggests new negative information is circulating among professionals.
Action: When short interest jumps >5% of float in two weeks, review your thesis. If you can't articulate why the shorts are wrong, reduce by 50%.

**#74: Customer Churn Rate Increasing (SaaS)**
Type: Fundamental
Priority: HIGH
Mechanism: For SaaS companies, rising churn means customers are leaving. Net revenue retention below 100% means existing customers are paying less than before. This is the death metric for subscription businesses.
Action: When net revenue retention drops below 100% (or gross churn rises >15% annualized), exit. The subscription flywheel has reversed.

**#75: Patent Cliff / Drug Expiration**
Type: Fundamental
Priority: HIGH
Mechanism: For pharma, the expiration of a key patent exposes revenue to generic competition. Revenue can drop 80%+ on a blockbuster drug going generic. The market begins pricing this 1-2 years before expiration.
Action: Exit pharma positions when the patent cliff is within 12 months and no adequate pipeline replacement exists.

**#76: Regulatory Action (FDA Warning, SEC Investigation)**
Type: Event/Fundamental
Priority: ABSOLUTE
Mechanism: FDA warning letters, SEC investigations, or antitrust actions signal existential threats. Even if the company prevails, the legal costs, management distraction, and uncertainty compress multiples for years.
Action: On news of regulatory action, exit at market. Don't try to "wait it out" — the uncertainty alone justifies selling.

**#77: Competitive Disruption (New Entrant Pricing Below Cost)**
Type: Fundamental
Priority: MEDIUM
Mechanism: When a well-funded competitor enters your position's market with pricing 30%+ below the incumbent, margin compression is coming. Even if the incumbent has better product, the pricing pressure forces a response.
Action: When a major competitor enters with disruptive pricing, review the position. If the incumbent can't match without destroying margins, exit within 30 days.

**#78: Management Selling Equity Compensation Aggressively**
Type: Fundamental
Priority: MEDIUM
Mechanism: When executives sell stock options/RSUs faster than they vest (pre-planned 10b5-1 plans modified to accelerate sales), they're racing to get liquidity. This is subtler than open-market insider selling but equally informative.
Action: Track 10b5-1 plan modifications via SEC filings. If executives accelerate vesting sales, reduce position. Especially bearish when multiple executives do it simultaneously.

**#79: Accounts Receivable Growing Faster Than Revenue**
Type: Fundamental
Priority: MEDIUM
Mechanism: When AR grows faster than revenue, the company is booking sales that haven't been collected. This could mean looser credit terms (desperate for revenue), or channel stuffing (recognizing revenue prematurely). Both lead to write-offs.
Action: When AR/revenue ratio rises for 2 consecutive quarters, investigate why. If no clear explanation, reduce by 50%.

**#80: Operating Cash Flow Divergence from Net Income**
Type: Fundamental
Priority: HIGH
Mechanism: When net income grows but operating cash flow declines, the earnings are low quality — driven by accounting, not cash. This is the accruals anomaly. High accruals (income >> cash flow) precede downward revisions 80% of the time.
Action: When OCF diverges negatively from net income for 2+ quarters, exit. The earnings are a mirage.

**#81: Peer Group Decline (Sector Earnings Revisions Down)**
Type: Fundamental
Priority: MEDIUM
Mechanism: If 3+ companies in the same industry report weak results or cut guidance, the problem is sector-wide. Your stock hasn't reported yet but the probability of missing just went up dramatically.
Action: When 3+ peers in the same sub-industry miss or cut guidance, reduce exposure. The sector tide is going out.

**#82: Buy-Side Consensus Breaks (Large Fund Exits)**
Type: Fundamental
Priority: MEDIUM
Mechanism: When a well-known buy-side firm exits a position (visible in 13F filings), other buy-side firms often follow within a quarter. Institutional herding works on both the buy AND sell side.
Action: When 2+ top-20 holders exit (per 13F), reduce. The smart money is changing their mind.

**#83: Dividend Cut or Suspension**
Type: Fundamental
Priority: ABSOLUTE
Mechanism: Companies cut dividends only when cash flow is genuinely threatened. It's a last resort because it destroys investor confidence. Stocks that cut dividends drop 20-30% on average and take years to recover.
Action: Exit on a dividend cut or suspension. No exceptions. The cash flow crisis that triggers the cut is almost always deeper than initially disclosed.

**#84: Pricing Power Loss (ASP Declining)**
Type: Fundamental
Priority: MEDIUM
Mechanism: Average Selling Price declining while volume grows = the company is cutting prices to maintain volume. This is a sign of commoditization and increasing competition. Margin compression follows within 1-2 quarters.
Action: When ASP declines >5% YoY without a clear volume-based strategy narrative, reduce. Pricing power is the moat — losing it means the moat is failing.

**#85: Operating Margin Below Peer Average**
Type: Fundamental
Priority: LOW
Mechanism: A company with operating margins significantly below peers is either less efficient or competing on price. Both situations make it vulnerable in a downturn — it's the weakest gazelle.
Action: For positions where operating margin is in the bottom quartile of its peer group and declining, exit in favor of the sector leader.

**#86: Working Capital Crisis (Current Ratio <1)**
Type: Fundamental
Priority: HIGH
Mechanism: Current ratio below 1 means the company can't cover its short-term obligations with short-term assets. It needs to borrow, dilute, or sell assets. This is a liquidity crisis in slow motion.
Action: If current ratio drops below 1 AND is declining, exit. The company is approaching a forced capital raise (dilutive) or worse.

**#87: Backlog Declining (Industrial/Defense)**
Type: Fundamental
Priority: MEDIUM
Mechanism: For industrial and defense companies, backlog is the best forward indicator. Declining backlog = future revenue will decline. It's a leading indicator by 2-4 quarters.
Action: When book-to-bill drops below 1.0 (more deliveries than new orders) for 2+ quarters, reduce industrial/defense positions.

**#88: Customer Satisfaction Decline (NPS/Reviews)**
Type: Fundamental
Priority: LOW
Mechanism: Declining NPS scores or product review ratings often precede revenue declines by 2-3 quarters. Customers are getting unhappy before they leave. This is a very early warning signal.
Action: Use as a thesis check, not a hard exit signal. If NPS is declining AND financial metrics are softening, exit. NPS alone is too early.

**#89: Executive Guidance Language Shift (Word Analysis)**
Type: Fundamental
Priority: MEDIUM
Mechanism: When management shifts from specific guidance ("We expect 15% growth") to vague guidance ("We're cautiously optimistic about the trajectory"), they're sandbagging or losing visibility. The language change precedes the numbers change.
Action: Analyze earnings call transcripts for confidence language. Shift from specific → vague = reduce by 25%. Combine with other factors.

**#90: Share Dilution Acceleration**
Type: Fundamental
Priority: MEDIUM
Mechanism: When share count increases >3% annually through stock-based compensation or secondary offerings, existing shareholders are being diluted. Per-share metrics get inflated by revenue growth but the actual ownership shrinks.
Action: When dilution exceeds 3% annually AND revenue growth doesn't significantly exceed it, the company is paying employees with your equity. Reduce or exit.

---

## ROUND 4: Market Regime & Macro Exits (91–120)
*When the macro environment shifts — the "tide going out" signals.*

**#91: VIX Breaks Above 25 — Elevated Fear**
Type: Macro
Priority: HIGH
Mechanism: VIX above 25 means options market is pricing in significant risk. Historical data shows 60% of trading days with VIX >25 are down days. Your long positions face a hostile environment.
Action: At VIX >25, tighten all stops to 1.5%. Exit all scout positions. Only conviction holds remain.

**#92: VIX Backwardation Onset**
Type: Macro
Priority: HIGH
Mechanism: When the VIX term structure flips from contango to backwardation (near-term > long-term), the market is pricing in IMMEDIATE risk. This is panic — not just concern. Markets in backwardation crash or bottom within days.
Action: At backwardation onset, close 75% of all long positions. The other 25% get max-tight trailing stops. This is the fire alarm, not a drill.

**#93: Credit Spreads Blow Out (HY OAS +100bps in a Week)**
Type: Macro
Priority: HIGH
Mechanism: High yield credit spreads widening 100+ bps in a week = the credit market is seizing up. Credit leads equity. When companies can't borrow, they can't grow, they can't buy back stock, and they start defaulting.
Action: When HY OAS widens >100bps in a week, go to maximum defensive. Exit all but the most defensive longs. This preceded every major equity crash in the last 30 years.

**#94: Fed Hawkish Surprise — Rate Expectations Shift**
Type: Macro
Priority: HIGH
Mechanism: When Fed Funds futures suddenly price in additional rate hikes (or remove expected cuts), it reprices the entire discount rate for all risk assets simultaneously. Equities, especially growth/tech, fall as the "risk-free" alternative becomes more attractive.
Action: On a hawkish Fed surprise (>25bps shift in rate expectations), reduce growth/tech exposure immediately. Rotate to value/financials or cash.

**#95: Dollar Spike (DXY >105 or +2% Weekly)**
Type: Macro
Priority: MEDIUM
Mechanism: A surging dollar crushes multinationals (earnings translation), emerging markets (debt servicing), and commodities (dollar-denominated). It's the "anti-everything" trade.
Action: When DXY spikes >2% in a week or breaks above 105, reduce commodity, multinational, and EM exposure. Favor domestic small-caps if staying long.

**#96: Bond Market Flash Signal (10Y Moves >15bps in a Day)**
Type: Macro
Priority: HIGH
Mechanism: A 15+ bps move in the 10Y Treasury in a single day is a seismic event. It reprices mortgages, corporate debt, and equity discount rates. Large bond moves cascade into all other markets within hours.
Action: On a >15bps 10Y move, pause all new entries for 24 hours. If the move is HIGHER yields, reduce growth/tech. If lower, reduce financials/value.

**#97: Yen Carry Trade Unwind (USD/JPY Drops >2% Weekly)**
Type: Macro
Priority: HIGH
Mechanism: The yen carry trade is one of the largest leveraged bets in global markets. When JPY strengthens sharply, carry trades unwind — funds must sell risk assets to repay yen-denominated debt. This triggered the August 2024 global selloff.
Action: On sharp yen strengthening (>2% weekly), reduce all risk exposure by 50%. This is a global deleveraging event.

**#98: Geopolitical Escalation (Military, Sanctions)**
Type: Macro
Priority: HIGH
Mechanism: Military escalation or new sanctions regimes create uncertainty that suppresses risk appetite. Oil spikes on Middle East risk. European stocks sell off on Russia risk. Asian markets drop on Taiwan risk.
Action: On geopolitical escalation, immediately go long gold/defense and reduce broad equity exposure. Don't try to trade around the headline — reduce risk and wait for clarity.

**#99: Liquidity Crunch (Bank Reserve Drop)**
Type: Macro
Priority: HIGH
Mechanism: When bank reserves at the Fed decline sharply (from QT or Treasury general account changes), market liquidity dries up. This manifests as wider bid-ask spreads, higher volatility, and declining asset prices across the board.
Action: Track Fed reserve balances weekly. When reserves drop >$100B in a month, reduce all positions. The market runs on liquidity — when it drains, everything suffers.

**#100: Recession Confirmation (2 Consecutive Negative GDP Quarters)**
Type: Macro
Priority: HIGH
Mechanism: While technically debated, two consecutive quarters of negative GDP growth = recession. Corporate earnings fall, unemployment rises, consumer spending declines. Equities typically bottom 6-9 months into a recession.
Action: On recession confirmation, shift to maximum defensive. Reduce all cyclical/growth longs. Overweight cash, bonds, utilities, healthcare.

**#101: Global M2 Contraction**
Type: Macro
Priority: MEDIUM
Mechanism: When the combined balance sheets of the Big 4 central banks are shrinking (QT globally), liquidity is being withdrawn from the system. This is the master variable — all risk asset prices are a function of liquidity.
Action: When global M2 growth turns negative, reduce risk asset exposure. This is a slow-moving but extremely powerful signal with a 6-month lead.

**#102: Oil Shock (>40% Spike in <6 Months)**
Type: Macro
Priority: HIGH
Mechanism: Sudden oil spikes act as a tax on consumers and compress margins. Most recessions since 1970 were preceded by an oil shock. Transportation, airlines, and consumer discretionary get crushed.
Action: On an oil shock, exit energy consumers (airlines, trucking, retail) and reduce broad equity exposure. Energy producers benefit, but the overall market impact is negative.

**#103: Emerging Market Currency Crisis**
Type: Macro
Priority: MEDIUM
Mechanism: When major EM currencies collapse (>10% monthly), it signals capital flight from risk assets globally. EM crises often start as local events but become contagion through dollar-denominated debt and trade linkages.
Action: On EM currency crisis, reduce EM exposure and monitor for contagion. If it spreads to 3+ countries, reduce all risk exposure.

**#104: Inflation Surprise (CPI >50bps Above Consensus)**
Type: Macro
Priority: HIGH
Mechanism: A significant inflation surprise reprices everything — rate expectations, growth expectations, and consumer confidence all shift simultaneously. Growth stocks get hit hardest (higher discount rates).
Action: On hot CPI (>50bps above consensus), sell growth/tech immediately. Rotate to commodities, TIPS, and short-duration positions.

**#105: Consumer Confidence Collapse (>20 Point Drop)**
Type: Macro
Priority: MEDIUM
Mechanism: A sudden drop in consumer confidence (Michigan or Conference Board) signals that the consumer is retrenching. Since consumption is 70% of GDP, this leads economic decline by 2-3 months.
Action: On a >20 point confidence drop, reduce consumer discretionary and retail exposure. Shift to staples and healthcare.

**#106: Bank Failure / Financial Stress Event**
Type: Macro
Priority: ABSOLUTE
Mechanism: A bank failure (like SVB in 2023) creates contagion fear. Even if your holdings aren't banks, the credit tightening that follows a bank failure restricts lending to all businesses. It's a systemic risk event.
Action: On a bank failure, immediately exit all financial sector positions and reduce overall by 50%. Go long gold and long-dated Treasuries.

**#107: MOVE Index Spike >130**
Type: Macro
Priority: HIGH
Mechanism: MOVE index (bond market volatility) above 130 indicates extreme bond market stress. Bond market stress cascades into equity markets through margin calls, portfolio rebalancing, and credit tightening.
Action: On MOVE >130, reduce all equity exposure by 50%. The bond market is the dog; the equity market is the tail.

**#108: Copper Crash (>15% Monthly Decline)**
Type: Macro
Priority: MEDIUM
Mechanism: Dr. Copper doesn't lie. A copper crash signals global industrial demand is falling off a cliff. This leads equity market declines by 1-3 months.
Action: When copper drops >15% in a month, exit all industrial and materials longs. Reduce broad equity exposure. The global economy is weakening.

**#109: Flash Crash / Circuit Breaker Event**
Type: Macro
Priority: ABSOLUTE
Mechanism: When market-wide circuit breakers trigger (7% SPX decline), the market has lost orderly functioning. Liquidity evaporates, bid-ask spreads blow out, and prices don't reflect fundamentals.
Action: During a circuit breaker event, do NOT panic sell into the halt. Wait for the reopen. Assess total portfolio exposure. If >50% deployed, reduce to 30%. These events often mark short-term bottoms, but the first bounce can be a trap.

**#110: Rate Inversion De-Steepening (Recession Arriving)**
Type: Macro
Priority: HIGH
Mechanism: The yield curve inverting is a warning. The curve UN-inverting (re-steepening) is the fire. Re-steepening means the Fed is cutting because the economy is weakening. The recession is arriving, not just threatened.
Action: When the 2s10s spread re-steepens from inversion, go maximum defensive. This is historically the START of the equity decline, not the end.

**#111: Sector-Specific Regulatory Risk (New Legislation)**
Type: Political
Priority: MEDIUM
Mechanism: New legislation targeting a specific sector (pharma pricing, tech antitrust, bank regulation) creates long-term headwinds. Even if the legislation takes years, the uncertainty compresses multiples immediately.
Action: When legislation targeting your sector gains serious momentum (committee vote, bipartisan support), reduce sector exposure by 25%.

**#112: Election Cycle Uncertainty (Within 3 Months of Election)**
Type: Political
Priority: LOW
Mechanism: The 3 months before a presidential election tend to be choppy as markets price in policy uncertainty. The direction depends on the candidates' policies (pro-business vs regulatory).
Action: Within 3 months of a major election, reduce position sizes by 20% and tighten stops. Volatility increases and trends become unreliable.

**#113: Tariff Escalation on Your Sector**
Type: Political
Priority: HIGH
Mechanism: New tariffs directly impact margins for importers and exporters. A 25% tariff on Chinese goods = 25% cost increase for companies sourcing from China. The market reprices immediately.
Action: On tariff escalation affecting your holdings, exit import-dependent positions immediately. The margin impact is calculable and significant.

**#114: Central Bank Surprise (Unexpected Rate Decision)**
Type: Macro
Priority: HIGH
Mechanism: When a major central bank does something unexpected (emergency cut, surprise hike, policy reversal), it signals that conditions are either much worse or much different than the market assumed. Surprise = mispricing.
Action: On a CB surprise, pause all trading for 24 hours. Let the market reprice. Then reassess all positions against the new macro reality.

**#115: Global Risk-Off Cascade (All Safe Havens Rallying)**
Type: Macro
Priority: HIGH
Mechanism: When gold, yen, Swiss franc, and US Treasuries all rally simultaneously, global investors are fleeing to safety. This is the broadest risk-off signal — it means the fear is not sector-specific, it's systemic.
Action: When all 4 safe havens rally on the same day, reduce all risk exposure by 50% or more. This is the "everything is selling" signal.

**#116: Margin Call Cascade (Broker-Dealer Stress)**
Type: Macro
Priority: ABSOLUTE
Mechanism: When reports of margin calls at major brokers emerge, forced liquidation is in progress. This creates indiscriminate selling — good stocks and bad stocks all sell together. Prices detach from fundamentals.
Action: During margin call cascades, reduce to 25% deployed maximum. Don't try to buy the dip — prices will go lower than fundamentals suggest before stabilizing.

**#117: Correlation Spike (>0.8 Average Cross-Stock)**
Type: Quantitative
Priority: MEDIUM
Mechanism: When cross-stock correlation exceeds 0.8, your "diversified" portfolio isn't diversified — it's one big bet. Every position moves together. A 10-position portfolio with 0.8 correlation behaves like 2-3 positions.
Action: On correlation >0.8, reduce to 3-4 uncorrelated positions max. Additional positions add risk, not diversification.

**#118: Smart Money Selling (Last Hour Weak)**
Type: Microstructure
Priority: MEDIUM
Mechanism: The Smart Money Index tracks last-hour volume vs first-hour volume. Institutional investors tend to trade in the last hour. When the last hour is consistently weak (selling) while the first hour is strong (retail buying), smart money is distributing to retail.
Action: When the Smart Money Index declines for 5+ consecutive days while the market rises, reduce exposure. Institutions are selling to retail.

**#119: ETF Outflows Exceeding 3% AUM Weekly**
Type: Flow
Priority: MEDIUM
Mechanism: When a sector ETF sees outflows exceeding 3% of AUM in a single week, institutional and advisor allocation decisions have turned against that sector. This creates persistent selling pressure.
Action: On >3% weekly ETF outflows in your sector, reduce all positions in that sector by 25%. Flows tend to persist for weeks.

**#120: Systematic Strategy De-Risking (CTA/Risk Parity)**
Type: Quantitative
Priority: MEDIUM
Mechanism: CTAs and risk parity funds manage trillions and trade mechanically. When volatility rises above their thresholds, they de-risk mechanically — selling $billions of equities regardless of fundamentals. This creates a self-reinforcing selling cascade.
Action: When volatility spike + falling equity trend aligns, expect CTA selling. Reduce positions ahead of the wave. CTA positioning data (from Goldman, JPM) lags by 1 day.

---

## ROUND 5: Portfolio Management & Behavioral Exits (121–150)
*The exits that prevent human (and AI) psychology from sabotaging good decisions.*

**#121: Revenge Trade Detection — Re-entering After Stop-Out**
Type: Behavioral
Priority: HIGH
Mechanism: After getting stopped out of a position, the urge to re-enter immediately is the strongest behavioral bias in trading. "It'll come back, I was just early." 70% of revenge re-entries lose money because the original thesis failed.
Action: 10-minute cooldown on the same ticker after any exit. After a stop-out, the ticker goes on a 24-hour blacklist. No exceptions.

**#122: Sunk Cost Trap — "I'm Already Down 8%, Might As Well Hold"**
Type: Behavioral
Priority: ABSOLUTE
Mechanism: The fact that you're already down is irrelevant to whether you should hold. The only question: "Would I enter this trade today at this price with this information?" If no, exit. Your entry price is ancient history.
Action: After every loss exceeds 5%, explicitly re-evaluate: "Would I buy this here?" If the answer isn't a clear yes, exit. The loss already happened.

**#123: Endowment Effect — Valuing What You Own More**
Type: Behavioral
Priority: MEDIUM
Mechanism: Humans (and AIs) value things they own more than things they don't. You'll hold a mediocre position because it's "yours" while ignoring a better opportunity because switching requires action. This is capital misallocation.
Action: Daily review: rank all positions by current factor score. If any position scores below 5/10 and a watchlist item scores above 7/10, make the swap. Don't let familiarity bias keep capital in inferior positions.

**#124: Anchoring — "But It Was $200 Last Week"**
Type: Behavioral
Priority: MEDIUM
Mechanism: Anchoring to past prices is irrational. A stock at $150 that was $200 last week isn't "cheap" — it's $150 because the market has new information. The prior price is irrelevant to future expected returns.
Action: Cover the "cost basis" column on your dashboard. Evaluate every position based on CURRENT factor score, not how much you've made/lost. Price paid is sunk.

**#125: Gambler's Fallacy — "It's Due for a Bounce"**
Type: Behavioral
Priority: HIGH
Mechanism: "It's dropped 5 days in a row, it HAS to bounce" — no it doesn't. Trends persist longer than you expect. A stock in a downtrend is more likely to fall further tomorrow than bounce. Probability doesn't reset.
Action: Never add to a losing position based on "it's due." Only add if the factor engine scores the entry ≥7/10 at current prices.

**#126: Portfolio Heat Check — Total Risk Exposure >50%**
Type: Portfolio
Priority: HIGH
Mechanism: "Portfolio heat" = sum of maximum loss across all positions (each position × its stop distance from current price). If total heat exceeds 50% of portfolio, a simultaneous stop-out across all positions would be catastrophic.
Action: Calculate portfolio heat daily. If >50%, close the position with the worst risk/reward ratio. Target heat of 25-35%.

**#127: Winner's Curse — Holding Winners Too Long**
Type: Behavioral
Priority: MEDIUM
Mechanism: Winners feel good. You don't want to sell them. But unrealized gains are unrealized — they're not real until you sell. Studies show individual investors hold winners 50% longer than optimal because selling a winner feels like "giving up."
Action: When a position hits 3x your initial risk target (entered with 2% stop, now up 6%), sell 50% and trail the rest. Take profits, not photos.

**#128: Confirmation Bias — Only Seeing Bull Case**
Type: Behavioral
Priority: MEDIUM
Mechanism: Once you own a position, you unconsciously filter for bullish information and dismiss bearish signals. Every positive analyst note confirms your genius; every red flag is "noise." This blinds you to legitimate exit signals.
Action: For every position held >5 days, actively search for the bear case. Read one bearish analysis. If the bear case is stronger than the bull case, exit.

**#129: Mean Reversion Expectation in a Trending Market**
Type: Behavioral
Priority: MEDIUM
Mechanism: In strongly trending markets, mean reversion thinking causes premature exits. "It's up 20%, it MUST come back to the mean." Trends can persist for months. Cutting winners early limits upside while holding losers limits downside capture.
Action: In strong trends (ADX >30), let winners run with trailing stops. Don't exit just because a move "feels extended." The trail protects you if the trend breaks.

**#130: Round Number Anchoring — Selling at $100/$200/$500**
Type: Behavioral
Priority: LOW
Mechanism: Humans anchor to round numbers. "I'll sell at $100." But $100 has no special significance — it's an arbitrary psychological level. Sometimes this creates self-fulfilling resistance, but often the right exit is at $97 or $103.
Action: Set exits based on factor scores and trailing stops, not round numbers. If your system says sell, sell — regardless of whether the price is "pretty."

**#131: Portfolio Rebalancing — Quarterly Review**
Type: Portfolio
Priority: MEDIUM
Mechanism: Over time, winning positions become oversized and losing positions become undersized. Without rebalancing, your portfolio drifts from its intended allocation. A quarterly review forces you to trim winners and cut dead weight.
Action: Every quarter, review all positions. Trim anything that's grown to >10% of portfolio. Cut anything that's been flat for 30+ days with no catalyst. Reallocate to highest-conviction ideas.

**#132: Cash Deployment Timer — Max 5 Days Without New Entry**
Type: Portfolio
Priority: MEDIUM
Mechanism: If you've been 40%+ cash for 5+ trading days, you're not cautious — you're paralyzed. The market provides opportunities daily. Cash above 40% for extended periods means your entry criteria are too strict or you're afraid.
Action: If cash exceeds 40% for 5 consecutive days, LOWER your entry threshold by 0.5 points on the factor engine. Deploy capital or acknowledge the market regime is genuinely hostile.

**#133: Scaling Out Protocol — Don't Exit All at Once**
Type: Portfolio
Priority: MEDIUM
Mechanism: Selling 100% of a winning position at one price is suboptimal. The market doesn't top at a single price — it distributes. Scaling out (25% at target 1, 25% at target 2, trail the rest) captures more of the move.
Action: At first profit target (2x risk), sell 25%. At second target (3x risk), sell 25%. Trail the remaining 50% with 1.5% trailing stop.

**#134: Dead Money Detection — No Movement for 10 Days**
Type: Portfolio
Priority: MEDIUM
Mechanism: A position that hasn't moved >1% in 10 trading days is dead money. It's not going up, it's not going down, and it's consuming capital that could be in a mover. Capital has an opportunity cost — dead money is the worst use of it.
Action: After 10 days of <1% total movement, exit and redeploy. If the stock wakes up later, you can re-enter. But don't pay the opportunity cost of waiting.

**#135: Loss Limit — 3 Consecutive Losing Trades on Same Thesis**
Type: Behavioral
Priority: HIGH
Mechanism: If you've been stopped out of 3 consecutive trades on the same thesis (e.g., "tech bounce," "NVDA reversal"), the thesis is wrong. Repeating a failed thesis is not persistence — it's stubbornness. Each loss is the market telling you no.
Action: After 3 consecutive losses on the same thesis, abandon it for 5 trading days. Re-evaluate with fresh eyes. If the data still supports it, re-enter. If not, move on.

**#136: Profit Target Hit — Pre-Defined Exit**
Type: Mechanical
Priority: HIGH
Mechanism: Greed says "let it run." Discipline says "take the profit I planned for." Pre-defined profit targets remove emotion from exit decisions. If your target was 5% and you're at 5%, take the profit.
Action: Set profit targets at entry. When hit, sell at least 50%. The target was set when you were objective — don't override it when you're emotional.

**#137: Overnight Risk Assessment — Reduce Before Known Events**
Type: Portfolio
Priority: MEDIUM
Mechanism: Holding full positions into known overnight risk events (earnings, FOMC, jobs report) is gambling, not trading. The event outcome is unknowable, and the market gaps on surprise.
Action: Before known risk events, reduce all affected positions by 50%. The cost of missing a gap in your favor is less than the cost of a gap against you.

**#138: Factor Score Decay — Position Drops Below 4/10**
Type: Systematic
Priority: HIGH
Mechanism: When you entered, the factor engine scored this trade 7/10. Now it scores 4/10. The factors that supported your entry have deteriorated. The trade's edge has evaporated even if price hasn't moved yet.
Action: Run the factor engine on all held positions daily. Any position scoring below 4/10 gets exited within 24 hours regardless of P&L.

**#139: Sector Crowding — >50% of Portfolio in Related Names**
Type: Portfolio
Priority: HIGH
Mechanism: Having NVDA, AMD, AVGO, and QCOM is not "4 positions" — it's one semiconductor bet. Sector crowding means one bad sector day wipes out your diversification. Concentration in disguise.
Action: Count correlated positions as one exposure. If related names exceed 30% of portfolio, trim the weakest until below 30%.

**#140: Gap Down on Your Short — Cover for Profit**
Type: Tactical
Priority: MEDIUM
Mechanism: When your short position gaps down significantly (>3%), the easy money on the short is captured. Continuing to hold exposes you to a short squeeze on the bounce. Shorts that gap down on news often bounce 30-50% of the move within days.
Action: Cover 50-75% of short positions that gap down >3% at the open. Keep a small position if the thesis remains intact.

**#141: Expiration Cycle — Options Decay on Existing Position**
Type: Derivatives
Priority: MEDIUM
Mechanism: If you're holding options (not just stock), theta decay accelerates in the final 2 weeks before expiration. An option position that was fine at 30 DTE becomes a melting ice cube at 7 DTE.
Action: Roll or close any options positions at 14 DTE unless they're deep in the money. Theta is not your friend.

**#142: After-Hours Signal Contradicts Your Position**
Type: Event
Priority: MEDIUM
Mechanism: If AH signals (earnings reactions, macro news, after-hours movers) contradict your position thesis, the pre-market will likely gap against you. The AH signal is a preview of tomorrow's open.
Action: Review all AH signals against your positions. If a signal directly contradicts your thesis (e.g., you're long tech and NVDA misses), prepare exit orders for the open.

**#143: Position Complexity — More Than 3 Legs**
Type: Portfolio
Priority: LOW
Mechanism: If a position has become complex (added multiple times, partial exits, averaged down, hedged with options), it's hard to manage and easy to mistrack. Complexity breeds errors.
Action: If a position has more than 3 trade records, simplify. Either fully commit or fully exit. Half-measures create confusion.

**#144: Sleep Test — Can You Hold This Overnight Without Anxiety?**
Type: Behavioral
Priority: MEDIUM
Mechanism: If a position makes you uncomfortable overnight, it's too large or too risky for your current conviction level. Anxiety is your subconscious telling you the risk/reward doesn't feel right. Trust it.
Action: If you wouldn't be comfortable holding a position if you couldn't check prices for 24 hours, reduce by 50%.

**#145: Maximum Open Positions — 15 Cap**
Type: Portfolio
Priority: MEDIUM
Mechanism: Attention is finite. Beyond 15 open positions, you can't meaningfully track catalysts, stops, and factor changes for each one. You become a passive holder, not an active manager. Quality of management degrades with quantity.
Action: Hard cap at 15 open positions across the portfolio. To open #16, close your weakest position. Quality over quantity in position count (not trade count — trade as many times as needed).

**#146: Correlation Break — Asset Stops Moving With Its Group**
Type: Quantitative
Priority: MEDIUM
Mechanism: If your tech stock suddenly stops moving with the tech sector (QQQ up 1%, your stock flat or down), something company-specific is wrong. Correlation breaks in a negative direction = informed selling.
Action: When a position's 5-day rolling correlation with its sector drops below 0.3 (from >0.7), investigate. If no clear positive reason, exit within 2 days.

**#147: Fund Flow Reversal — Your Sector Seeing Outflows**
Type: Flow
Priority: MEDIUM
Mechanism: When sector ETF fund flows reverse from inflows to outflows, institutional allocators are rotating away. This creates persistent selling pressure over weeks as the rotation plays out.
Action: When fund flows reverse to outflows for 2+ consecutive weeks, trim sector exposure by 25% per week until flows stabilize.

**#148: Market Breadth Collapse — <40% of Stocks Above 50-Day MA**
Type: Macro
Priority: HIGH
Mechanism: When fewer than 40% of S&P 500 stocks are above their 50-day MA, the market is sick despite what the index might show. A few mega-caps are masking broad weakness. This condition precedes 70%+ of 10%+ corrections.
Action: When breadth drops below 40%, exit all but your strongest 3-4 positions. The average stock is already in a correction even if SPY isn't.

**#149: Profit Satisficing — "Good Enough" Exit**
Type: Portfolio
Priority: MEDIUM
Mechanism: A 3% gain captured is worth more than a 10% gain imagined. Satisficing (accepting a "good enough" outcome) beats maximizing (trying to capture the perfect exit) because perfect exits only exist in hindsight.
Action: If a position is up 3%+ and the factor engine scores it ≤6/10 currently, take the profit. Don't wait for more when the factors say the edge is gone.

**#150: System Override — When Nothing Else Works, Go to Cash**
Type: Emergency
Priority: ABSOLUTE
Mechanism: When multiple exit signals trigger simultaneously (VIX spike + credit widening + breadth collapse + correlation spike + regime shift), the correct action is not to "pick which positions to keep." It's to go to cash and reassess from zero.
Action: When 5+ independent exit signals fire on the same day, close all positions and go 100% cash. Rebuild from scratch when conditions stabilize. Preservation of capital > maximization of returns.

---

## Summary: All 150 Exit Factors by Category

| Category | Factors | Count |
|----------|---------|-------|
| Stop Loss & Risk Management | #1-30 | 30 |
| Technical & Price Action | #31-60 | 30 |
| Fundamental & Earnings | #61-90 | 30 |
| Market Regime & Macro | #91-120 | 30 |
| Portfolio Management & Behavioral | #121-150 | 30 |
| **TOTAL** | | **150** |

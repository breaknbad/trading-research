# 150 Trading Factors & Correlations
> Original 50 in `alfred-correlations-50.md` | 100 new factors below
> Built per Mark directive 2026-02-26: "Identify 100 different factors and correlations the experts look at"

---

## ROUND 1: Microstructure & Order Flow (51–70)
*What's happening in the market RIGHT NOW — the factors day traders and institutional desks watch in real time.*

**#51: Dark Pool Short Volume Ratio >50%**
Direction: Market Down (short-term)
Reliability: ~77%
Mechanism: FINRA reports daily short volume by venue. When dark pool short volume exceeds 50% of total volume on a name, institutional sellers are distributing through off-exchange venues to avoid moving the price. They're getting out quietly.
Action: Avoid buying names where dark pool short volume ratio has been >50% for 3+ consecutive days. If already long, tighten stops.
Data: FINRA ADF/TRF daily short volume files (free, next-day).

**#52: Unusual Options Activity — Smart Money Sweeps**
Direction: Both
Reliability: ~79%
Mechanism: When someone pays the ask on large options blocks ($1M+ premium) and sweeps across multiple exchanges simultaneously, they need to get filled NOW. This is informed money positioning before a known catalyst. Sweeps > blocks (blocks can be hedged).
Action: Follow sweep direction. Call sweeps with >$500K premium on OTM strikes = bullish. Put sweeps = bearish. Must be >2x average daily options volume on the strike.
Data: Unusual Whales, FlowAlgo, or CBOE real-time.

**#53: Bid-Ask Spread Compression on High Volume**
Direction: Market Up
Reliability: ~76%
Mechanism: Tightening spreads + rising volume = market makers are confident in the direction and competing aggressively for flow. Wide spreads + volume = uncertainty. Spread compression during an uptrend confirms conviction.
Action: Favor entries when the bid-ask spread narrows below its 20-day average AND volume is above average. Avoid entries when spreads widen >2x normal.

**#54: Level 2 Spoofing / Iceberg Orders**
Direction: Both
Reliability: ~75%
Mechanism: Large visible orders that get pulled before execution (spoofing) signal manipulation — someone wants to push price in one direction. Iceberg orders (small visible, large hidden) signal real institutional accumulation/distribution.
Action: If seeing repeated large bids appearing and disappearing, don't trust the support. If small orders keep getting filled at the same price level repeatedly, institutional accumulation is likely.

**#55: VWAP Reclaim After Morning Selloff**
Direction: Market Up
Reliability: ~80%
Mechanism: VWAP is the institutional benchmark price. When a stock sells off below VWAP in the first hour but reclaims it by 10:30 AM, it signals that dip buyers overwhelmed morning sellers. Institutions buying the dip is a strong signal.
Action: Enter long when price reclaims VWAP after a morning dip, with volume confirmation. Stop below the morning low.

**#56: NYSE TICK Extremes (>+1000 or <-1000)**
Direction: Both
Reliability: ~78%
Mechanism: The NYSE TICK measures how many stocks just traded on an uptick vs downtick. Readings above +1000 indicate broad buying pressure; below -1000 indicates panic selling. Sustained readings in one direction signal institutional programs running.
Action: Readings >+1000 sustained for 5+ minutes = strong buy signal for index longs. Readings <-1000 = either exit longs or wait for reversal. Mean reversion from extremes works well intraday.

**#57: Relative Volume (RVOL) > 3x by 10:00 AM**
Direction: Both (follow the direction)
Reliability: ~82%
Mechanism: When a stock has traded 3x its average volume by 10:00 AM, something material has changed. The market is pricing in new information. Volume is the one indicator that can't lie — real money is changing hands.
Action: If RVOL > 3x with price UP, go long with momentum. If RVOL > 3x with price DOWN, stay away or short. The first 30 minutes of extreme volume set the tone for the day.

**#58: Pre-Market Volume Surge (>500K shares before 9:30)**
Direction: Both
Reliability: ~77%
Mechanism: Heavy pre-market volume indicates overnight catalysts that institutions are positioning around. Most retail can't trade pre-market effectively, so this is largely institutional and algorithmic flow.
Action: Stocks with >500K pre-market shares traded AND gapping >3% will typically continue in the gap direction for the first 30 minutes. Wait for the opening 5-min candle to confirm, then enter.

**#59: Short Interest > 20% Float + Borrow Rate Spiking**
Direction: Market Up (squeeze potential)
Reliability: ~76%
Mechanism: High short interest creates a coiled spring. When borrow rates spike (>50% annualized), shorts are getting expensive to maintain. Any positive catalyst forces covering, which drives price up, which forces more covering — a squeeze.
Action: Track names with >20% short interest AND rising borrow rates. On any positive catalyst (earnings beat, analyst upgrade, sector strength), go long for a squeeze. Size smaller — these are volatile.

**#60: Block Trade Prints on the Tape**
Direction: Both
Reliability: ~77%
Mechanism: Large block trades (>10K shares or >$500K) printed at the ask indicate aggressive buying. Blocks at the bid indicate aggressive selling. The tape doesn't lie — large prints are institutional.
Action: Track time & sales for block prints. If 3+ blocks hit the ask within 10 minutes, go long. If blocks are hitting the bid, don't fight institutional selling.

**#61: Options Implied Volatility Skew (Put Skew Steepening)**
Direction: Market Down
Reliability: ~78%
Mechanism: When OTM puts become disproportionately expensive vs OTM calls, smart money is buying crash protection. The put skew steepens before major declines because informed participants hedge quietly.
Action: Monitor 25-delta put vs 25-delta call IV. When put premium exceeds call premium by >10 vol points, hedge long positions. This often leads equity declines by 1-2 weeks.

**#62: Gamma Exposure (GEX) Flip from Positive to Negative**
Direction: Market Down (more volatile)
Reliability: ~80%
Mechanism: When dealer gamma exposure flips negative (below key strike prices), market makers must sell as prices drop and buy as prices rise — they AMPLIFY moves instead of dampening them. Negative GEX = bigger swings.
Action: Track aggregate dealer GEX (SpotGamma, SqueezeMetrics). Below the GEX flip level, reduce position sizes and widen stops. Above it, the market is more stable — trend-following works better.

**#63: Net New 52-Week Highs vs Lows (Breadth)**
Direction: Both
Reliability: ~81%
Mechanism: When new highs outnumber new lows by >10:1, the market has broad strength. When new lows dominate, even if the index is flat, the average stock is deteriorating. This is the earliest divergence signal.
Action: Track NYSE new highs minus new lows daily. Positive and expanding = stay long. Turning negative while SPX is flat/up = reduce exposure. This divergence has preceded every major correction.

**#64: Sector ETF Money Flow (Relative Rotation)**
Direction: Both
Reliability: ~78%
Mechanism: Capital rotates between sectors in a predictable cycle: risk-on (tech, discretionary) → risk-off (utilities, staples, healthcare). Tracking which sectors are seeing inflows vs outflows reveals where smart money is positioning.
Action: Use relative rotation graphs (RRG) or ETF fund flow data. Overweight sectors in "leading" quadrant (strong momentum + strong relative strength). Underweight those in "lagging."

**#65: After-Hours Volume Spike on No News**
Direction: Both
Reliability: ~75%
Mechanism: When a stock trades 5x+ normal AH volume without a press release, someone knows something. It could be a leaked earnings number, a pending acquisition, or an insider acting on material non-public info (illegal but real).
Action: Flag any stock with >5x normal AH volume and no corresponding news. If direction is UP, add to watchlist for morning open. Don't chase AH — wait for confirmation at open.

**#66: Cumulative Delta Divergence**
Direction: Both
Reliability: ~79%
Mechanism: Cumulative delta tracks the running total of volume at the ask minus volume at the bid. If price is rising but cumulative delta is falling, buyers are getting weaker — the rally is running on fumes. And vice versa.
Action: Enter only when price and cumulative delta agree. If price makes a new high but delta doesn't = distribution, prepare to exit. If price makes a new low but delta diverges up = accumulation, prepare to buy.

**#67: Market-On-Close (MOC) Imbalance**
Direction: Both
Reliability: ~77%
Mechanism: NYSE publishes MOC imbalances at 3:50 PM. Large buy imbalances ($1B+) push prices up into the close; large sell imbalances push down. This is institutional rebalancing and pension fund flow — predictable and mechanical.
Action: At 3:50 PM, check MOC imbalances. Large buy imbalance = go long SPY for the final 10 minutes. Large sell = go short or close longs. Simple, mechanical, repeatable.

**#68: ETF Creation/Redemption Activity**
Direction: Both
Reliability: ~76%
Mechanism: When authorized participants create new ETF shares, it means demand exceeds supply — bullish for underlying holdings. Redemptions mean supply exceeds demand. This is a direct measure of institutional flow into/out of themes.
Action: Track SPY, QQQ, IWM creation/redemption units. Net creations = institutional buying. Net redemptions = institutional selling. Particularly useful at trend changes.

**#69: Cross-Exchange Arbitrage (Crypto)**
Direction: Both
Reliability: ~78%
Mechanism: When BTC or ETH trades at a significant premium on one exchange vs another (>0.5%), it signals directional pressure from specific market participants. Coinbase premium over Binance = US institutional buying. Binance premium = Asia retail FOMO.
Action: Track Coinbase-Binance spread. Persistent Coinbase premium = bullish (US institutions accumulating). Persistent discount = bearish (US institutions distributing while Asia holds).

**#70: Market Maker Inventory Proxy (ETF vs Underlying Spread)**
Direction: Both
Reliability: ~75%
Mechanism: When an ETF trades at a premium to its NAV, market makers are short the ETF and long the underlying — they'll eventually need to buy the ETF or sell the underlying. Discounts indicate the opposite positioning.
Action: Track SPY/QQQ premium/discount to fair value (IIV). Persistent premium = demand exceeding supply, bullish. Discount = supply exceeding demand, cautious.

---

## ROUND 2: Technical & Price Action (71–90)
*Pattern recognition, momentum, mean reversion — what chartists and quants look at.*

**#71: Opening Range Breakout (First 15-Minute Candle)**
Direction: Both
Reliability: ~74%
Mechanism: The first 15 minutes absorb overnight orders and set the day's initial range. A breakout above this range with volume indicates bullish institutional flow; below indicates bearish. ORB is one of the oldest and most reliable day trading setups.
Action: Mark the high and low of the first 15-minute candle. Enter long on a break above with volume >1.5x average. Enter short on a break below. Stop at the opposite side of the range.

**#72: Gap and Go (>4% Gap with Catalyst)**
Direction: Up (continuation)
Reliability: ~76%
Mechanism: Stocks gapping >4% on a fundamental catalyst (earnings, upgrade, FDA approval) tend to continue in the gap direction, especially when volume confirms. The gap represents overnight institutional repricing.
Action: Buy the first pullback to VWAP or the 9 EMA on the 5-minute chart within the first hour. Stop below the pre-market low. Target 1.5-2x the risk.

**#73: 9/20 EMA Cross on 5-Minute Chart**
Direction: Both
Reliability: ~73%
Mechanism: The 9 EMA crossing above the 20 EMA on the 5-minute chart signals short-term momentum shift. Used by thousands of day traders, it becomes somewhat self-fulfilling on liquid names.
Action: Enter long when 9 crosses above 20 on 5-min with rising volume. Enter short on the opposite. Works best in the first 2 hours and last hour. Less reliable during lunch.

**#74: MACD Histogram Divergence (Daily)**
Direction: Both
Reliability: ~77%
Mechanism: When price makes a new high but the MACD histogram makes a lower high, momentum is weakening despite price strength. This divergence is one of the most reliable reversal signals in technical analysis.
Action: Don't enter new longs on bearish MACD divergence. Don't short on bullish divergence. Use as a timing filter — not standalone, but it dramatically improves entry quality.

**#75: RSI Divergence at Extremes (>70 or <30)**
Direction: Both (reversal)
Reliability: ~76%
Mechanism: RSI above 70 with declining peaks = bearish divergence (momentum fading even as price rises). RSI below 30 with rising troughs = bullish divergence (selling pressure easing).
Action: Don't buy when RSI shows bearish divergence above 70 on daily. Accumulate when RSI shows bullish divergence below 30. Combine with support/resistance for entry timing.

**#76: Volume Profile — Point of Control (POC) Test**
Direction: Both
Reliability: ~79%
Mechanism: The POC is the price with the most traded volume over a given period — the "fair value" agreed on by most participants. Price tends to revert to POC. Breaks away from POC with volume signal genuine trend changes.
Action: Fade moves away from POC when volume is low (mean reversion). Follow moves away from POC when volume is high (breakout). POC acts as a magnet during consolidation.

**#77: Bollinger Band Squeeze (Low Bandwidth)**
Direction: Both (breakout coming)
Reliability: ~78%
Mechanism: When Bollinger Bands narrow to their tightest in 6+ months, volatility compression has reached an extreme. Like a coiled spring, the subsequent expansion is typically explosive. The squeeze doesn't predict direction — only that a big move is coming.
Action: When BB bandwidth hits 6-month lows, prepare for a breakout. Enter in the direction of the breakout once price closes outside the bands on volume. Avoid bias — let the market show direction.

**#78: Fibonacci 61.8% Retracement Hold**
Direction: Up (continuation)
Reliability: ~75%
Mechanism: The 61.8% retracement is the deepest "healthy" pullback in a trend. Holding here means the trend is likely to continue. Breaking below suggests the prior move is being fully reversed.
Action: In uptrends, buy at 61.8% retracement with a stop below 78.6%. In downtrends, short at 61.8% retracement. Target the prior high/low. Clean risk/reward with defined levels.

**#79: Inside Day Breakout (Daily Candle)**
Direction: Both
Reliability: ~74%
Mechanism: An inside day (high is lower than prior high, low is higher than prior low) represents consolidation and indecision. The breakout from this compressed range typically leads to a multi-day directional move.
Action: Mark the inside day's high and low. Enter on the breakout with volume on the next day. Stop at the opposite side. Works best after strong trending moves (consolidation before continuation).

**#80: Multiple Time Frame Alignment (MTF)**
Direction: Both
Reliability: ~82%
Mechanism: When the weekly, daily, and hourly charts all agree on direction (all uptrending or all downtrending), the probability of continuation is highest. Conflicting timeframes = chop zone.
Action: Only enter trades where weekly trend, daily trend, and hourly trend all align. This single filter eliminates most losing trades. If timeframes conflict, stay flat.

**#81: Anchored VWAP from Earnings/Catalyst**
Direction: Both
Reliability: ~79%
Mechanism: VWAP anchored from the last major catalyst (earnings, FDA, etc.) represents the average price all participants have paid since that event. It's a crucial support/resistance level that institutions track.
Action: When price pulls back to anchored VWAP from the last positive catalyst, it's a buying opportunity. When it breaks below, the thesis from that catalyst is invalidated — exit.

**#82: Market Internal Divergence (SPY Up, Internals Red)**
Direction: Market Down
Reliability: ~80%
Mechanism: When SPY is green but $ADD (advance-decline), $TICK, and $VOLD (up volume - down volume) are all negative, the index is being held up by a few names. This artificial strength typically resolves downward.
Action: Don't go long SPY when internals diverge bearishly. If already long, tighten stops. The divergence usually resolves within 1-2 hours intraday.

**#83: Overnight Range (Globex) as Support/Resistance**
Direction: Both
Reliability: ~76%
Mechanism: The overnight session establishes a range where international participants have agreed on value. The high and low of this range become key levels for the regular session. Breakouts from the overnight range with volume have strong follow-through.
Action: Mark the overnight (Globex) high and low pre-open. Trade breakouts with volume. If price is trapped within the overnight range, expect chop.

**#84: Keltner Channel Squeeze (Inside Bollinger Bands)**
Direction: Both (breakout)
Reliability: ~77%
Mechanism: When Bollinger Bands contract inside Keltner Channels, it's the "squeeze" signal (popularized by John Carter). The release from this squeeze generates powerful directional moves.
Action: Use TTM Squeeze indicator. When the squeeze fires (dots turn from red to green), enter in the direction of the momentum histogram. Stop below the squeeze low (for longs).

**#85: Pivot Point Confluence**
Direction: Both
Reliability: ~75%
Mechanism: When multiple pivot point levels from different timeframes (daily, weekly, monthly) converge at the same price, that level becomes a powerful support/resistance zone. More confluence = more significance.
Action: Calculate daily, weekly, and monthly pivots. When 2+ align within 0.5%, that zone is high probability for a bounce or rejection. Enter with tight stops on the other side.

**#86: Volume Dry-Up Before Breakout**
Direction: Up
Reliability: ~78%
Mechanism: In a base/consolidation, declining volume indicates sellers are exhausted. When volume then surges on a breakout candle, it confirms that the low-volume period was accumulation, not distribution.
Action: Watch for volume declining to <50% of average during consolidation near highs. Enter on the first volume surge above resistance. The lower the base volume, the more reliable the breakout.

**#87: Failed Breakdown (Bear Trap)**
Direction: Market Up
Reliability: ~80%
Mechanism: When price breaks below a key support level but immediately recovers (within 1-3 candles), it traps shorts who entered on the breakdown. Their covering becomes fuel for a sharp move higher.
Action: If price breaks below support but closes back above within 2 sessions, go long aggressively. Stop below the failed breakdown low. These are some of the highest probability long entries.

**#88: Three Drives Pattern**
Direction: Both (reversal)
Reliability: ~74%
Mechanism: Three pushes to new highs (or lows) with each drive weaker than the last = exhaustion. The third push traps the last momentum chasers. Popularized by Robert Prechter and later by harmonic traders.
Action: After the third drive, enter counter-trend with a stop above/below the third extreme. Target the origin of the first drive. Works on all timeframes.

**#89: Sector Breakout Rotation (New Sector Highs)**
Direction: Both
Reliability: ~77%
Mechanism: When a sector ETF breaks to new 52-week highs, it signals institutional rotation into that theme. Capital follows momentum into sectors, creating multi-week trends.
Action: Track all 11 GICS sector ETFs. When a sector breaks to 52-week highs, buy the strongest names within it (leaders, not laggards). Hold until the sector's relative strength starts declining.

**#90: Candle Close Location (Wicks vs Bodies)**
Direction: Both
Reliability: ~73%
Mechanism: Long lower wicks indicate buyers defending price (bullish). Long upper wicks indicate sellers rejecting price (bearish). Bodies > wicks indicate conviction. The close location within the range tells you who won the session.
Action: For entries, favor candles that close in the top 25% of their range (bullish) or bottom 25% (bearish). Doji candles (open ≈ close with long wicks) = indecision, don't enter.

---

## ROUND 3: Fundamental & Earnings Quality (91–110)
*What drives value over weeks and months — the factors fundamental analysts and value investors watch.*

**#91: Earnings Revision Momentum (Upward Revisions)**
Direction: Market Up
Reliability: ~83%
Mechanism: When analysts raise earnings estimates, it signals improving business conditions not yet in the price. Stocks with rising EPS estimates outperform those with declining estimates by ~10% annually. The "estimate revision cycle" is one of the strongest fundamental factors.
Action: Screen for stocks where consensus EPS estimates have risen >5% in the last 30 days. Go long. This factor has strong academic backing (Glushkov 2009, institutional factor models).

**#92: Revenue Growth Acceleration**
Direction: Market Up
Reliability: ~81%
Mechanism: Revenue growth rate increasing quarter-over-quarter is the purest signal of demand acceleration. Earnings can be managed; revenue cannot be faked. Acceleration means the business is gaining customers faster.
Action: Buy stocks where YoY revenue growth rate INCREASED from the prior quarter (e.g., 15% → 20%). Avoid stocks where growth is decelerating even if still positive.

**#93: Gross Margin Expansion**
Direction: Market Up
Reliability: ~79%
Mechanism: Expanding gross margins signal pricing power — the company can charge more or produce more cheaply. This is the highest-quality form of earnings improvement because it's operational, not financial engineering.
Action: Go long stocks where gross margin expanded 100+ bps QoQ for 2+ consecutive quarters. Short stocks where gross margins are compressing (NVDA's 75%→71% drop is a warning).

**#94: Free Cash Flow Yield > 7%**
Direction: Market Up
Reliability: ~78%
Mechanism: FCF yield (free cash flow / market cap) above 7% means the company generates enough cash to "buy itself" in ~14 years. This is a deep value signal — the market is pricing the business as if it will decline, but cash generation says otherwise.
Action: Screen for FCF yield >7% with stable or growing FCF. Avoid value traps by requiring FCF to be stable or growing (not one-time). Hold for 6-12 months.

**#95: Insider Buying After Earnings Miss**
Direction: Market Up
Reliability: ~82%
Mechanism: When insiders buy after the company misses earnings, they're signaling the miss is temporary and the market overreacted. They know the business better than analysts. This is a strong contrarian signal.
Action: Track SEC Form 4 filings. When C-suite insiders buy >$100K worth after a post-earnings selloff, go long with a 3-6 month horizon. Cluster buying (3+ insiders) is even stronger.

**#96: Short Interest Ratio (Days to Cover) > 10**
Direction: Both (squeeze risk)
Reliability: ~76%
Mechanism: Days to cover = short interest / average daily volume. Above 10 means shorts would need 2 weeks of average volume to close positions. Any positive catalyst creates a squeeze because shorts literally can't exit fast enough.
Action: Maintain a watchlist of stocks with days-to-cover >10. On positive catalysts, these moves are amplified 2-3x. Size accordingly (smaller, because the vol is extreme).

**#97: Debt-to-EBITDA Rising Above 4x**
Direction: Market Down
Reliability: ~77%
Mechanism: Leverage above 4x puts a company in the danger zone — it can service debt in good times but any downturn in EBITDA risks covenant breaches, rating downgrades, and death spirals. Credit stress leads to equity destruction.
Action: Avoid or short companies where net debt/EBITDA has risen above 4x and is still climbing. Especially dangerous in rate-hiking environments.

**#98: Guidance Raise (Full Year)**
Direction: Market Up
Reliability: ~84%
Mechanism: When management raises full-year guidance, they're telling you the business is doing better than they originally expected. This is the strongest forward-looking signal because management has the most information about their own company.
Action: Buy on full-year guidance raises, even if the stock gaps up on the news. Guidance raises lead to a "staircase" of estimate revisions and upgrades over the following weeks.

**#99: Operating Leverage Inflection**
Direction: Market Up
Reliability: ~80%
Mechanism: When a company's revenue growth exceeds expense growth (operating leverage), each incremental dollar of revenue generates disproportionate earnings. This inflection from margin compression to expansion is where the biggest stock moves begin.
Action: Screen for companies where operating income is growing faster than revenue for 2+ consecutive quarters. This signals the business has crossed the profitability inflection.

**#100: Inventory-to-Sales Ratio Declining**
Direction: Market Up
Reliability: ~76%
Mechanism: Declining inventory-to-sales means demand is outpacing supply. The company is selling faster than it can stock shelves. This leads to pricing power, margin expansion, and positive earnings surprises.
Action: In retail and manufacturing, track inventory/sales ratio. A declining trend supports longs. Rising ratio (inventory building while sales flatten) is a sell signal.

**#101: Customer Concentration Risk (>30% from One Customer)**
Direction: Market Down (risk factor)
Reliability: ~74%
Mechanism: If one customer represents >30% of revenue, the company has a single point of failure. Loss of that customer = catastrophic revenue hit. The market often ignores this until it happens.
Action: Avoid or reduce position size in companies with >30% customer concentration. If the key customer announces a review/change, exit immediately.

**#102: R&D Intensity as % of Revenue (Innovation Signal)**
Direction: Market Up (long-term)
Reliability: ~76%
Mechanism: Companies spending >15% of revenue on R&D are investing in future products. In tech and biotech, R&D intensity correlates with revenue growth 2-3 years out. It's a leading indicator of innovation.
Action: In growth sectors, favor companies with high and rising R&D/revenue ratios. In value sectors, ignore this factor (capex matters more).

**#103: Buyback Yield > 3%**
Direction: Market Up
Reliability: ~78%
Mechanism: When companies repurchase >3% of their shares annually, they're reducing float and increasing per-share metrics. Buybacks funded by free cash flow (not debt) are a strong bullish signal — management believes the stock is undervalued.
Action: Screen for buyback yield >3% funded by FCF. Combine with insider buying for a very strong signal. Avoid debt-funded buybacks (financial engineering, not conviction).

**#104: Earnings Quality Score (Accruals Ratio)**
Direction: Both
Reliability: ~80%
Mechanism: Companies with high accruals (earnings far exceeding cash flow) are more likely to see future earnings downgrades. Low accruals (cash flow > reported earnings) signal high-quality earnings. The Sloan Accrual Anomaly has generated alpha for decades.
Action: Calculate accruals ratio: (Net Income - Operating Cash Flow) / Total Assets. Favor stocks with NEGATIVE accruals (cash > earnings). Avoid stocks with high positive accruals.

**#105: Same-Store Sales (Comps) Acceleration**
Direction: Market Up
Reliability: ~82%
Mechanism: For retail and restaurants, same-store sales growth acceleration is the single most important metric. It means existing locations are gaining traffic/ticket — organic growth without needing new stores.
Action: Go long retail/restaurant stocks with accelerating comps for 2+ quarters. Short those with decelerating comps. This metric is reported monthly/quarterly and moves stocks significantly.

**#106: Congressional Trading Filings (STOCK Act)**
Direction: Both
Reliability: ~75%
Mechanism: Members of Congress and their spouses file trades 45 days after execution. While delayed, cluster buying in a sector or name signals policy awareness. Congressional portfolios have historically outperformed the market.
Action: Track Quiver Quantitative or Capitol Trades. When 3+ members of relevant committees buy the same sector, go long. Especially strong for defense, healthcare, and tech (committee members with oversight).

**#107: Analyst Initiation with Overweight/Buy**
Direction: Market Up
Reliability: ~73%
Mechanism: New coverage initiations (not existing coverage upgrades) signal an investment bank has done deep due diligence and is willing to put their reputation behind a name. The first 30 days after initiation tend to outperform.
Action: Track new initiations at Buy/Overweight. Enter within the first week for names that haven't already run. More significant when a top-tier bank initiates (Goldman, Morgan Stanley, JPM).

**#108: Dividend Growth Streak > 10 Years**
Direction: Market Up (defensive)
Reliability: ~79%
Mechanism: Companies that have grown dividends for 10+ consecutive years (Dividend Achievers) have proven they can grow earnings through multiple economic cycles. The dividend acts as a discipline mechanism — management must generate cash to fund it.
Action: In defensive/income allocations, favor Dividend Achievers. They outperform during drawdowns and compound reliably. Core holdings, not trading vehicles.

**#109: Capex Cycle Upturn (Rising Capex/Revenue)**
Direction: Market Up (cyclicals)
Reliability: ~77%
Mechanism: When companies start investing in capacity again (rising capex/revenue ratio after a trough), it signals management confidence in future demand. Capex cycles drive industrial and materials stocks for 2-3 year periods.
Action: Track capex/revenue ratios for industrial and materials companies. When the ratio inflects up from a trough, go long cyclicals. This is a multi-quarter position, not a trade.

**#110: Price/Sales Ratio vs Sector Median**
Direction: Both
Reliability: ~75%
Mechanism: P/S ratio removes earnings manipulation. Stocks trading at >2x their sector's median P/S are priced for perfection and vulnerable to any miss. Stocks below 0.5x median are potentially undervalued (or distressed — need to check why).
Action: Avoid initiating longs in names at >2x sector P/S unless growth rate justifies it. Favor names at 0.5-0.8x sector P/S with stable revenue.

---

## ROUND 4: Event-Driven & Catalysts (111–130)
*The things that MOVE stocks — news, policy, filings, and structural events.*

**#111: Fed Speaker Hawkish/Dovish Shift**
Direction: Both
Reliability: ~79%
Mechanism: When Fed governors shift language from hawkish to dovish (or vice versa), it signals a policy pivot before it happens. Markets move on the expectation, not the action. One dovish comment from a hawk moves rates and equities.
Action: Track Fed speaker language changes via CME FedWatch and market reactions. A hawkish member turning dovish = buy equities/bonds. A dove turning hawkish = reduce exposure. The shift matters more than the level.

**#112: CPI/PPI Print vs Expectations**
Direction: Both
Reliability: ~81%
Mechanism: Inflation prints are binary catalysts. Cooler than expected = equity rally (rate cut expectations). Hotter = selloff (higher for longer). The magnitude of surprise determines the move size.
Action: Position for CPI/PPI days. If expecting a cool print: long equities, long bonds. If hot: cash or short. Check Cleveland Fed nowcast and Truflation for real-time inflation estimates as edge.

**#113: 13F Filing Reveals (Institutional Holdings)**
Direction: Both
Reliability: ~74%
Mechanism: Quarterly 13F filings show what top managers bought/sold with a 45-day delay. When multiple top funds (Berkshire, Bridgewater, Renaissance) initiate or add to the same name, it's consensus institutional conviction.
Action: Track 13F filings for top 20 managers. Stocks appearing as new positions in 3+ top funds are strong longs. Stocks being liquidated by multiple funds = avoid.

**#114: FDA Approval/Rejection Binary Event**
Direction: Both (extreme)
Reliability: ~85% (direction of move once decision is out)
Mechanism: FDA decisions cause 30-100% moves in biotech. Approval = surge. Rejection = collapse. AdCom votes give a preview (positive vote = 85% chance of approval).
Action: Don't hold through FDA decisions unless it's a calculated binary bet. If holding, size to survive a 50% adverse move. Better to wait for the decision and buy the first pullback on an approval.

**#115: M&A Announcement (Target and Acquirer)**
Direction: Target Up, Acquirer Both
Reliability: ~90% (target moves toward deal price)
Mechanism: M&A targets trade toward the offer price (merger arb spread). Acquirers often drop 2-5% on announcement (paying a premium = dilutive). The spread between current price and deal price reflects deal risk.
Action: In announced deals, go long the target if spread is >5% and deal risk is low (friendly, no regulatory concern). For acquirers, buy the dip if the deal is strategically sound.

**#116: Activist Investor 13D Filing**
Direction: Market Up
Reliability: ~78%
Mechanism: When an activist (Icahn, Elliott, Starboard) files a 13D disclosing a 5%+ stake, it signals they'll push for changes (board seats, asset sales, buybacks) that unlock value. The filing itself is a catalyst.
Action: Buy on 13D filings from proven activists. The first 30-60 days typically see the biggest move. Hold through the campaign (6-12 months) for full value realization.

**#117: Tariff/Trade Policy Announcement**
Direction: Both (sector-specific)
Reliability: ~77%
Mechanism: Tariff announcements directly impact input costs and competitive dynamics. New tariffs on Chinese goods = bullish for domestic manufacturers, bearish for importers. Tariff removal = opposite.
Action: Map tariff exposure by company (import-dependent vs domestic). Position immediately on announcements — markets reprice within hours. Domestic manufacturers with pricing power benefit most.

**#118: Index Rebalance (Addition/Deletion)**
Direction: Both
Reliability: ~82%
Mechanism: When a stock is added to the S&P 500, every index fund MUST buy it. This creates $5-10B of forced buying in a single session. Deletions create forced selling. The effect is mechanical and predictable.
Action: Buy stocks announced for S&P 500 addition before the effective date (usually 5 trading days). Sell/short deletions. The "index effect" generates 3-7% excess returns on average.

**#119: Lock-Up Expiration (IPO/SPAC)**
Direction: Market Down
Reliability: ~76%
Mechanism: When insider lock-ups expire (typically 90-180 days after IPO), restricted shareholders can sell for the first time. Insiders with massive paper gains often sell, creating 5-15% declines around lock-up dates.
Action: Short or buy puts ahead of lock-up expirations. The effect is strongest when insiders hold >30% of float and the stock has appreciated since IPO.

**#120: Geopolitical Shock (War, Coup, Sanctions)**
Direction: Market Down (short-term)
Reliability: ~80%
Mechanism: Geopolitical shocks create immediate fear-driven selling. However, historically, markets recover from geopolitical events within weeks unless they cause fundamental economic damage. "Buy when there's blood in the streets."
Action: On geopolitical shocks: don't panic sell. If already in cash, wait 2-3 days for the initial panic to subside, then buy the dip. Long gold as a hedge during escalation.

**#121: Earnings Whisper Number vs Consensus**
Direction: Both
Reliability: ~75%
Mechanism: The "whisper number" (what buy-side actually expects) is often higher than published consensus. Companies that beat consensus but miss whispers sell off. Companies that beat whispers surge.
Action: Track earnings whispers (earningswhispers.com). Position for beats vs whisper, not consensus. If whisper is significantly above consensus, the stock may sell off even on a "beat."

**#122: Conference Call Tone (NLP Sentiment)**
Direction: Both
Reliability: ~76%
Mechanism: Management tone on earnings calls predicts future performance. Increased use of positive words, confidence markers, and specific guidance language correlates with subsequent outperformance. Hedging language and uncertainty markers precede misses.
Action: Use NLP tools to analyze call transcripts for sentiment change vs prior quarters. Improving tone = hold/add. Deteriorating tone = reduce. The shift matters more than absolute level.

**#123: Sector Rotation via Bond Proxies (Utilities, REITs)**
Direction: Both
Reliability: ~78%
Mechanism: When utilities and REITs outperform, it signals money is moving to bond-like equities for yield — a defensive signal. When they underperform while cyclicals lead, it's risk-on.
Action: Track XLU and VNQ relative to SPY. Rising relative strength = defensive rotation, reduce risk. Falling relative strength = risk-on, add cyclical exposure.

**#124: Government Shutdown/Debt Ceiling**
Direction: Market Down (short-term)
Reliability: ~74%
Mechanism: Shutdown threats create uncertainty that suppresses risk appetite. However, markets typically rally once resolution is reached. The uncertainty premium is temporary.
Action: Reduce exposure ahead of shutdown deadlines. Increase on resolution. Don't sell into the panic — use it as a buying opportunity with a 2-week horizon.

**#125: Treasury Auction Demand (Bid-to-Cover Ratio)**
Direction: Both
Reliability: ~77%
Mechanism: Weak demand at Treasury auctions (bid-to-cover <2.0) signals insufficient appetite for US debt, which forces higher yields and pressures equities. Strong auctions (>2.5) signal global confidence in US assets.
Action: Track 10Y and 30Y auction results. Weak auctions = reduce equity exposure, especially rate-sensitive sectors. Strong auctions = supportive for equities.

**#126: Bankruptcy Risk Score (Altman Z-Score < 1.8)**
Direction: Market Down
Reliability: ~80%
Mechanism: The Altman Z-Score predicts bankruptcy probability using profitability, leverage, liquidity, and efficiency ratios. Below 1.8 = distress zone. Below 1.0 = imminent risk. Distressed companies destroy equity value rapidly.
Action: Never go long a stock with Z-Score below 1.8 unless it's an explicit distressed debt play. Screen all positions quarterly. Rising Z-Scores from below 1.8 = turnaround plays.

**#127: Sector ETF Implied Correlation Rising**
Direction: Market Down
Reliability: ~76%
Mechanism: When implied correlation across sector ETFs rises, it means the market expects everything to move together — a sign of systemic risk or macro dominance. High correlation = stock-picking doesn't matter, macro does.
Action: When implied correlation spikes, reduce single-stock positions and use index hedges (SPY puts). When correlation drops, increase single-stock bets — alpha generation is easier.

**#128: Fiscal Stimulus/Spending Bill Passage**
Direction: Market Up
Reliability: ~79%
Mechanism: Large fiscal spending packages inject money directly into the economy. Infrastructure bills benefit materials/industrials. Defense spending benefits aerospace. The mapping of bill → sector beneficiaries is direct and tradeable.
Action: Track major bills through committee to passage. Position in beneficiary sectors when passage probability exceeds 70% (prediction markets). Don't wait for signing — markets front-run.

**#129: Natural Disaster Impact (Supply Chain)**
Direction: Both (sector-specific)
Reliability: ~75%
Mechanism: Natural disasters disrupt supply chains, causing scarcity pricing for goods and materials. Lumber after hurricanes, oil after Gulf storms, chips after factory fires. The supply shock creates tradeable moves.
Action: Map supply chain dependencies. When a disaster hits a key production region, go long the commodity/companies that benefit from scarcity. Short supply-chain-dependent companies that face shortages.

**#130: Equity Offering / Secondary Announcement**
Direction: Market Down (short-term)
Reliability: ~79%
Mechanism: When a company announces a secondary offering, it dilutes existing shareholders. The stock typically drops 3-8% on announcement as the market prices in more shares. The discount at which shares are offered signals management's urgency.
Action: Sell or reduce on secondary announcements. If you like the company long-term, buy back after the offering prices (usually 2-3 days later at a lower price). The deeper the offering discount, the more bearish.

---

## ROUND 5: Cross-Asset & Quantitative (131–150)
*The correlations machines and macro traders exploit — intermarket analysis and systematic factors.*

**#131: 10Y-2Y Treasury Spread (Yield Curve Steepness)**
Direction: Both
Reliability: ~82%
Mechanism: The yield curve is the single most reliable recession predictor. Inversion (2Y > 10Y) = recession coming. But the RE-STEEPENING from inverted is often when the recession actually starts and equities sell off hardest.
Action: Inversion = start building defensive positions over 6-12 months. Re-steepening after inversion = the clock is ticking, go maximum defensive. Normal steepening from normal levels = bullish for banks and cyclicals.

**#132: VIX Term Structure (Contango vs Backwardation)**
Direction: Both
Reliability: ~79%
Mechanism: Normal VIX term structure is contango (future months > spot). Backwardation (spot > future) = acute fear. The steepness of contango/backwardation tells you the market's fear timeline.
Action: Steep contango = complacency, buy cheap protection. Backwardation = peak fear, markets often bounce within days. Track VIX/VIX3M ratio — above 1.0 = backwardation.

**#133: Gold/Silver Ratio**
Direction: Both
Reliability: ~76%
Mechanism: Gold is a fear asset; silver is an industrial/fear hybrid. Rising gold/silver ratio = risk-off (gold outperforming). Declining ratio = risk-on (silver outperforming, signaling industrial demand).
Action: Ratio above 80 = extreme fear, contrarian buy signal for risk assets. Ratio below 60 = risk-on environment, stay long equities. Track for regime confirmation.

**#134: Copper vs Gold (Dr. Copper Ratio)**
Direction: Both
Reliability: ~80%
Mechanism: Copper is the PhD of economics — it goes into everything industrial. When copper outperforms gold, the global economy is strengthening. When gold outperforms copper, growth is slowing.
Action: Rising copper/gold ratio = overweight cyclicals, industrials, emerging markets. Falling ratio = overweight defensives, gold, bonds. This is one of the best macro regime indicators.

**#135: US Dollar Index (DXY) Breakout/Breakdown**
Direction: Both (inversely for equities)
Reliability: ~78%
Mechanism: A strong dollar crushes multinational earnings, emerging market debt servicing, and commodity prices. A weak dollar supports all three. DXY is the "anti-everything" trade.
Action: DXY breaking above 105 = reduce international/EM/commodity exposure. DXY breaking below 100 = add EM, commodities, multinationals. The dollar is the most important macro variable for global equities.

**#136: TED Spread Widening (3M LIBOR - 3M T-Bill)**
Direction: Market Down
Reliability: ~81%
Mechanism: The TED spread measures banking system stress. Widening spread = banks don't trust each other (charging more for interbank lending). This preceded 2008 by months. SOFR has replaced LIBOR, but credit spreads serve the same function.
Action: When the TED spread (or SOFR-Treasury equivalent) widens 50+ bps from its trough, reduce equity exposure. This is an early warning of credit stress.

**#137: Momentum Factor (12-1 Month Return)**
Direction: Market Up (for winners)
Reliability: ~80%
Mechanism: Stocks that have outperformed over the past 12 months (excluding the most recent month) tend to continue outperforming for 3-6 months. This is the most robust anomaly in finance, documented across markets and time periods.
Action: Go long the top decile of 12-1 month momentum stocks. Rebalance monthly. Short the bottom decile for a long-short factor portfolio. Works best in trending markets; fails during sharp reversals.

**#138: Mean Reversion Factor (5-Day RSI Extreme)**
Direction: Both (counter-trend)
Reliability: ~76%
Mechanism: Stocks that have dropped >10% in 5 days tend to bounce 3-5% in the following week. Stocks that have surged >10% in 5 days tend to give back 2-3%. Short-term mean reversion is the counter-thesis to momentum.
Action: Buy stocks that are oversold (5-day RSI <10) in an overall uptrend. Sell/short stocks that are overbought (5-day RSI >90) in a downtrend. Time horizon: 3-5 trading days.

**#139: Intermarket Divergence (Bonds vs Stocks)**
Direction: Market Down (for stocks)
Reliability: ~79%
Mechanism: When bonds rally (yields fall) while stocks also rally, one market is wrong. Bonds are pricing in economic weakness; stocks are pricing in growth. Historically, bonds are right more often.
Action: When TLT and SPY both trend up for 4+ weeks, be cautious on equities. Bonds tend to lead. If bonds reverse (yields rise) while stocks are still rising, the equity rally has more fuel.

**#140: Carry Trade Unwind (JPY Strengthening Sharply)**
Direction: Market Down
Reliability: ~82%
Mechanism: The yen carry trade (borrow cheap JPY, buy risk assets) is one of the largest trades in the world. When JPY strengthens sharply (>2% in a week), carry trades unwind — global risk assets sell off as leveraged positions close.
Action: Monitor USD/JPY. A sharp yen rally (JPY strengthening) is a sell signal for global equities, especially EM and high-beta tech. This triggered the Aug 2024 selloff.

**#141: Baltic Dry Index (Shipping Costs)**
Direction: Both
Reliability: ~75%
Mechanism: The BDI tracks shipping costs for dry bulk commodities. Rising BDI = growing global trade demand. Falling BDI = trade volumes declining. It can't be speculated on easily, making it a purer signal of real economic activity.
Action: Use BDI as a background global growth indicator. Rising BDI supports long commodity/industrial positions. Sharply declining BDI = global slowdown, reduce cyclical exposure.

**#142: MOVE Index (Bond Market Volatility)**
Direction: Market Down (when MOVE spikes)
Reliability: ~78%
Mechanism: The MOVE index measures Treasury market volatility. Spikes in MOVE signal bond market stress, which cascades into equity markets through credit conditions, margin calls, and portfolio rebalancing.
Action: MOVE above 120 = reduce equity exposure and increase hedges. Below 80 = calm bond market supports equity risk-taking. The 2023 MOVE spike preceded the SVB crisis.

**#143: Credit Default Swap (CDS) Spread Widening**
Direction: Market Down
Reliability: ~81%
Mechanism: CDS spreads price the cost of insuring against corporate default. Widening spreads = market pricing in higher default risk. CDS markets often lead equity markets at turning points because credit traders are typically smarter than equity traders.
Action: Track investment-grade CDS index (CDX.IG). Widening 20+ bps in a month = reduce equity exposure. CDS has led major equity drawdowns by 2-4 weeks.

**#144: Factor Crowding (Momentum Crash Risk)**
Direction: Market Down (for crowded factor)
Reliability: ~77%
Mechanism: When too much money chases the same factor (momentum, value, low-vol), the trade becomes crowded. When it reverses, everyone runs for the exit simultaneously, causing an outsized crash. Momentum crashes (like March 2009) are devastating.
Action: Track factor crowding via portfolio overlap metrics. When the top momentum stocks all have similar institutional holders, reduce momentum exposure. Diversify across uncorrelated factors.

**#145: Earnings Yield vs 10Y Treasury Yield (Equity Risk Premium)**
Direction: Both
Reliability: ~78%
Mechanism: The equity risk premium (S&P 500 E/P minus 10Y yield) measures the extra compensation for owning stocks vs bonds. When ERP is high (>3%), stocks are attractive. When it's near zero or negative, bonds offer better risk-adjusted returns.
Action: ERP above 3% = overweight equities. ERP below 1% = shift toward bonds. The current ERP level should inform overall equity allocation, not individual stock selection.

**#146: Put/Call Open Interest Ratio at Key Strikes**
Direction: Both
Reliability: ~76%
Mechanism: Large open interest at specific strike prices creates "pin" effects — market makers hedge creates gravitational pull toward max pain (the strike where the most options expire worthless). Options expiration weeks amplify this.
Action: Track max pain and large OI strikes for SPY. Price tends to gravitate toward max pain into Friday expiration. Position accordingly for OpEx week.

**#147: Crypto Exchange Liquidation Cascade**
Direction: Market Down then Up
Reliability: ~80%
Mechanism: Cascading liquidations happen when leveraged positions get force-closed, which pushes prices lower, which triggers more liquidations. Once the cascade exhausts (>$500M in 24hr liquidations), the market has been purged and typically bounces hard.
Action: Track liquidation data (Coinglass). During a cascade (>$500M/day), don't buy. After the cascade ends (liquidations drop to <$50M/hr), buy aggressively — the leveraged sellers are gone.

**#148: Options Gamma Pinning at Round Numbers**
Direction: Neutral (range-bound)
Reliability: ~75%
Mechanism: Large option open interest at round numbers ($100, $150, $200, $500) creates dealer hedging flows that "pin" the stock near that strike. The larger the OI, the stronger the pin effect. This suppresses volatility around that strike.
Action: If a stock has massive OI at a round number strike with <5 DTE, don't expect a big move. Wait until after expiration for the pin to release. Sell premium (strangles) around pinned strikes.

**#149: Relative Strength Index of the Index (Meta-RSI)**
Direction: Both
Reliability: ~74%
Mechanism: Tracking RSI of the S&P 500 itself (not individual stocks) gives a regime signal. SPX RSI above 70 for >2 weeks = strong trend, don't short. SPX RSI below 30 = oversold market, start accumulating. The market has a longer mean-reversion cycle than individual stocks.
Action: SPX daily RSI >70 for 10+ days = melt-up, stay long until RSI drops below 60. SPX RSI <30 = buy with 1-3 month horizon. Don't fight the index-level trend.

**#150: Correlation Regime Shift (Rolling 30-Day)**
Direction: Both
Reliability: ~77%
Mechanism: When the average correlation between S&P 500 stocks spikes above 0.7, the market is in "risk-on/risk-off" mode where everything moves together. When it drops below 0.3, it's a stock-picker's market where fundamentals matter more than macro.
Action: High correlation regime = trade the index, not individual stocks. Use SPY/QQQ. Low correlation regime = trade individual stocks, use sector/factor bets. Correlation regime determines the optimal strategy, not the direction.

---

## Summary: All 150 Factors by Category

| Category | Factors | Count |
|----------|---------|-------|
| Macro & Sentiment (Original) | #1-25 | 25 |
| Crypto On-Chain (Original) | #26-50 | 25 |
| Microstructure & Order Flow | #51-70 | 20 |
| Technical & Price Action | #71-90 | 20 |
| Fundamental & Earnings Quality | #91-110 | 20 |
| Event-Driven & Catalysts | #111-130 | 20 |
| Cross-Asset & Quantitative | #131-150 | 20 |
| **TOTAL** | | **150** |

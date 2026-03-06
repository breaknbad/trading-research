# Dashboard Data Audit — Mar 5, 2026

## Findings

### 1. ALL POSITIONS CLOSED
- vex: 0 OPEN, 126 CLOSED
- tars: 0 OPEN, 72 CLOSED  
- alfred: 0 OPEN, 58 CLOSED
- eddie_v: 0 OPEN, 116 CLOSED
- alfred_crypto: 0 OPEN, 144 CLOSED
- **Total: 0 OPEN across entire fleet. 516 CLOSED trades.**

### 2. 56 GARBAGE-PRICE TRADES
- BTC sold at $29-32 (should be $70K+)
- ETH sold at $18-20 (should be $2K+)
- ADA sold at $0.00
- All from CoinGecko returning garbage data
- All CLOSED — damage already done, but corrupting P&L calculations
- Most from vex_crypto bot_id (Mar 2-3), some from vex (Mar 4)

### 3. PORTFOLIO SNAPSHOTS TABLE BROKEN
- 400 Bad Request on all queries
- Either table schema changed or RLS blocking reads
- Dashboard can't read snapshots = dashboard shows nothing useful

### 4. BOT_ID CONTAMINATION
- 6 different bot_ids: vex, tars, alfred, eddie_v, alfred_crypto, vex_crypto
- Should be 4 (one per bot). The _crypto variants create duplicate tracking.

## Required Cleanup
1. Delete or mark garbage-price trades (56 records)
2. Fix portfolio_snapshots table access
3. Standardize bot_ids to 4 only
4. Rebuild snapshots from clean trade data
5. Verify dashboard reads correct data

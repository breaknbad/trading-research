#!/usr/bin/env python3
"""Main orchestrator: runs every 5 min via cron, ties everything together."""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone, timedelta

import config
import scanner
import risk_manager
import executor
import dashboard_sync

# ET offset (UTC-5 standard, UTC-4 daylight)
def _now_et():
    """Get current time in US Eastern. Simple DST approximation."""
    utc_now = datetime.now(timezone.utc)
    # DST: 2nd Sunday March - 1st Sunday November (approximate)
    year = utc_now.year
    march_second_sun = 8 + (6 - datetime(year, 3, 8).weekday()) % 7
    nov_first_sun = 1 + (6 - datetime(year, 11, 1).weekday()) % 7
    dst_start = datetime(year, 3, march_second_sun, 7, 0, tzinfo=timezone.utc)
    dst_end = datetime(year, 11, nov_first_sun, 6, 0, tzinfo=timezone.utc)
    offset = timedelta(hours=-4) if dst_start <= utc_now < dst_end else timedelta(hours=-5)
    return utc_now + offset, offset


def is_market_open():
    """Check if US market is currently open."""
    et_now, _ = _now_et()
    # Weekday check (Mon=0, Fri=4)
    if et_now.weekday() > 4:
        return False, "Weekend"
    market_open = et_now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = et_now.replace(hour=16, minute=0, second=0, microsecond=0)
    if et_now < market_open:
        return False, "Pre-market"
    if et_now >= market_close:
        return False, "After hours"
    return True, "Market open"


def is_scout_allowed():
    """Check if we're before the scout cutoff time."""
    et_now, _ = _now_et()
    cutoff = et_now.replace(hour=config.SCOUT_CUTOFF_HOUR, minute=config.SCOUT_CUTOFF_MINUTE, second=0)
    return et_now < cutoff


def _setup_logging():
    """Set up daily log file."""
    os.makedirs(config.LOGS_DIR, exist_ok=True)
    log_file = os.path.join(config.LOGS_DIR, datetime.now().strftime("%Y-%m-%d") + ".log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )
    return logging.getLogger("alfred")


def run_cycle(force=False, dry_run=False, verbose=True):
    """
    Run one complete trading cycle. Returns summary string.
    """
    logger = _setup_logging()
    et_now, _ = _now_et()
    logger.info(f"=== CYCLE START {et_now.strftime('%Y-%m-%d %H:%M ET')} ===")

    summary_lines = []

    # 1. Market hours check
    if not force:
        market_open, reason = is_market_open()
        if not market_open:
            msg = f"Market closed: {reason}"
            logger.info(msg)
            return msg

    # 2. Risk check
    logger.info("Running risk checks...")
    risk = risk_manager.check_risk(verbose=verbose)
    portfolio = risk.get("portfolio")

    if not portfolio:
        msg = "❌ No portfolio data - aborting cycle"
        logger.info(msg)
        return msg

    total_value = float(portfolio.get("total_value_usd", config.STARTING_CAPITAL))
    summary_lines.append(f"💰 Portfolio: ${total_value:,.2f}")

    # 3. Execute closes (stop losses, risk violations)
    closed = []
    for pos_info in risk["positions_to_close"]:
        if dry_run:
            logger.info(f"[DRY RUN] Would close {pos_info['ticker']}: {pos_info['reason']}")
            closed.append(pos_info["ticker"])
        else:
            result = executor.execute_close(pos_info, verbose=verbose)
            if result:
                closed.append(f"{result['action']} {result['shares']}x {result['ticker']}")
                logger.info(f"Closed: {result['action']} {result['shares']}x {result['ticker']}")

    if closed:
        summary_lines.append(f"🔴 Closed: {', '.join(closed)}")

    # 4. Circuit breaker and hard limits only (cooldown handled per-signal)
    if risk["circuit_breaker"]:
        summary_lines.append("🛑 Circuit breaker active - no new trades")
        logger.info("Circuit breaker active")
    else:
        # 5. Scan for signals
        logger.info("Scanning for signals...")
        signals = scanner.scan(verbose=verbose)

        if signals:
            scout_ok = is_scout_allowed()
            executed = []
            for signal in signals:
                # Skip scouts after cutoff
                if signal["tier"] == "SCOUT" and not scout_ok:
                    logger.info(f"[SKIP] Scout {signal['ticker']} after 3:30 PM cutoff")
                    continue

                if dry_run:
                    logger.info(f"[DRY RUN] Would trade {signal['tier']} {signal['direction']} {signal['ticker']}")
                    executed.append(f"{signal['tier']} {signal['ticker']}")
                else:
                    result = executor.execute_open(signal, portfolio, verbose=verbose)
                    if result:
                        executed.append(f"{result['tier']} {result['action']} {result['shares']}x {result['ticker']}")
                        logger.info(f"Executed: {result['tier']} {result['action']} {result['shares']}x {result['ticker']}")
                        # Re-check hard limits only (daily max, circuit breaker)
                        # Don't re-check cooldown mid-cycle — allow batch execution
                        risk = risk_manager.check_risk(verbose=False)
                        if risk["circuit_breaker"]:
                            logger.info("Hard limit reached, stopping")
                            break

            if executed:
                summary_lines.append(f"🟢 Trades: {', '.join(executed)}")
            else:
                summary_lines.append("📊 Signals found but none executed")
        else:
            summary_lines.append("📊 No signals detected")

    # 6. Dashboard sync
    if not dry_run:
        logger.info("Syncing dashboard...")
        try:
            dashboard_sync.sync_dashboard(verbose=verbose)
        except Exception as e:
            logger.info(f"Dashboard sync error: {e}")

    summary = f"**Alfred** {et_now.strftime('%H:%M ET')} | " + " | ".join(summary_lines)
    logger.info(f"=== CYCLE END === {summary}")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run one trading cycle")
    parser.add_argument("--force", action="store_true", help="Run even if market is closed")
    parser.add_argument("--dry-run", action="store_true", help="Don't execute trades")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    summary = run_cycle(force=args.force, dry_run=args.dry_run, verbose=not args.quiet)
    print(f"\n{summary}")

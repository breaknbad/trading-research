#!/usr/bin/env python3
"""
pre_deploy_check.py — Run before ANY code change to trading scripts.
If this fails, DO NOT DEPLOY. Period.

Usage: python3 pre_deploy_check.py
Exit 0 = safe to deploy. Exit 1 = fix issues first.
"""

import subprocess
import sys
import os

CHECKS = []
FAILURES = []


def check(name):
    def decorator(fn):
        CHECKS.append((name, fn))
        return fn
    return decorator


@check("Unit tests pass")
def run_tests():
    result = subprocess.run(
        [sys.executable, "tests/test_stop_check.py"],
        capture_output=True, text=True, cwd=os.path.dirname(__file__) or "."
    )
    if result.returncode != 0:
        return False, result.stdout + result.stderr
    return True, "All tests passed"


@check("stop_check.py has STOP GUARD")
def check_stop_guard():
    with open(os.path.join(os.path.dirname(__file__), "stop_check.py")) as f:
        code = f.read()
    if "gain_pct" not in code or "STOP GUARD" not in code:
        return False, "STOP GUARD (gain_pct > 0 check) missing from stop_check.py"
    return True, "STOP GUARD present"


@check("stop_check.py has price sanity import")
def check_price_sanity():
    with open(os.path.join(os.path.dirname(__file__), "stop_check.py")) as f:
        code = f.read()
    if "price_sanity" not in code and "sanity_check" not in code:
        return False, "Price sanity gate not imported in stop_check.py"
    return True, "Price sanity gate active"


@check("No --auto-execute in launchd plists")
def check_no_auto_execute():
    plist_dir = os.path.expanduser("~/Library/LaunchAgents")
    bad = []
    for f in os.listdir(plist_dir):
        if f.startswith("com.miai.") and f.endswith(".plist"):
            path = os.path.join(plist_dir, f)
            with open(path) as fh:
                content = fh.read()
            # Only stop_check should have auto-execution capability
            if "stopcheck" in f:
                continue
            if "--auto-execute" in content or "--auto-scale" in content:
                bad.append(f)
    if bad:
        return False, f"Auto-execute flags found in: {', '.join(bad)}"
    return True, "No rogue auto-execute flags"


@check("portfolio_guard uses $50K baseline")
def check_portfolio_guard():
    guard_path = os.path.join(os.path.dirname(__file__), "portfolio_guard.py")
    if not os.path.exists(guard_path):
        return True, "portfolio_guard.py not found (skip)"
    with open(guard_path) as f:
        code = f.read()
    if "STARTING_CAPITAL = 25000" in code:
        return False, "STARTING_CAPITAL still set to $25K (should be $50K)"
    return True, "Baseline correct"


@check("stop_check.py has CoinGecko fallback")
def check_coingecko_fallback():
    with open(os.path.join(os.path.dirname(__file__), "stop_check.py")) as f:
        code = f.read()
    if "coingecko" not in code.lower():
        return False, "No CoinGecko fallback in stop_check.py — Yahoo-only is fragile"
    return True, "CoinGecko fallback present"


@check("stop_check.py has ticker normalization")
def check_ticker_norm():
    with open(os.path.join(os.path.dirname(__file__), "stop_check.py")) as f:
        code = f.read()
    if "CRYPTO_BARE" not in code:
        return False, "Ticker normalization (CRYPTO_BARE) missing — bare BTC will return $32"
    return True, "Ticker normalization present"


def main():
    print("🔍 PRE-DEPLOY CHECK — Trading Research")
    print("=" * 50)

    for name, fn in CHECKS:
        try:
            ok, msg = fn()
            status = "✅" if ok else "❌"
            print(f"  {status} {name}: {msg}")
            if not ok:
                FAILURES.append(name)
        except Exception as e:
            print(f"  💥 {name}: CRASHED — {e}")
            FAILURES.append(name)

    print("=" * 50)
    if FAILURES:
        print(f"  🚫 {len(FAILURES)} FAILED — DO NOT DEPLOY")
        for f in FAILURES:
            print(f"     ↳ {f}")
        sys.exit(1)
    else:
        print(f"  ✅ {len(CHECKS)} checks passed — SAFE TO DEPLOY")
        sys.exit(0)


if __name__ == "__main__":
    main()

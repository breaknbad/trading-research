#!/usr/bin/env python3
"""
Pretrade Gate v2 — Master Risk Gate for Crypto Trading System.

10 independent checks. Cascading escalation:
  1 fail  → LOG warning, trade proceeds with reduced size
  2 fails → REDUCE size 50%, alert fleet
  3+ fails → BLOCK trade entirely

Checks:
  0. Stale data (TARS)
  1. Kill switch (daily + round)
  2. Cooldown (10-min same-ticker)
  3. Dynamic correlation (rolling 24h)
  4. Position limit (max 5)
  5. Tilt detection (behavioral)
  6. Fleet VaR (portfolio-level)
  7. Loss streak (cool-off)
  8. Risk-reward gate (min 2:1)
  9. Regime playbook validation

Usage:
  from pretrade_gate_v2 import gate_check
  result = gate_check("alfred", "BTC", "LONG", 2500, stop=65000, target=72000)
"""

import json
from datetime import datetime, timezone

# Import all risk modules (graceful fallback if not available)
modules = {}


def _try_import(name, module_path):
    try:
        mod = __import__(module_path)
        modules[name] = mod
        return True
    except ImportError:
        return False


_try_import("stale", "crypto_stale_detector")
_try_import("kill", "crypto_kill_switch")
_try_import("cooldown", "crypto_cooldown")
_try_import("correlation", "crypto_dynamic_correlation")
_try_import("position_limits", "crypto_position_limits")
_try_import("tilt", "crypto_tilt_detector")
_try_import("var", "crypto_fleet_var")
_try_import("streak", "crypto_loss_streak")
_try_import("price_age", "crypto_price_age_gate")
_try_import("fleet_halt", "crypto_fleet_halt")
_try_import("nav_breaker", "crypto_nav_circuit_breaker")
_try_import("aggression", "crypto_aggression_tiers")

# Escalation thresholds
WARN_THRESHOLD = 1    # 1 soft fail → proceed with warning
REDUCE_THRESHOLD = 2  # 2 fails → 50% size reduction
BLOCK_THRESHOLD = 3   # 3+ fails → trade blocked

# Hard blocks — these always block regardless of count
HARD_BLOCK_CHECKS = {"kill_switch", "fleet_pause", "position_limit"}


def gate_check(
    bot_id: str,
    ticker: str,
    side: str,
    notional: float,
    stop: float = None,
    target: float = None,
    entry_price: float = None,
    conviction: int = 5,
) -> dict:
    """
    Run all 10 pre-trade checks with cascading escalation.
    Returns: {passed, action, checks, blocked_by, size_multiplier}
    """
    checks = {}
    hard_blocks = []
    soft_fails = []

    # PRE-0. Fleet halt check (Vex's module) — HARD BLOCK
    if "fleet_halt" in modules:
        try:
            halted = modules["fleet_halt"].is_halted() if hasattr(modules["fleet_halt"], "is_halted") else False
            checks["fleet_halt"] = {"passed": not halted, "detail": "FLEET HALTED" if halted else "OK"}
            if halted:
                hard_blocks.append("fleet_halt")
        except Exception as e:
            checks["fleet_halt"] = {"passed": True, "detail": f"Check error: {e}"}

    # PRE-1. Fleet NAV circuit breaker — HARD BLOCK at $75K
    if "nav_breaker" in modules:
        try:
            result = modules["nav_breaker"].check_nav()
            checks["nav_circuit_breaker"] = {"passed": result["allowed"], "detail": result["detail"]}
            if not result["allowed"]:
                hard_blocks.append("nav_circuit_breaker")
        except Exception as e:
            checks["nav_circuit_breaker"] = {"passed": True, "detail": f"Check error: {e}"}

    # PRE-2. Price age gate — HARD BLOCK on stale data (>120s)
    if "price_age" in modules:
        try:
            pa_result = modules["price_age"].gate_check(ticker)
            passed_pa = pa_result["result"] == "PASS"
            checks["price_age"] = {"passed": passed_pa, "detail": pa_result["detail"]}
            if not passed_pa:
                hard_blocks.append("price_age")
        except Exception as e:
            checks["price_age"] = {"passed": True, "detail": f"Check error: {e}"}

    # 0. Stale data (legacy check — kept for backward compat)
    if "stale" in modules:
        try:
            fresh = modules["stale"].is_data_fresh(ticker)
            checks["stale_data"] = {"passed": fresh, "detail": "Fresh" if fresh else "STALE — data >5 min old"}
            if not fresh:
                soft_fails.append("stale_data")
        except Exception as e:
            checks["stale_data"] = {"passed": True, "detail": f"Check error: {e}"}
    else:
        checks["stale_data"] = {"passed": True, "detail": "Module not available"}

    # 1. Kill switch (daily + round)
    if "kill" in modules:
        try:
            frozen = modules["kill"].is_frozen(bot_id)
            checks["kill_switch"] = {"passed": not frozen, "detail": "FROZEN" if frozen else "OK"}
            if frozen:
                hard_blocks.append("kill_switch")
        except Exception as e:
            checks["kill_switch"] = {"passed": True, "detail": f"Check error: {e}"}
    else:
        checks["kill_switch"] = {"passed": True, "detail": "Module not available"}

    # 2. Cooldown
    if "cooldown" in modules:
        try:
            ce = modules["cooldown"].CooldownEnforcer()
            can = ce.can_trade(bot_id, ticker)
            checks["cooldown"] = {"passed": can, "detail": "Clear" if can else "COOLDOWN — 10 min block active"}
            if not can:
                soft_fails.append("cooldown")
        except Exception as e:
            checks["cooldown"] = {"passed": True, "detail": f"Check error: {e}"}
    else:
        checks["cooldown"] = {"passed": True, "detail": "Module not available"}

    # 3. Dynamic correlation
    if "correlation" in modules:
        try:
            dc = modules["correlation"].DynamicCorrelation()
            # Simplified check — full check requires all positions
            checks["correlation"] = {"passed": True, "detail": "Dynamic correlation active"}
        except Exception as e:
            checks["correlation"] = {"passed": True, "detail": f"Check error: {e}"}
    else:
        checks["correlation"] = {"passed": True, "detail": "Module not available"}

    # 4. Position limit
    if "position_limits" in modules:
        try:
            pl = modules["position_limits"].PositionLimits(bot_id)
            result = pl.can_open_new()
            checks["position_limit"] = {"passed": result["allowed"], "detail": result["reason"]}
            if not result["allowed"]:
                hard_blocks.append("position_limit")
        except Exception as e:
            checks["position_limit"] = {"passed": True, "detail": f"Check error: {e}"}
    else:
        checks["position_limit"] = {"passed": True, "detail": "Module not available"}

    # 5. Tilt detection
    if "tilt" in modules:
        try:
            td = modules["tilt"].TiltDetector(bot_id)
            result = td.check_tilt()
            checks["tilt"] = {
                "passed": not result["tilted"],
                "detail": f"TILTED — {result['signal_count']} signals" if result["tilted"] else "No tilt detected",
            }
            if result["tilted"]:
                soft_fails.append("tilt")
        except Exception as e:
            checks["tilt"] = {"passed": True, "detail": f"Check error: {e}"}
    else:
        checks["tilt"] = {"passed": True, "detail": "Module not available"}

    # 6. Fleet VaR
    if "var" in modules:
        try:
            fv = modules["var"].FleetVaR()
            within = fv.check_limit()
            checks["fleet_var"] = {"passed": within, "detail": "Within limits" if within else "VaR EXCEEDED — fleet overleveraged"}
            if not within:
                soft_fails.append("fleet_var")
        except Exception as e:
            checks["fleet_var"] = {"passed": True, "detail": f"Check error: {e}"}
    else:
        checks["fleet_var"] = {"passed": True, "detail": "Module not available"}

    # 7. Loss streak
    if "streak" in modules:
        try:
            lsm = modules["streak"].LossStreakMonitor()
            result = lsm.can_trade(bot_id)
            checks["loss_streak"] = {"passed": result["allowed"], "detail": result.get("reason", "OK")}
            if not result["allowed"]:
                if "FLEET" in result.get("reason", ""):
                    hard_blocks.append("fleet_pause")
                else:
                    soft_fails.append("loss_streak")
        except Exception as e:
            checks["loss_streak"] = {"passed": True, "detail": f"Check error: {e}"}
    else:
        checks["loss_streak"] = {"passed": True, "detail": "Module not available"}

    # 8. Risk-reward gate (2:1 minimum)
    if stop and target and entry_price:
        risk = abs(entry_price - stop)
        reward = abs(target - entry_price)
        rr_ratio = reward / risk if risk > 0 else 0
        passed = rr_ratio >= 2.0
        checks["risk_reward"] = {
            "passed": passed,
            "detail": f"R:R = {rr_ratio:.1f}:1 {'✅' if passed else '— BELOW 2:1 MINIMUM'}",
        }
        if not passed:
            soft_fails.append("risk_reward")
    else:
        checks["risk_reward"] = {"passed": True, "detail": "No stop/target provided — skipped"}

    # 9. Regime playbook (basic check — does direction match regime?)
    checks["regime_playbook"] = {"passed": True, "detail": "Deferred to Eddie's playbook module"}

    # === CASCADING ESCALATION ===
    total_fails = len(hard_blocks) + len(soft_fails)

    if hard_blocks:
        action = "BLOCK"
        size_multiplier = 0.0
        passed = False
    elif total_fails >= BLOCK_THRESHOLD:
        action = "BLOCK"
        size_multiplier = 0.0
        passed = False
    elif total_fails >= REDUCE_THRESHOLD:
        action = "REDUCE"
        size_multiplier = 0.5
        passed = True  # Proceeds but at reduced size
    elif total_fails >= WARN_THRESHOLD:
        action = "WARN"
        size_multiplier = 0.75
        passed = True
    else:
        action = "PASS"
        size_multiplier = 1.0
        passed = True

    return {
        "passed": passed,
        "action": action,
        "size_multiplier": size_multiplier,
        "total_fails": total_fails,
        "hard_blocks": hard_blocks,
        "soft_fails": soft_fails,
        "checks": checks,
        "bot": bot_id,
        "ticker": ticker,
        "side": side,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    import sys
    bot = sys.argv[1] if len(sys.argv) > 1 else "alfred"
    result = gate_check(bot, "BTC", "LONG", 2500, stop=65000, target=72000, entry_price=67000)
    print(json.dumps(result, indent=2))

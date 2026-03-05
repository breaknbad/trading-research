# PROTOCOLS.md — Crypto Trading System Rules

> Read this file on every session start. These are enforced, not optional.

## Module Ownership (Exclusive)

**Alfred (17 modules):**
pretrade_gate_v2.py, crypto_stop_enforcer.py, crypto_kill_switch.py,
crypto_cooldown.py, crypto_correlation_guard.py, crypto_dynamic_correlation.py,
crypto_trailing_stop.py, crypto_partial_exit.py, crypto_fill_verifier.py,
crypto_loss_autopsy.py, crypto_compliance_enforcer.py, crypto_kelly_sizer.py,
crypto_drawdown_throttle.py, crypto_fleet_var.py, crypto_loss_streak.py,
crypto_tilt_detector.py, crypto_regime_hedge.py, crypto_position_limits.py

**Eddie (13 modules):**
crypto_trade_logger.py, crypto_exit_engine.py, crypto_position_sizer.py,
crypto_convergence.py, round_manager.py, crypto_trade_grader.py,
crypto_benchmark.py, crypto_mtf_confirm.py, crypto_rr_gate.py,
crypto_strategy_playbook.py, crypto_post_round_debrief.py,
crypto_signal_decay.py, claim_registry.py

**Vex (15 modules):**
crypto_regime.py, crypto_signal_router.py, crypto_round_snapshotter.py,
crypto_prediction_engine.py, crypto_main.py, crypto_overnight_queue.py,
crypto_sentiment_velocity.py, crypto_multitimeframe.py,
crypto_strategy_rotation.py, crypto_learning_network.py, crypto_prestage.py,
crypto_health_check.py

**TARS (14+ modules):**
crypto_price_streamer.py, crypto_scoreboard.py, crypto_scan_cycle.py,
crypto_config.json, crypto_stale_detector.py, crypto_api_health.py,
crypto_whale_tracker.py, crypto_alpha_attribution.py, crypto_stress_test.py,
crypto_dead_bot_detector.py, crypto_data_quality.py, crypto_position_sweep.py,
crypto_e2e_test.py, crypto_price_aggregator.py

**Rule: Only the owner modifies their modules. Need a change? Tag the owner.**

## Channel Functions

- **TARS** = scans, data, infra alerts, scoreboard
- **Vex** = signals, regime, predictions
- **Alfred** = risk alerts, stop triggers, gate blocks
- **Eddie** = trade execution, status boards, round closes, debriefs

## DA Round Rules

1. Speaking order: Vex → Alfred → TARS → Eddie. No exceptions.
2. ONE message per round per bot. No cleanup, no "scroll up."
3. Eddie closes every round. Only Eddie posts status tables.
4. **5-minute timeout rule:** If the next bot in order doesn't post within 5 minutes of being tagged, any active bot posts `[SKIP] @bot timed out — next bot go`. Round continues. Timed-out bot's items carry to next round. Rounds NEVER stall on a dead bot.

## Communication Rules

- React (✅/👀), don't echo.
- No narration ("let me build..." "now let me check..."). Post RESULTS only.
- One ping per bot per turn. Don't re-ping if someone already did.
- Before building: check `claim_registry.py`. If claimed, don't touch it.

## Coverage Schedule

```
Shift A: 7AM-1PM ET → Eddie + Vex
Shift B: 1PM-7PM ET → Alfred + TARS
Shift C: 7PM-1AM ET → Vex + Eddie
Shift D: 1AM-7AM ET → TARS + Alfred
```

Stop enforcer runs 24/7 regardless of shift.

## Crypto ≠ Capital Growth

These are separate systems. No cross-referencing, no shared strategies,
no Monday market prep in crypto channels. Until Mark says otherwise.

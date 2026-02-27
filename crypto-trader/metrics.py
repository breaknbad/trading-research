"""
Performance metrics for backtest results.
"""

import numpy as np
import pandas as pd

from strategy import BacktestResult


def compute_metrics(result: BacktestResult, initial_capital: float = 10_000.0) -> dict:
    """
    Compute standard trading performance metrics.

    Returns dict with:
        total_return_pct, win_rate, sharpe_ratio, max_drawdown_pct, num_trades,
        num_wins, num_losses, avg_win_pct, avg_loss_pct, profit_factor
    """
    trades = result.trades
    equity = result.equity_curve

    metrics = {}

    # --- Basic counts ---
    metrics["num_trades"] = len(trades)

    if not trades:
        metrics.update({
            "total_return_pct": 0.0,
            "win_rate": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "num_wins": 0,
            "num_losses": 0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "profit_factor": 0.0,
        })
        return metrics

    # --- Total return ---
    final_equity = equity.iloc[-1]
    metrics["total_return_pct"] = ((final_equity - initial_capital) / initial_capital) * 100

    # --- Win / loss breakdown ---
    wins = [t for t in trades if t.is_win]
    losses = [t for t in trades if not t.is_win]

    metrics["num_wins"] = len(wins)
    metrics["num_losses"] = len(losses)
    metrics["win_rate"] = (len(wins) / len(trades)) * 100

    metrics["avg_win_pct"] = (
        np.mean([t.return_pct * 100 for t in wins]) if wins else 0.0
    )
    metrics["avg_loss_pct"] = (
        np.mean([t.return_pct * 100 for t in losses]) if losses else 0.0
    )

    # --- Profit factor ---
    gross_profit = sum(t.return_pct for t in wins) if wins else 0.0
    gross_loss = abs(sum(t.return_pct for t in losses)) if losses else 0.0
    metrics["profit_factor"] = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # --- Sharpe ratio (annualized, assuming hourly returns) ---
    returns = equity.pct_change().dropna()
    if len(returns) > 1 and returns.std() > 0:
        # Annualize: ~8760 hours in a year
        metrics["sharpe_ratio"] = round(
            (returns.mean() / returns.std()) * np.sqrt(8760), 4
        )
    else:
        metrics["sharpe_ratio"] = 0.0

    # --- Max drawdown ---
    cummax = equity.cummax()
    drawdown = (equity - cummax) / cummax
    metrics["max_drawdown_pct"] = abs(drawdown.min()) * 100

    return metrics


def print_report(metrics: dict, product_id: str = "BTC-USD") -> None:
    """Pretty-print a backtest performance report."""
    print("\n" + "=" * 55)
    print(f"  BACKTEST REPORT — {product_id}")
    print("=" * 55)
    print(f"  Total Return:      {metrics['total_return_pct']:>+10.2f}%")
    print(f"  Max Drawdown:      {metrics['max_drawdown_pct']:>10.2f}%")
    print(f"  Sharpe Ratio:      {metrics['sharpe_ratio']:>10.4f}")
    print("-" * 55)
    print(f"  Total Trades:      {metrics['num_trades']:>10d}")
    print(f"  Wins / Losses:     {metrics['num_wins']:>4d} / {metrics['num_losses']:<4d}")
    print(f"  Win Rate:          {metrics['win_rate']:>10.1f}%")
    print(f"  Avg Win:           {metrics['avg_win_pct']:>+10.2f}%")
    print(f"  Avg Loss:          {metrics['avg_loss_pct']:>+10.2f}%")
    print(f"  Profit Factor:     {metrics['profit_factor']:>10.2f}")
    print("=" * 55 + "\n")

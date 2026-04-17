"""Risk-adjusted performance metrics.

All metrics accept a sequence of *per-trade* or *per-period* returns
plus an optional dollar-PnL series and ``capital_base`` that anchors
the "total return" calculation to a fixed denominator — this avoids
the "chained-product explosion" you get when 7000+ independent
arbitrage trades are compounded against a $1 nominal base.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import numpy as np


@dataclass
class PerformanceMetrics:
    total_return: float
    cagr: float
    mean_period_return: float
    volatility: float
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float
    win_rate: float
    n_trades: int
    gross_profit: float
    gross_loss: float
    profit_factor: float
    total_pnl: float
    capital_base: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_metrics(
    returns: np.ndarray,
    pnl_per_trade: np.ndarray | None = None,
    periods_per_year: int = 252,
    risk_free: float = 0.04,
    initial_capital: float = 1.0,
    capital_base: float | None = None,
    compound: bool = False,
) -> PerformanceMetrics:
    """Compute standard risk-adjusted metrics.

    Parameters
    ----------
    returns
        Per-trade ROIC (or per-period simple returns).  Used for
        Sharpe / Sortino / volatility.
    pnl_per_trade
        Per-trade dollar PnL.  If present, the equity curve and
        max drawdown are computed on the cumulative *dollar* PnL —
        this is the correct model for recycled-capital arb books.
    periods_per_year
        Annualisation factor: daily 252, weekly 52, hourly 8760,
        per-event (e.g. multiple events per day) → set accordingly.
    risk_free
        Annual risk-free rate for the Sharpe excess-return calc.
    capital_base
        Denominator for total-return quoting.  Defaults to
        ``sum(notional per trade)`` ≈ ``sum(pnl)`` fallback to 1.
    compound
        Compound per-period returns instead of linear aggregation.
    """
    returns = np.asarray(returns, dtype=float)
    if returns.size == 0:
        return _empty_metrics()

    if pnl_per_trade is not None and len(pnl_per_trade) > 0:
        pnl = np.asarray(pnl_per_trade, dtype=float)
    else:
        pnl = returns

    total_pnl = float(pnl.sum())
    cb = float(capital_base) if capital_base is not None else 1.0

    n_periods = len(returns)
    years = n_periods / periods_per_year if periods_per_year > 0 else 1.0

    if compound:
        equity = np.cumprod(1.0 + returns) * initial_capital
        total_return = float(equity[-1] / initial_capital - 1.0)
        cagr = (equity[-1] / initial_capital) ** (1.0 / max(years, 1e-9)) - 1.0 if years > 0 else 0.0
    else:
        # Linear aggregation in *dollar* space — the honest model for
        # an arb book that recycles ``cb`` through each trade.
        equity = cb + np.cumsum(pnl)
        total_return = total_pnl / cb if cb > 0 else 0.0
        cagr = total_return / max(years, 1e-9) if years > 0 else 0.0

    mean_r = float(np.mean(returns))
    vol = float(np.std(returns, ddof=1)) if n_periods > 1 else 0.0
    ann_vol = vol * np.sqrt(periods_per_year)

    rf_per_period = risk_free / periods_per_year
    excess = returns - rf_per_period
    sharpe = (
        float(np.mean(excess) / np.std(returns, ddof=1) * np.sqrt(periods_per_year))
        if vol > 0 else 0.0
    )

    downside = returns[returns < 0]
    dd_std = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0
    sortino = (
        float(np.mean(excess) / dd_std * np.sqrt(periods_per_year)) if dd_std > 1e-10 else 0.0
    )

    # Max drawdown on dollar equity curve.
    running_max = np.maximum.accumulate(equity)
    drawdown = (equity - running_max) / np.maximum(running_max, 1e-9)
    max_dd = float(drawdown.min()) if len(drawdown) else 0.0
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0

    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    win_rate = float(len(wins) / len(pnl)) if len(pnl) else 0.0
    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    return PerformanceMetrics(
        total_return=total_return,
        cagr=cagr,
        mean_period_return=mean_r,
        volatility=ann_vol,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        max_drawdown=max_dd,
        win_rate=win_rate,
        n_trades=int(len(pnl)),
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,
        total_pnl=total_pnl,
        capital_base=cb,
    )


def _empty_metrics() -> PerformanceMetrics:
    return PerformanceMetrics(
        total_return=0.0,
        cagr=0.0,
        mean_period_return=0.0,
        volatility=0.0,
        sharpe=0.0,
        sortino=0.0,
        calmar=0.0,
        max_drawdown=0.0,
        win_rate=0.0,
        n_trades=0,
        gross_profit=0.0,
        gross_loss=0.0,
        profit_factor=0.0,
        total_pnl=0.0,
        capital_base=0.0,
    )


# ---------------------------------------------------------------------------
# Kelly helpers — adapted from Ludescher (2024)
# ---------------------------------------------------------------------------


def kelly_fraction(p: float, market_price: float) -> float:
    """Optimal fraction of capital per Kelly for a binary 0/1-settling contract."""
    if not 0.0 < market_price < 1.0:
        return 0.0
    f = (p - market_price) / (1.0 - market_price)
    return float(max(-1.0, min(1.0, f)))


def half_kelly(p: float, market_price: float) -> float:
    """Half-Kelly — matches PDX house convention."""
    return 0.5 * kelly_fraction(p, market_price)

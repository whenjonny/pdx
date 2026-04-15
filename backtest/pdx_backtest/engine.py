"""Backtest engine — glues strategies, data, and metrics together."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from pdx_backtest.metrics import PerformanceMetrics, compute_metrics
from pdx_backtest.strategies.base import StrategyResult


@dataclass
class BacktestResult:
    strategy_name: str
    metrics: PerformanceMetrics
    strategy_result: StrategyResult
    params: dict[str, Any] = field(default_factory=dict)

    def summary_line(self) -> str:
        m = self.metrics
        return (
            f"{self.strategy_name:28s} "
            f"trades={m.n_trades:4d}  "
            f"total={m.total_return:+.2%}  "
            f"CAGR={m.cagr:+.2%}  "
            f"Sharpe={m.sharpe:+.2f}  "
            f"Sortino={m.sortino:+.2f}  "
            f"MDD={m.max_drawdown:+.2%}  "
            f"win={m.win_rate:.2%}  "
            f"PF={m.profit_factor:.2f}"
        )


class BacktestEngine:
    """Thin wrapper that records metrics for each strategy run."""

    def __init__(
        self,
        periods_per_year: int = 252,
        risk_free: float = 0.04,
    ) -> None:
        self.periods_per_year = periods_per_year
        self.risk_free = risk_free
        self._results: list[BacktestResult] = []

    # ------------------------------------------------------------------
    def evaluate(
        self,
        strategy_result: StrategyResult,
        periods_per_year: int | None = None,
        initial_capital: float = 1.0,
        capital_base: float | None = None,
    ) -> BacktestResult:
        ppy = periods_per_year or self.periods_per_year
        metrics = compute_metrics(
            returns=strategy_result.returns,
            pnl_per_trade=strategy_result.pnl_per_trade,
            periods_per_year=ppy,
            risk_free=self.risk_free,
            initial_capital=initial_capital,
            capital_base=capital_base,
        )
        result = BacktestResult(
            strategy_name=strategy_result.name,
            metrics=metrics,
            strategy_result=strategy_result,
            params=dict(strategy_result.notes),
        )
        self._results.append(result)
        return result

    # ------------------------------------------------------------------
    @property
    def results(self) -> list[BacktestResult]:
        return list(self._results)

    def comparison_table(self) -> str:
        header = (
            f"{'Strategy':28s} trades  total         CAGR          Sharpe    "
            f"Sortino   MDD          Win       PF"
        )
        lines = [header, "-" * len(header)]
        for r in self._results:
            lines.append(r.summary_line())
        return "\n".join(lines)

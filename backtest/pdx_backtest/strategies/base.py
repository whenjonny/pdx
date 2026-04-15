"""Strategy base class and shared types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class Trade:
    """A single executed trade in a backtest."""

    step: int
    action: str             # e.g. "buy_yes_all", "sell_no_i=2"
    notional: float         # USDC committed
    pnl: float              # realised (at settlement) PnL in USDC
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyResult:
    """Output of running a strategy over one or more markets."""

    name: str
    trades: list[Trade]
    equity_curve: np.ndarray
    returns: np.ndarray
    pnl_per_trade: np.ndarray
    capital_deployed: float
    capital_lockup_period_steps: int
    notes: dict[str, Any] = field(default_factory=dict)

    @property
    def n_trades(self) -> int:
        return len(self.trades)


class Strategy:
    """Minimal strategy interface.

    Concrete strategies override ``run(...)`` and return a
    ``StrategyResult``.  They are intentionally stateless across calls
    — the engine composes runs to build aggregate statistics.
    """

    name: str = "base"

    def run(self, *args, **kwargs) -> StrategyResult:  # pragma: no cover
        raise NotImplementedError

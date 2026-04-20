"""Portfolio tracker — tracks positions and P&L across both venues."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

from pdx_arb.types import ArbTrade, Venue


@dataclass
class PositionSummary:
    pair_id: str
    question: str
    buy_venue: Venue
    sell_venue: Venue
    size_usd: float
    entry_spread_bps: float
    current_spread_bps: float = 0.0
    unrealized_pnl: float = 0.0
    entry_time: float = 0.0


@dataclass
class PortfolioSnapshot:
    timestamp: float
    total_equity: float
    realized_pnl: float
    unrealized_pnl: float
    open_positions: int
    total_trades: int
    win_rate: float
    avg_pnl_per_trade: float
    sharpe: float
    max_drawdown_pct: float


class PortfolioTracker:
    """Tracks all positions and P&L for the arbitrage book."""

    def __init__(self, initial_capital: float = 100_000.0) -> None:
        self.initial_capital = initial_capital
        self._realized_pnl = 0.0
        self._trade_pnls: list[float] = []
        self._equity_curve: list[tuple[float, float]] = [(time.time(), initial_capital)]
        self._peak_equity = initial_capital
        self._max_drawdown = 0.0
        self._open_trades: dict[str, ArbTrade] = {}
        self._closed_trades: list[ArbTrade] = []
        self._venue_pnl: dict[Venue, float] = defaultdict(float)

    def record_open(self, trade: ArbTrade) -> None:
        """Record a newly opened position."""
        if trade.status == "filled":
            self._open_trades[trade.trade_id] = trade

    def record_close(self, trade: ArbTrade) -> None:
        """Record a settled/closed position."""
        if trade.trade_id in self._open_trades:
            del self._open_trades[trade.trade_id]
        trade.settled = True
        self._closed_trades.append(trade)
        self._realized_pnl += trade.pnl_net
        self._trade_pnls.append(trade.pnl_net)
        self._venue_pnl[trade.signal.buy_venue] -= trade.leg_buy.fee_paid
        self._venue_pnl[trade.signal.sell_venue] -= trade.leg_sell.fee_paid

        equity = self.initial_capital + self._realized_pnl
        self._equity_curve.append((time.time(), equity))
        self._peak_equity = max(self._peak_equity, equity)
        dd = (self._peak_equity - equity) / self._peak_equity if self._peak_equity > 0 else 0
        self._max_drawdown = max(self._max_drawdown, dd)

    @property
    def equity(self) -> float:
        return self.initial_capital + self._realized_pnl

    @property
    def open_positions(self) -> list[PositionSummary]:
        return [
            PositionSummary(
                pair_id=t.signal.pair.pair_id,
                question=t.signal.pair.question,
                buy_venue=t.signal.buy_venue,
                sell_venue=t.signal.sell_venue,
                size_usd=t.leg_buy.size_usd,
                entry_spread_bps=t.signal.net_spread_bps,
                entry_time=t.leg_buy.timestamp,
            )
            for t in self._open_trades.values()
        ]

    def snapshot(self) -> PortfolioSnapshot:
        n = len(self._trade_pnls)
        wins = sum(1 for p in self._trade_pnls if p > 0)
        avg_pnl = sum(self._trade_pnls) / n if n > 0 else 0
        import numpy as np
        if n >= 2:
            returns = np.array(self._trade_pnls)
            std = returns.std()
            sharpe = (returns.mean() / std * np.sqrt(252)) if std > 1e-10 else 0.0
        else:
            sharpe = 0.0

        return PortfolioSnapshot(
            timestamp=time.time(),
            total_equity=self.equity,
            realized_pnl=self._realized_pnl,
            unrealized_pnl=0.0,
            open_positions=len(self._open_trades),
            total_trades=n,
            win_rate=wins / n if n > 0 else 0,
            avg_pnl_per_trade=avg_pnl,
            sharpe=sharpe,
            max_drawdown_pct=self._max_drawdown * 100,
        )

    def venue_breakdown(self) -> dict[str, float]:
        return {v.name: pnl for v, pnl in self._venue_pnl.items()}

    def print_summary(self) -> None:
        s = self.snapshot()
        print(f"\n{'=' * 60}")
        print(f"  Portfolio Summary")
        print(f"{'=' * 60}")
        print(f"  Equity:          ${s.total_equity:>12,.2f}")
        print(f"  Realized P&L:    ${s.realized_pnl:>+12,.2f}")
        print(f"  Total trades:    {s.total_trades:>12d}")
        print(f"  Open positions:  {s.open_positions:>12d}")
        print(f"  Win rate:        {s.win_rate:>11.1%}")
        print(f"  Avg PnL/trade:   ${s.avg_pnl_per_trade:>+12,.2f}")
        print(f"  Sharpe:          {s.sharpe:>+12.2f}")
        print(f"  Max drawdown:    {s.max_drawdown_pct:>11.2f}%")
        print(f"{'=' * 60}")

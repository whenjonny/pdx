"""Portfolio management for event-driven backtesting.

Tracks open positions, mark-to-market equity, and closed trade history
in real time as the event engine dispatches fills, settlements, and
price ticks.

Listens to:
  - ``OrderFill``   -- opens or closes positions.
  - ``Settlement``  -- closes all positions in a resolved market.
  - ``MarketTick``  -- updates mark-to-market prices.

Provides:
  - Real-time equity (cash + MTM positions).
  - Position-level and strategy-level PnL.
  - Closed trade history with entry/exit details.
  - Equity curve snapshots for downstream analytics.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pdx_backtest.event_engine import (
    EventEngine,
    OrderFill,
    Settlement,
    MarketTick,
)


# ---------------------------------------------------------------------------
# Data records
# ---------------------------------------------------------------------------


@dataclass
class Position:
    """A single open position."""

    position_id: str
    market_id: str
    side: str  # "yes" or "no"
    size: float  # number of tokens (not notional)
    entry_price: float
    entry_time: float
    notional: float  # size x entry_price
    strategy_name: str
    order_id: str  # originating order

    def unrealized_pnl(self, current_price: float) -> float:
        """Mark-to-market PnL."""
        if self.side == "yes":
            return self.size * (current_price - self.entry_price)
        else:
            return self.size * (self.entry_price - current_price)

    def settlement_pnl(self, outcome: str) -> float:
        """PnL at settlement."""
        if self.side == "yes":
            settlement_value = 1.0 if outcome == "yes" else 0.0
        else:
            settlement_value = 1.0 if outcome == "no" else 0.0
        return self.size * (settlement_value - self.entry_price)


@dataclass
class ClosedTrade:
    """Record of a completed trade (open + close)."""

    position_id: str
    market_id: str
    side: str
    strategy_name: str
    entry_price: float
    exit_price: float
    size: float
    notional: float
    pnl: float
    entry_time: float
    exit_time: float
    exit_reason: str  # "signal", "settlement", "risk_liquidation", "stop_loss"


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


class Portfolio:
    """Real-time portfolio tracking with mark-to-market.

    Listens to:
    - OrderFill: opens/updates positions
    - Settlement: closes positions at settlement price
    - MarketTick: updates mark-to-market

    Provides:
    - Real-time equity (cash + MTM positions)
    - Position-level PnL
    - Closed trade history
    - Equity curve snapshots
    """

    def __init__(
        self,
        engine: EventEngine,
        initial_capital: float = 100_000.0,
    ):
        self._engine = engine
        self._initial_capital = initial_capital
        self._cash = initial_capital

        # Positions: position_id -> Position
        self._positions: dict[str, Position] = {}
        self._position_counter: int = 0

        # Closed trades
        self._closed_trades: list[ClosedTrade] = []

        # Latest prices for MTM
        self._latest_prices: dict[str, float] = {}  # market_id -> yes_price

        # Equity curve: (timestamp, equity)
        self._equity_curve: list[tuple[float, float]] = [(0.0, initial_capital)]

        # Register handlers
        engine.register(OrderFill, self._on_fill)
        engine.register(Settlement, self._on_settlement)
        engine.register(MarketTick, self._on_tick)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_position_id(self) -> str:
        self._position_counter += 1
        return f"POS-{self._position_counter:06d}"

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_fill(self, fill: OrderFill) -> None:
        """Handle an order fill -- open or add to position.

        The side in OrderFill is "buy_yes", "buy_no", "sell_yes", "sell_no".
        - buy_yes/buy_no: opens a long yes/no position
        - sell_yes/sell_no: closes existing yes/no position
        """
        is_buy = fill.side.startswith("buy")
        token_side = fill.side.split("_")[1]  # "yes" or "no"

        if is_buy:
            # Open new position
            size = fill.fill_size / fill.fill_price  # tokens = notional / price
            position = Position(
                position_id=self._generate_position_id(),
                market_id=fill.market_id,
                side=token_side,
                size=size,
                entry_price=fill.fill_price,
                entry_time=fill.timestamp,
                notional=fill.fill_size,
                strategy_name=fill.strategy_name,
                order_id=fill.order_id,
            )
            self._positions[position.position_id] = position
            self._cash -= fill.fill_size
        else:
            # Close existing position(s) for this market/side
            to_close = [
                p
                for p in self._positions.values()
                if p.market_id == fill.market_id
                and p.side == token_side
                and p.strategy_name == fill.strategy_name
            ]
            remaining_size = (
                fill.fill_size / fill.fill_price if fill.fill_price > 0 else 0
            )

            for pos in to_close:
                if remaining_size <= 0:
                    break
                close_size = min(pos.size, remaining_size)
                close_notional = close_size * fill.fill_price

                pnl = (
                    pos.unrealized_pnl(fill.fill_price) * (close_size / pos.size)
                    if pos.size > 0
                    else 0.0
                )

                trade = ClosedTrade(
                    position_id=pos.position_id,
                    market_id=pos.market_id,
                    side=pos.side,
                    strategy_name=pos.strategy_name,
                    entry_price=pos.entry_price,
                    exit_price=fill.fill_price,
                    size=close_size,
                    notional=(
                        pos.notional * (close_size / pos.size) if pos.size > 0 else 0.0
                    ),
                    pnl=pnl,
                    entry_time=pos.entry_time,
                    exit_time=fill.timestamp,
                    exit_reason="signal",
                )
                self._closed_trades.append(trade)
                self._cash += close_notional

                remaining_size -= close_size
                pos.size -= close_size
                if pos.size <= 0.001:
                    del self._positions[pos.position_id]

        # Record equity snapshot
        self._equity_curve.append((fill.timestamp, self.equity))

    def _on_settlement(self, settlement: Settlement) -> None:
        """Handle market settlement -- close all positions in this market."""
        to_settle = [
            p
            for p in list(self._positions.values())
            if p.market_id == settlement.market_id
        ]

        for pos in to_settle:
            pnl = pos.settlement_pnl(settlement.outcome)
            settlement_value = 1.0 if (
                (pos.side == "yes" and settlement.outcome == "yes")
                or (pos.side == "no" and settlement.outcome == "no")
            ) else 0.0

            trade = ClosedTrade(
                position_id=pos.position_id,
                market_id=pos.market_id,
                side=pos.side,
                strategy_name=pos.strategy_name,
                entry_price=pos.entry_price,
                exit_price=settlement_value,
                size=pos.size,
                notional=pos.notional,
                pnl=pnl,
                entry_time=pos.entry_time,
                exit_time=settlement.timestamp,
                exit_reason="settlement",
            )
            self._closed_trades.append(trade)
            self._cash += pos.size * settlement_value
            del self._positions[pos.position_id]

        if to_settle:
            self._equity_curve.append((settlement.timestamp, self.equity))

    def _on_tick(self, tick: MarketTick) -> None:
        """Update latest prices for MTM."""
        self._latest_prices[tick.market_id] = tick.yes_price

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def positions(self) -> dict[str, Position]:
        return self._positions

    @property
    def equity(self) -> float:
        """Total equity = cash + mark-to-market value of open positions."""
        mtm = 0.0
        for pos in self._positions.values():
            price = self._latest_prices.get(pos.market_id, pos.entry_price)
            if pos.side == "yes":
                mtm += pos.size * price
            else:
                mtm += pos.size * (1.0 - price)
        return self._cash + mtm

    @property
    def initial_capital(self) -> float:
        return self._initial_capital

    @property
    def total_pnl(self) -> float:
        return self.equity - self._initial_capital

    @property
    def closed_trades(self) -> list[ClosedTrade]:
        return self._closed_trades

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def positions_for_strategy(self, strategy_name: str) -> list[Position]:
        return [
            p for p in self._positions.values() if p.strategy_name == strategy_name
        ]

    def positions_for_market(self, market_id: str) -> list[Position]:
        return [p for p in self._positions.values() if p.market_id == market_id]

    def closed_trades_for_strategy(self, strategy_name: str) -> list[ClosedTrade]:
        return [t for t in self._closed_trades if t.strategy_name == strategy_name]

    def strategy_pnl(self, strategy_name: str) -> float:
        """Realized PnL for a strategy."""
        return sum(
            t.pnl for t in self._closed_trades if t.strategy_name == strategy_name
        )

    def strategy_unrealized_pnl(self, strategy_name: str) -> float:
        """Unrealized PnL for a strategy's open positions."""
        total = 0.0
        for pos in self._positions.values():
            if pos.strategy_name == strategy_name:
                price = self._latest_prices.get(pos.market_id, pos.entry_price)
                total += pos.unrealized_pnl(price)
        return total

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def get_equity_curve(self) -> tuple[np.ndarray, np.ndarray]:
        """Return (timestamps, equity_values) arrays."""
        if not self._equity_curve:
            return np.array([0.0]), np.array([self._initial_capital])
        ts = np.array([t for t, _ in self._equity_curve])
        eq = np.array([e for _, e in self._equity_curve])
        return ts, eq

    def get_returns(self) -> np.ndarray:
        """Per-trade returns (PnL / notional) for closed trades."""
        if not self._closed_trades:
            return np.array([], dtype=float)
        return np.array(
            [
                t.pnl / t.notional if t.notional > 0 else 0.0
                for t in self._closed_trades
            ],
            dtype=float,
        )

    def get_pnl_per_trade(self) -> np.ndarray:
        """Dollar PnL for each closed trade."""
        if not self._closed_trades:
            return np.array([], dtype=float)
        return np.array([t.pnl for t in self._closed_trades], dtype=float)

    def summary(self) -> dict:
        """Portfolio summary."""
        closed_pnl = sum(t.pnl for t in self._closed_trades)
        winning = [t for t in self._closed_trades if t.pnl > 0]
        losing = [t for t in self._closed_trades if t.pnl <= 0]

        return {
            "initial_capital": self._initial_capital,
            "cash": self._cash,
            "equity": self.equity,
            "total_pnl": self.total_pnl,
            "realized_pnl": closed_pnl,
            "unrealized_pnl": self.equity
            - self._cash
            - sum(p.notional for p in self._positions.values()),
            "n_open_positions": len(self._positions),
            "n_closed_trades": len(self._closed_trades),
            "win_rate": (
                len(winning) / len(self._closed_trades)
                if self._closed_trades
                else 0.0
            ),
            "gross_profit": sum(t.pnl for t in winning),
            "gross_loss": sum(t.pnl for t in losing),
            "avg_trade_pnl": (
                closed_pnl / len(self._closed_trades)
                if self._closed_trades
                else 0.0
            ),
            "strategies": list(
                set(t.strategy_name for t in self._closed_trades)
            ),
        }

    # ------------------------------------------------------------------
    # Risk management interface
    # ------------------------------------------------------------------

    def force_close_position(
        self,
        position_id: str,
        price: float,
        timestamp: float,
        reason: str = "risk_liquidation",
    ) -> ClosedTrade | None:
        """Force close a position (used by risk manager for liquidations).

        Returns the ClosedTrade or None if position not found.
        """
        pos = self._positions.get(position_id)
        if pos is None:
            return None

        pnl = pos.unrealized_pnl(price)
        trade = ClosedTrade(
            position_id=pos.position_id,
            market_id=pos.market_id,
            side=pos.side,
            strategy_name=pos.strategy_name,
            entry_price=pos.entry_price,
            exit_price=price,
            size=pos.size,
            notional=pos.notional,
            pnl=pnl,
            entry_time=pos.entry_time,
            exit_time=timestamp,
            exit_reason=reason,
        )
        self._closed_trades.append(trade)

        if pos.side == "yes":
            self._cash += pos.size * price
        else:
            self._cash += pos.size * (1.0 - price)

        del self._positions[position_id]
        self._equity_curve.append((timestamp, self.equity))
        return trade


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "Position",
    "ClosedTrade",
    "Portfolio",
]

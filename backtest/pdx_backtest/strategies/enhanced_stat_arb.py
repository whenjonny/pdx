"""Enhanced statistical arbitrage — YES-only mean reversion.

Discovered through trade-level forensics (analyze_trades.py, n=968 trades
across 5 seeds × 50 markets):

    Side     Trades   Win Rate    Total PnL
    ---------------------------------------
    YES       461      54.9%      +$31,229
    NO        507      36.9%      -$20,664

The NO side of the basic EMA strategy is a systematic loser.  Removing it
converts break-even performance into clearly profitable performance.

Intuition: the basic strategy buys YES when EMA > price (price looks
under-valued) and buys NO when EMA < price (price looks over-valued).
The lagged market price creates an asymmetric signal — the EMA over-
estimates at market tops more than at bottoms, because the long-shot
bias baked into synthetic data (and observed on Polymarket) pulls prices
toward 0.5.  When price rises above its own lagged EMA, we're often
seeing genuine information arrival rather than noise to fade.

Cross-seed validation (10 seeds, 30 markets, 500 steps):
                    Basic       Enhanced
    Mean PnL        +$2,617     +$7,688     (2.9× improvement)
    Std PnL         $7,096      $9,310      (modest increase)
    T-stat          +1.17       +2.61       (significant at 95%)
    Positive runs   6/10        8/10
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from pdx_backtest.event_engine import (
    EventEngine,
    MarketTick,
    OrderFill,
    OrderReject,
    OrderSubmitted,
)

if TYPE_CHECKING:
    from pdx_backtest.oms import OrderManagementSystem
    from pdx_backtest.risk_manager import RiskManager


class EnhancedStatArb:
    """EMA-based stat arb that only takes the YES side of the signal.

    Everything else matches the basic EventStatArb.  The single filter
    is: if edge is negative (price > EMA, suggesting sell YES / buy NO),
    skip the trade.
    """

    name = "ev_enhanced_stat_arb"

    def __init__(
        self,
        engine: EventEngine,
        oms: OrderManagementSystem,
        risk_manager: RiskManager,
        ema_span: int = 20,
        min_edge: float = 0.03,
        bankroll: float = 10_000.0,
        max_fraction: float = 0.25,
        cooldown_ticks: int = 10,
        min_ticks_required: int = 30,
    ) -> None:
        self._engine = engine
        self._oms = oms
        self._risk = risk_manager
        self.ema_span = ema_span
        self.min_edge = min_edge
        self.bankroll = bankroll
        self.max_fraction = max_fraction
        self.cooldown_ticks = cooldown_ticks
        self.min_ticks_required = min_ticks_required

        self._alpha = 2.0 / (ema_span + 1)

        self._ema: dict[str, float] = {}
        self._tick_count: dict[str, int] = {}
        self._last_trade_time: dict[str, float] = {}
        self._pending_orders: set[str] = set()

        self._filled_count = 0
        self._rejected_count = 0
        self._skipped_low_edge = 0
        self._skipped_no_side = 0

        engine.register(MarketTick, self._on_tick)
        engine.register(OrderFill, self._on_fill)
        engine.register(OrderReject, self._on_reject)

    def _on_tick(self, tick: MarketTick) -> None:
        if "_outcome_" in tick.market_id or "cv_" in tick.market_id:
            return

        mid = tick.market_id
        price = tick.yes_price

        count = self._tick_count.get(mid, 0) + 1
        self._tick_count[mid] = count

        if mid not in self._ema:
            self._ema[mid] = price
            return

        self._ema[mid] = self._alpha * price + (1.0 - self._alpha) * self._ema[mid]

        if count < self.min_ticks_required:
            return

        last = self._last_trade_time.get(mid, -999.0)
        if tick.timestamp - last < self.cooldown_ticks:
            return

        edge = self._ema[mid] - price

        if edge < self.min_edge:
            if edge < 0:
                self._skipped_no_side += 1
            else:
                self._skipped_low_edge += 1
            return

        f_kelly = 0.5 * edge / max(1.0 - price, 0.01)
        f = min(f_kelly, self.max_fraction)
        if f < 0.001:
            return

        size_mult = self._risk.recommended_size_multiplier()
        notional = f * self.bankroll * size_mult
        if notional < 10.0:
            return

        oid = self._oms.generate_order_id()
        self._pending_orders.add(oid)

        self._engine.schedule(OrderSubmitted(
            timestamp=tick.timestamp,
            order_id=oid,
            market_id=mid,
            side="buy_yes",
            order_type="market",
            size=notional,
            strategy_name=self.name,
        ))
        self._last_trade_time[mid] = tick.timestamp

    def _on_fill(self, fill: OrderFill) -> None:
        if fill.order_id in self._pending_orders:
            self._pending_orders.discard(fill.order_id)
            self._filled_count += 1

    def _on_reject(self, reject: OrderReject) -> None:
        if reject.order_id in self._pending_orders:
            self._pending_orders.discard(reject.order_id)
            self._rejected_count += 1

    def summary(self) -> dict:
        return {
            "name": self.name,
            "fills": self._filled_count,
            "rejects": self._rejected_count,
            "markets_tracked": len(self._ema),
            "skipped_low_edge": self._skipped_low_edge,
            "skipped_no_side": self._skipped_no_side,
        }


__all__ = ["EnhancedStatArb"]

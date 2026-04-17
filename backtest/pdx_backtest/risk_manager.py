"""Pre-trade and post-trade risk management for event-driven backtesting.

Acts as a gatekeeper between strategies and OMS.  Every ``OrderSubmitted``
event is checked against configurable limits *before* OMS processes it.
If any check fails, the risk manager emits an ``OrderReject`` and records
the order ID in a rejected set that OMS queries via ``is_rejected()``.

Post-trade monitoring updates drawdown, exposure, and strategy-level PnL
tracking on every ``OrderFill`` and ``MarketTick``.

Registration order matters: the risk manager MUST be instantiated (and
therefore registered with the engine) *before* the OMS so that its
``OrderSubmitted`` handler runs first.

Design decisions:
  - The engine does not support blocking event propagation.  Instead,
    the risk manager records rejected order IDs and OMS checks the set.
  - All state is deterministic given the same event stream.
  - ``RiskLimits`` is a plain dataclass -- serialisable and easy to
    sweep in parameter searches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pdx_backtest.event_engine import (
    EventEngine,
    Event,
    OrderSubmitted,
    OrderFill,
    OrderReject,
    MarketTick,
    Settlement,
    RiskAlert,
)

if TYPE_CHECKING:
    from pdx_backtest.portfolio import Portfolio


# ---------------------------------------------------------------------------
# Configurable risk limits
# ---------------------------------------------------------------------------


@dataclass
class RiskLimits:
    """Configurable risk limits -- mirrors what a real trading desk would set."""

    # Portfolio-level limits
    max_drawdown_pct: float = 0.15  # 15% max drawdown -> halt all trading
    max_portfolio_notional: float = 500_000.0  # max total exposure
    max_daily_loss: float = 10_000.0  # daily loss limit
    max_open_positions: int = 50  # total position count

    # Per-strategy limits
    max_strategy_notional: float = 100_000.0  # max exposure per strategy
    max_strategy_loss: float = 5_000.0  # per-strategy loss limit
    max_strategy_positions: int = 20  # positions per strategy

    # Per-trade limits
    max_single_trade_notional: float = 10_000.0  # max single order size
    min_single_trade_notional: float = 10.0  # min order size
    max_position_pct_of_liquidity: float = 0.10  # don't take >10% of book

    # Concentration limits
    max_single_market_exposure_pct: float = 0.20  # max 20% of portfolio in one market
    max_correlated_exposure_pct: float = 0.40  # max 40% in correlated markets

    # Rate limits
    max_orders_per_minute: int = 60  # order rate limit
    cooldown_after_n_rejects: int = 3  # pause after N consecutive rejects
    cooldown_duration: float = 60.0  # cooldown seconds

    # Dynamic sizing
    kelly_fraction: float = 0.5  # half-Kelly default
    reduce_size_after_drawdown_pct: float = 0.05  # start reducing after 5% DD
    min_size_multiplier: float = 0.25  # at max DD, trade at 25% size


# ---------------------------------------------------------------------------
# Risk manager
# ---------------------------------------------------------------------------


class RiskManager:
    """Pre-trade and post-trade risk management.

    Pre-trade checks (on OrderSubmitted):
      1. Global halt
      2. Strategy halt
      3. Cooldown after consecutive rejects
      4. Rate limiting
      5. Single trade size limits
      6. Portfolio drawdown limit
      7. Daily loss limit
      8. Portfolio notional limit
      9. Position count limit
     10. Per-strategy notional / loss / position limits
     11. Single-market concentration limit
     12. Liquidity check (order size vs book depth)

    Post-trade monitoring (on OrderFill, MarketTick):
      1. Portfolio drawdown tracking
      2. Mark-to-market equity updates
      3. Strategy performance tracking
      4. Market exposure updates

    Risk actions:
      - Block order (emit OrderReject)
      - Reduce position size (via ``recommended_size_multiplier()``)
      - Halt strategy
      - Halt all trading
    """

    def __init__(
        self,
        engine: EventEngine,
        portfolio: Portfolio,
        limits: RiskLimits | None = None,
    ) -> None:
        self._engine = engine
        self._portfolio = portfolio
        self._limits = limits or RiskLimits()

        # --- state tracking ---------------------------------------------------
        self._halted: bool = False
        self._halted_strategies: set[str] = set()
        self._peak_equity: float = portfolio.equity
        self._daily_pnl: float = 0.0
        self._day_start_equity: float = portfolio.equity
        self._current_day: int = 0  # day counter (timestamp / 86400)

        # Rate limiting state
        self._order_timestamps: list[float] = []  # sliding window
        self._consecutive_rejects: dict[str, int] = {}  # strategy -> count
        self._cooldown_until: dict[str, float] = {}  # strategy -> timestamp

        # Strategy-level tracking
        self._strategy_pnl: dict[str, float] = {}
        self._strategy_notional: dict[str, float] = {}
        self._strategy_positions: dict[str, int] = {}

        # Market exposure tracking
        self._market_exposure: dict[str, float] = {}  # market_id -> notional
        self._latest_liquidity: dict[str, float] = {}  # market_id -> book depth

        # Rejected order IDs -- OMS checks this via ``is_rejected()``
        self._rejected_order_ids: set[str] = set()

        # Risk event log
        self._alerts: list[RiskAlert] = []

        # --- register handlers (BEFORE OMS is created) -------------------------
        engine.register(OrderSubmitted, self._pre_trade_check)
        engine.register(OrderFill, self._post_fill)
        engine.register(MarketTick, self._on_tick)
        engine.register(OrderReject, self._on_reject)

    # ------------------------------------------------------------------
    # Alert helper
    # ------------------------------------------------------------------

    def _emit_alert(
        self,
        alert_type: str,
        message: str,
        severity: str,
        timestamp: float,
    ) -> None:
        """Create a ``RiskAlert``, log it locally, and schedule it on the engine."""
        alert = RiskAlert(
            timestamp=timestamp,
            alert_type=alert_type,
            message=message,
            severity=severity,
        )
        self._alerts.append(alert)
        self._engine.schedule(alert)

    # ------------------------------------------------------------------
    # Pre-trade gate
    # ------------------------------------------------------------------

    def _pre_trade_check(self, order: OrderSubmitted) -> None:
        """Gate-keep every order before it reaches OMS.

        If any check fails we emit an ``OrderReject`` and record the
        ``order_id`` in ``_rejected_order_ids``.  OMS must call
        ``is_rejected(order_id)`` and skip processing when ``True``.
        """
        strategy = order.strategy_name

        # Check 0: Global halt
        if self._halted:
            self._reject_order(order, "global_halt", "Trading halted due to risk breach")
            return

        # Check 1: Strategy halted
        if strategy in self._halted_strategies:
            self._reject_order(
                order, "strategy_halted", f"Strategy {strategy} halted"
            )
            return

        # Check 2: Cooldown check
        if strategy in self._cooldown_until:
            if order.timestamp < self._cooldown_until[strategy]:
                self._reject_order(
                    order, "cooldown", f"Strategy {strategy} in cooldown"
                )
                return
            else:
                # Cooldown expired -- reset
                del self._cooldown_until[strategy]
                self._consecutive_rejects[strategy] = 0

        # Check 3: Rate limit (sliding 60-second window)
        cutoff = order.timestamp - 60.0
        self._order_timestamps = [t for t in self._order_timestamps if t > cutoff]
        if len(self._order_timestamps) >= self._limits.max_orders_per_minute:
            self._reject_order(order, "rate_limit", "Order rate limit exceeded")
            return

        # Check 4: Single trade size limits
        if order.size > self._limits.max_single_trade_notional:
            self._reject_order(
                order,
                "trade_too_large",
                f"Order ${order.size:.0f} exceeds max "
                f"${self._limits.max_single_trade_notional:.0f}",
            )
            return
        if order.size < self._limits.min_single_trade_notional:
            self._reject_order(
                order,
                "trade_too_small",
                f"Order ${order.size:.0f} below min "
                f"${self._limits.min_single_trade_notional:.0f}",
            )
            return

        # Check 5: Portfolio drawdown
        current_dd = self._current_drawdown()
        if current_dd > self._limits.max_drawdown_pct:
            self._halted = True
            self._reject_order(
                order,
                "max_drawdown",
                f"Drawdown {current_dd:.1%} exceeds limit "
                f"{self._limits.max_drawdown_pct:.1%}",
            )
            self._emit_alert(
                "drawdown_breach",
                f"Max drawdown breached: {current_dd:.1%}",
                "critical",
                order.timestamp,
            )
            return

        # Check 6: Daily loss limit
        if self._daily_pnl < -self._limits.max_daily_loss:
            self._reject_order(
                order,
                "daily_loss_limit",
                f"Daily loss ${-self._daily_pnl:.0f} exceeds limit "
                f"${self._limits.max_daily_loss:.0f}",
            )
            return

        # Check 7: Portfolio notional limit
        total_notional = sum(self._market_exposure.values())
        if total_notional + order.size > self._limits.max_portfolio_notional:
            self._reject_order(
                order,
                "portfolio_notional_limit",
                f"Would exceed max portfolio notional "
                f"${self._limits.max_portfolio_notional:.0f}",
            )
            return

        # Check 8: Position count
        total_positions = len(self._portfolio.positions)
        if total_positions >= self._limits.max_open_positions:
            self._reject_order(
                order,
                "position_limit",
                f"Open positions {total_positions} at limit "
                f"{self._limits.max_open_positions}",
            )
            return

        # Check 9: Per-strategy notional limit
        strat_notional = self._strategy_notional.get(strategy, 0.0)
        if strat_notional + order.size > self._limits.max_strategy_notional:
            self._reject_order(
                order,
                "strategy_notional_limit",
                f"Strategy {strategy} would exceed notional limit",
            )
            return

        # Check 10: Per-strategy loss limit
        strat_loss = self._strategy_pnl.get(strategy, 0.0)
        if strat_loss < -self._limits.max_strategy_loss:
            self._halted_strategies.add(strategy)
            self._reject_order(
                order,
                "strategy_loss_limit",
                f"Strategy {strategy} loss ${-strat_loss:.0f} exceeds limit",
            )
            self._emit_alert(
                "strategy_halted",
                f"Strategy {strategy} halted: loss limit breached",
                "critical",
                order.timestamp,
            )
            return

        # Check 11: Per-strategy position limit
        strat_positions = self._strategy_positions.get(strategy, 0)
        if strat_positions >= self._limits.max_strategy_positions:
            self._reject_order(
                order,
                "strategy_position_limit",
                f"Strategy {strategy} at position limit "
                f"{self._limits.max_strategy_positions}",
            )
            return

        # Check 12: Single-market concentration limit
        market_exposure = self._market_exposure.get(order.market_id, 0.0)
        equity = max(self._portfolio.equity, 1.0)  # avoid div-by-zero
        if (
            (market_exposure + order.size) / equity
            > self._limits.max_single_market_exposure_pct
        ):
            self._reject_order(
                order,
                "concentration_limit",
                f"Market {order.market_id} exposure would exceed "
                f"{self._limits.max_single_market_exposure_pct:.0%}",
            )
            return

        # Check 13: Liquidity check
        liq = self._latest_liquidity.get(order.market_id, 50_000.0)
        if order.size / liq > self._limits.max_position_pct_of_liquidity:
            self._reject_order(
                order,
                "liquidity_limit",
                f"Order is {order.size / liq:.1%} of book, "
                f"limit {self._limits.max_position_pct_of_liquidity:.0%}",
            )
            return

        # All checks passed -- record timestamp for rate limiting
        self._order_timestamps.append(order.timestamp)

    # ------------------------------------------------------------------
    # Rejection helper
    # ------------------------------------------------------------------

    def _reject_order(self, order: OrderSubmitted, reason: str, message: str) -> None:
        """Emit an ``OrderReject`` and record the order ID as rejected."""
        reject = OrderReject(
            timestamp=order.timestamp,
            priority=1,  # high priority -- processed before OMS fill events
            order_id=order.order_id,
            reason=reason,
            strategy_name=order.strategy_name,
        )
        self._engine.schedule(reject)
        self._rejected_order_ids.add(order.order_id)

    def is_rejected(self, order_id: str) -> bool:
        """Check if an order was rejected by the risk manager.

        OMS should call this before processing an ``OrderSubmitted``
        event to avoid executing a risk-blocked order.
        """
        return order_id in self._rejected_order_ids

    # ------------------------------------------------------------------
    # Post-fill handler
    # ------------------------------------------------------------------

    def _post_fill(self, fill: OrderFill) -> None:
        """Update exposure tracking after a fill."""
        strategy = fill.strategy_name

        # Update strategy notional
        self._strategy_notional[strategy] = (
            self._strategy_notional.get(strategy, 0.0) + fill.fill_size
        )

        # Update strategy position count
        self._strategy_positions[strategy] = (
            self._strategy_positions.get(strategy, 0) + 1
        )

        # Update market exposure
        self._market_exposure[fill.market_id] = (
            self._market_exposure.get(fill.market_id, 0.0) + fill.fill_size
        )

        # Reset consecutive reject counter on successful fill
        self._consecutive_rejects[strategy] = 0

    # ------------------------------------------------------------------
    # Tick handler
    # ------------------------------------------------------------------

    def _on_tick(self, tick: MarketTick) -> None:
        """Update tracking on price ticks."""
        # Update liquidity estimate
        self._latest_liquidity[tick.market_id] = tick.liquidity

        # Update peak equity for drawdown
        equity = self._portfolio.equity
        if equity > self._peak_equity:
            self._peak_equity = equity

        # Day boundary detection (every 86400 seconds)
        day = int(tick.timestamp / 86400)
        if day > self._current_day:
            self._current_day = day
            self._daily_pnl = 0.0
            self._day_start_equity = equity

    # ------------------------------------------------------------------
    # Reject handler
    # ------------------------------------------------------------------

    def _on_reject(self, reject: OrderReject) -> None:
        """Track consecutive rejects for cooldown logic.

        Only counts OMS-level rejects (execution_failure, no_market_data,
        fill_too_small, limit_price_exceeded).  Risk manager's own rejects
        (cooldown, rate_limit, etc.) are excluded to prevent cascading
        cooldowns.
        """
        strategy = reject.strategy_name
        if not strategy:
            return
        if reject.order_id in self._rejected_order_ids:
            return
        self._consecutive_rejects[strategy] = (
            self._consecutive_rejects.get(strategy, 0) + 1
        )
        if self._consecutive_rejects[strategy] >= self._limits.cooldown_after_n_rejects:
            self._cooldown_until[strategy] = (
                reject.timestamp + self._limits.cooldown_duration
            )
            self._emit_alert(
                "cooldown_triggered",
                f"Strategy {strategy} entering cooldown after "
                f"{self._consecutive_rejects[strategy]} consecutive rejects",
                "warning",
                reject.timestamp,
            )

    # ------------------------------------------------------------------
    # Drawdown calculation
    # ------------------------------------------------------------------

    def _current_drawdown(self) -> float:
        """Current drawdown from peak equity."""
        equity = self._portfolio.equity
        if self._peak_equity <= 0:
            return 0.0
        return max(0.0, (self._peak_equity - equity) / self._peak_equity)

    # ------------------------------------------------------------------
    # Dynamic position sizing
    # ------------------------------------------------------------------

    def recommended_size_multiplier(self) -> float:
        """Dynamic position sizing based on current drawdown.

        Returns a float in ``[min_size_multiplier, 1.0]``.  Strategies
        should multiply their intended order size by this value.

        Linear reduction from 1.0 at ``reduce_size_after_drawdown_pct``
        to ``min_size_multiplier`` at ``max_drawdown_pct``.
        """
        dd = self._current_drawdown()
        limits = self._limits

        if dd <= limits.reduce_size_after_drawdown_pct:
            return 1.0

        if dd >= limits.max_drawdown_pct:
            return limits.min_size_multiplier

        # Linear interpolation between the two thresholds
        frac = (dd - limits.reduce_size_after_drawdown_pct) / (
            limits.max_drawdown_pct - limits.reduce_size_after_drawdown_pct
        )
        return 1.0 - frac * (1.0 - limits.min_size_multiplier)

    # ------------------------------------------------------------------
    # External update hooks (called by Portfolio)
    # ------------------------------------------------------------------

    def update_strategy_pnl(self, strategy: str, pnl_delta: float) -> None:
        """Called by portfolio when a position PnL changes (fill or settlement).

        Updates both per-strategy PnL and daily PnL tracking.
        """
        self._strategy_pnl[strategy] = (
            self._strategy_pnl.get(strategy, 0.0) + pnl_delta
        )
        self._daily_pnl += pnl_delta

    def close_position_exposure(
        self, strategy: str, market_id: str, notional: float
    ) -> None:
        """Called when a position is closed -- reduce exposure tracking.

        Clamps at zero to avoid negative exposure from rounding.
        """
        self._strategy_notional[strategy] = max(
            0.0, self._strategy_notional.get(strategy, 0.0) - notional
        )
        self._strategy_positions[strategy] = max(
            0, self._strategy_positions.get(strategy, 0) - 1
        )
        self._market_exposure[market_id] = max(
            0.0, self._market_exposure.get(market_id, 0.0) - notional
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def halted(self) -> bool:
        """Whether all trading has been halted."""
        return self._halted

    @property
    def alerts(self) -> list[RiskAlert]:
        """Full list of risk alerts emitted during the simulation."""
        return self._alerts

    @property
    def limits(self) -> RiskLimits:
        """Current risk limits (read-only reference)."""
        return self._limits

    # ------------------------------------------------------------------
    # Summary / diagnostics
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        """Risk manager summary for post-run analysis."""
        return {
            "halted": self._halted,
            "halted_strategies": list(self._halted_strategies),
            "peak_equity": self._peak_equity,
            "current_drawdown": self._current_drawdown(),
            "daily_pnl": self._daily_pnl,
            "strategy_pnl": dict(self._strategy_pnl),
            "strategy_notional": dict(self._strategy_notional),
            "strategy_positions": dict(self._strategy_positions),
            "market_exposure": dict(self._market_exposure),
            "n_alerts": len(self._alerts),
            "alerts_by_type": _count_by(self._alerts, lambda a: a.alert_type),
            "rejected_orders": len(self._rejected_order_ids),
            "size_multiplier": self.recommended_size_multiplier(),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _count_by(items: list, key_fn) -> dict[str, int]:  # type: ignore[type-arg]
    """Count items by a key function."""
    counts: dict[str, int] = {}
    for item in items:
        k = key_fn(item)
        counts[k] = counts.get(k, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "RiskLimits",
    "RiskManager",
]

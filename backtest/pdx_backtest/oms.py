"""Order Management System for event-driven backtesting.

Simulates realistic order lifecycle with execution friction applied at
submission time (not post-hoc).  The OMS listens for ``OrderSubmitted``
events and, after a configurable latency delay, emits either an
``OrderFill`` or ``OrderReject`` event.

Friction components applied at execution:
  1. **Execution failure** -- Bernoulli draw per trade.
  2. **Partial fills** -- Beta-distributed fill fraction.
  3. **Slippage** -- half bid-ask spread.
  4. **Market impact** -- sqrt(order_size / liquidity) model.
  5. **Latency adverse move** -- Gaussian price drift during latency.

The system is fully deterministic given the same ``numpy`` RNG seed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pdx_backtest.event_engine import (
    EventEngine,
    OrderSubmitted,
    OrderFill,
    OrderReject,
    MarketTick,
    OrderBookUpdate,
)
from pdx_backtest.friction import FrictionParams


# ---------------------------------------------------------------------------
# Internal order tracking
# ---------------------------------------------------------------------------


@dataclass
class OrderState:
    """Internal order tracking."""

    order_id: str
    market_id: str
    side: str  # "buy_yes", "buy_no", "sell_yes", "sell_no"
    order_type: str  # "market", "limit"
    requested_size: float  # notional USDC
    limit_price: float | None
    strategy_name: str
    submit_time: float
    status: str  # "pending", "filled", "partial", "rejected", "cancelled"
    filled_size: float = 0.0
    avg_fill_price: float = 0.0
    fill_count: int = 0


# ---------------------------------------------------------------------------
# Order Management System
# ---------------------------------------------------------------------------


class OrderManagementSystem:
    """Simulates realistic order execution with friction.

    Listens for:
    - OrderSubmitted -- applies latency, checks fills against orderbook
    - MarketTick -- updates latest prices (for market orders)
    - OrderBookUpdate -- updates orderbook (for limit orders and realistic fills)

    Emits:
    - OrderFill when order executes (with realistic price including slippage + impact)
    - OrderReject when order fails (execution failure, insufficient liquidity, etc.)
    """

    def __init__(
        self,
        engine: EventEngine,
        friction: dict[str, FrictionParams] | None = None,
        default_friction: FrictionParams | None = None,
        rng: np.random.Generator | None = None,
        execution_latency_ms: float = 200.0,
        max_retry: int = 0,
        risk_manager: object | None = None,
    ) -> None:
        self._engine = engine
        # friction per market_id prefix -- e.g. "poly_" -> polymarket params
        self._friction = friction or {}
        self._default_friction = default_friction or FrictionParams.polymarket()
        self._rng = rng or np.random.default_rng(42)
        self._latency = execution_latency_ms / 1000.0  # convert to seconds
        self._max_retry = max_retry
        self._risk_manager = risk_manager

        # State
        self._orders: dict[str, OrderState] = {}
        self._latest_prices: dict[str, tuple[float, float]] = {}  # market_id -> (yes, no)
        self._latest_books: dict[str, OrderBookUpdate] = {}
        self._order_counter: int = 0
        self._fill_log: list[OrderFill] = []
        self._reject_log: list[OrderReject] = []

        # Register handlers
        engine.register(OrderSubmitted, self._on_order_submitted)
        engine.register(MarketTick, self._on_market_tick)
        engine.register(OrderBookUpdate, self._on_orderbook_update)

    # ------------------------------------------------------------------
    # Friction lookup
    # ------------------------------------------------------------------

    def _get_friction(self, market_id: str) -> FrictionParams:
        """Get friction params for a market based on venue prefix."""
        for prefix, params in self._friction.items():
            if market_id.startswith(prefix):
                return params
        return self._default_friction

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_market_tick(self, tick: MarketTick) -> None:
        """Update latest prices."""
        self._latest_prices[tick.market_id] = (tick.yes_price, tick.no_price)

    def _on_orderbook_update(self, update: OrderBookUpdate) -> None:
        """Update latest orderbook."""
        self._latest_books[update.market_id] = update

    def _on_order_submitted(self, event: OrderSubmitted) -> None:
        """Process a new order submission.

        1. Check if risk manager already rejected this order
        2. Record the order
        3. Schedule a fill attempt after latency delay
        """
        if self._risk_manager is not None and hasattr(self._risk_manager, "is_rejected"):
            if self._risk_manager.is_rejected(event.order_id):
                return

        order = OrderState(
            order_id=event.order_id,
            market_id=event.market_id,
            side=event.side,
            order_type=event.order_type,
            requested_size=event.size,
            limit_price=event.limit_price,
            strategy_name=event.strategy_name,
            submit_time=event.timestamp,
            status="pending",
        )
        self._orders[event.order_id] = order

        # Schedule fill attempt after latency
        self._attempt_fill(order, event.timestamp + self._latency)

    # ------------------------------------------------------------------
    # Fill logic
    # ------------------------------------------------------------------

    def _attempt_fill(self, order: OrderState, fill_time: float) -> None:
        """Attempt to fill an order at the given time.

        This is where all friction is applied:
        1. Check execution success (Bernoulli)
        2. Compute fill fraction (Beta distribution)
        3. Compute execution price (slippage + impact + latency move)
        4. Emit OrderFill or OrderReject
        """
        friction = self._get_friction(order.market_id)

        # Step 1: Execution failure check
        if self._rng.random() < friction.execution_failure_rate:
            reject = OrderReject(
                timestamp=fill_time,
                order_id=order.order_id,
                reason="execution_failure",
                strategy_name=order.strategy_name,
            )
            order.status = "rejected"
            self._reject_log.append(reject)
            self._engine.schedule(reject)
            return

        # Step 2: Get current market price
        prices = self._latest_prices.get(order.market_id)
        if prices is None:
            reject = OrderReject(
                timestamp=fill_time,
                order_id=order.order_id,
                reason="no_market_data",
                strategy_name=order.strategy_name,
            )
            order.status = "rejected"
            self._reject_log.append(reject)
            self._engine.schedule(reject)
            return

        yes_price, no_price = prices

        # Determine reference price based on side
        if order.side in ("buy_yes", "sell_no"):
            ref_price = yes_price
        else:
            ref_price = no_price

        # Step 3: Compute fill fraction
        fill_frac = float(np.clip(
            self._rng.beta(friction.partial_fill_alpha, friction.partial_fill_beta),
            0.0,
            1.0,
        ))
        fill_notional = order.requested_size * fill_frac

        if fill_notional < 1.0:  # minimum fill size $1
            reject = OrderReject(
                timestamp=fill_time,
                order_id=order.order_id,
                reason="fill_too_small",
                strategy_name=order.strategy_name,
            )
            order.status = "rejected"
            self._reject_log.append(reject)
            self._engine.schedule(reject)
            return

        # Step 4: Compute execution price with all friction components
        is_buy = order.side.startswith("buy")

        # 4a. Slippage (bid-ask spread)
        half_spread = friction.half_spread_bps / 10_000.0
        if is_buy:
            exec_price = ref_price * (1.0 + half_spread)
        else:
            exec_price = ref_price * (1.0 - half_spread)

        # 4b. Market impact (sqrt model)
        book = self._latest_books.get(order.market_id)
        liquidity = friction.default_liquidity
        if book is not None:
            # Use actual book depth
            if is_buy and book.asks:
                liquidity = sum(size for _, size in book.asks)
            elif not is_buy and book.bids:
                liquidity = sum(size for _, size in book.bids)
            liquidity = max(liquidity, 1000.0)

        impact = friction.impact_coeff * np.sqrt(fill_notional / liquidity)
        if is_buy:
            exec_price *= 1.0 + impact
        else:
            exec_price *= 1.0 - impact

        # 4c. Latency adverse move
        adverse_move = abs(self._rng.normal(0, friction.latency_adverse_move_std))
        if is_buy:
            exec_price += adverse_move
        else:
            exec_price -= adverse_move

        # Clamp price to valid range
        exec_price = float(np.clip(exec_price, 0.001, 0.999))

        # Step 5: Limit order price check
        if order.order_type == "limit" and order.limit_price is not None:
            if is_buy and exec_price > order.limit_price:
                reject = OrderReject(
                    timestamp=fill_time,
                    order_id=order.order_id,
                    reason=(
                        f"limit_price_exceeded: "
                        f"exec={exec_price:.4f} > limit={order.limit_price:.4f}"
                    ),
                    strategy_name=order.strategy_name,
                )
                order.status = "rejected"
                self._reject_log.append(reject)
                self._engine.schedule(reject)
                return
            if not is_buy and exec_price < order.limit_price:
                reject = OrderReject(
                    timestamp=fill_time,
                    order_id=order.order_id,
                    reason=(
                        f"limit_price_exceeded: "
                        f"exec={exec_price:.4f} < limit={order.limit_price:.4f}"
                    ),
                    strategy_name=order.strategy_name,
                )
                order.status = "rejected"
                self._reject_log.append(reject)
                self._engine.schedule(reject)
                return

        # Step 6: Emit fill
        remaining = order.requested_size - fill_notional
        order.filled_size += fill_notional
        order.avg_fill_price = (
            (order.avg_fill_price * order.fill_count + exec_price)
            / (order.fill_count + 1)
        )
        order.fill_count += 1
        order.status = "filled" if remaining < 1.0 else "partial"

        fill = OrderFill(
            timestamp=fill_time,
            order_id=order.order_id,
            market_id=order.market_id,
            side=order.side,
            fill_size=fill_notional,
            fill_price=exec_price,
            remaining=remaining,
            strategy_name=order.strategy_name,
        )
        self._fill_log.append(fill)
        self._engine.schedule(fill)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def generate_order_id(self) -> str:
        """Generate unique order ID."""
        self._order_counter += 1
        return f"ORD-{self._order_counter:06d}"

    @property
    def orders(self) -> dict[str, OrderState]:
        return self._orders

    @property
    def fill_log(self) -> list[OrderFill]:
        return self._fill_log

    @property
    def reject_log(self) -> list[OrderReject]:
        return self._reject_log

    def fill_rate(self) -> float:
        """Overall fill rate."""
        total = len(self._fill_log) + len(self._reject_log)
        return len(self._fill_log) / total if total > 0 else 0.0

    def summary(self) -> dict:
        """OMS execution summary."""
        fills = len(self._fill_log)
        rejects = len(self._reject_log)
        total_filled_notional = sum(f.fill_size for f in self._fill_log)
        reject_reasons: dict[str, int] = {}
        for r in self._reject_log:
            reason = r.reason.split(":")[0]
            reject_reasons[reason] = reject_reasons.get(reason, 0) + 1

        return {
            "total_orders": len(self._orders),
            "fills": fills,
            "rejects": rejects,
            "fill_rate": fills / (fills + rejects) if (fills + rejects) > 0 else 0.0,
            "total_filled_notional": total_filled_notional,
            "reject_reasons": reject_reasons,
        }

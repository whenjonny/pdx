"""Event-driven backtest engine.

Replaces the time-series iteration approach with a priority-queue event
loop.  Strategies register callbacks for event types they care about;
the engine dispatches events in (timestamp, priority) order.

Key design decisions:
  - Events are dataclasses sortable by (timestamp, priority) for heapq.
  - ``true_prob`` is never exposed to strategies -- only ``MarketSimulator``
    holds it internally for settlement resolution.
  - ``MarketTick`` carries the observable CLOB state (yes_price, no_price,
    volume, liquidity) but nothing that leaks the latent fair value.
  - The engine logs every dispatched event for post-hoc analysis.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from pdx_backtest.data import CrossPlatformPath, MarketPath, MultiOutcomeSnapshot

# ---------------------------------------------------------------------------
# Event hierarchy
# ---------------------------------------------------------------------------


@dataclass(order=True)
class Event:
    """Base event -- sortable by (timestamp, priority) for the heapq."""

    timestamp: float
    priority: int = field(default=5, compare=True)


@dataclass(order=True)
class MarketTick(Event):
    """Price update for a single market.

    YES and NO prices come from the CLOB -- they need *not* sum to 1.0.
    ``true_prob`` is deliberately absent; strategies cannot cheat.
    """

    market_id: str = field(default="", compare=False)
    yes_price: float = field(default=0.0, compare=False)
    no_price: float = field(default=0.0, compare=False)
    volume_24h: float = field(default=0.0, compare=False)
    liquidity: float = field(default=50_000.0, compare=False)


@dataclass(order=True)
class OrderBookUpdate(Event):
    """Simulated L2 orderbook snapshot."""

    market_id: str = field(default="", compare=False)
    bids: list[tuple[float, float]] = field(default_factory=list, compare=False)
    asks: list[tuple[float, float]] = field(default_factory=list, compare=False)


@dataclass(order=True)
class OrderSubmitted(Event):
    """Strategy submitted an order to OMS."""

    order_id: str = field(default="", compare=False)
    market_id: str = field(default="", compare=False)
    side: str = field(default="buy_yes", compare=False)  # "buy_yes", "buy_no", "sell_yes", "sell_no"
    order_type: str = field(default="market", compare=False)  # "market", "limit"
    size: float = field(default=0.0, compare=False)  # notional USDC
    limit_price: float | None = field(default=None, compare=False)
    strategy_name: str = field(default="", compare=False)


@dataclass(order=True)
class OrderFill(Event):
    """Order was (partially) filled."""

    order_id: str = field(default="", compare=False)
    market_id: str = field(default="", compare=False)
    side: str = field(default="", compare=False)
    fill_size: float = field(default=0.0, compare=False)  # actual USDC filled
    fill_price: float = field(default=0.0, compare=False)  # execution price (after slippage + impact)
    remaining: float = field(default=0.0, compare=False)  # unfilled portion
    strategy_name: str = field(default="", compare=False)


@dataclass(order=True)
class OrderReject(Event):
    """Order rejected by OMS or risk manager."""

    order_id: str = field(default="", compare=False)
    reason: str = field(default="", compare=False)  # "risk_limit", "insufficient_capital", etc.
    strategy_name: str = field(default="", compare=False)


@dataclass(order=True)
class Settlement(Event):
    """Market resolved -- positions settled."""

    market_id: str = field(default="", compare=False)
    outcome: str = field(default="", compare=False)  # "yes" or "no"
    settlement_price: float = field(default=0.0, compare=False)  # 1.0 for winner, 0.0 for loser


@dataclass(order=True)
class RiskAlert(Event):
    """Risk manager emitted an alert."""

    alert_type: str = field(default="", compare=False)  # "drawdown_breach", "position_limit", etc.
    message: str = field(default="", compare=False)
    severity: str = field(default="warning", compare=False)  # "warning", "critical", "halt"


# ---------------------------------------------------------------------------
# Event engine
# ---------------------------------------------------------------------------


class EventEngine:
    """Priority-queue event loop for discrete-event simulation.

    Events are dispatched in ``(timestamp, priority)`` order.  Handlers
    registered for a given event type are called synchronously in
    registration order.  Handlers may schedule new events (which will be
    processed in a future iteration).
    """

    def __init__(self, seed: int = 42) -> None:
        self._queue: list[tuple[float, int, int, Event]] = []
        self._handlers: dict[type, list[Callable[[Event], None]]] = {}
        self._clock: float = 0.0
        self._rng: np.random.Generator = np.random.default_rng(seed)
        self._event_log: list[Event] = []
        self._running: bool = False

    # -- scheduling --------------------------------------------------------

    def schedule(self, event: Event) -> None:
        """Add *event* to the priority queue."""
        heapq.heappush(
            self._queue,
            (event.timestamp, event.priority, id(event), event),
        )

    # -- handler registration ----------------------------------------------

    def register(self, event_type: type, handler: Callable[[Event], None]) -> None:
        """Register *handler* to be called whenever *event_type* is dispatched."""
        self._handlers.setdefault(event_type, []).append(handler)

    # -- main loop ---------------------------------------------------------

    def run(self, until: float | None = None) -> list[Event]:
        """Process events until the queue is empty or *until* is exceeded.

        Returns the full event log (audit trail) accumulated during the
        run, including events from prior ``run()`` calls on the same
        engine instance.
        """
        self._running = True
        while self._queue:
            ts, prio, _, event = heapq.heappop(self._queue)
            if until is not None and ts > until:
                # Put it back -- the caller may resume later.
                heapq.heappush(self._queue, (ts, prio, id(event), event))
                break
            self._clock = ts
            self._event_log.append(event)
            for handler in self._handlers.get(type(event), []):
                handler(event)
        self._running = False
        return self._event_log

    # -- accessors ---------------------------------------------------------

    @property
    def clock(self) -> float:
        """Current simulation time (timestamp of the last dispatched event)."""
        return self._clock

    @property
    def rng(self) -> np.random.Generator:
        """Shared random generator -- deterministic across runs."""
        return self._rng

    @property
    def event_log(self) -> list[Event]:
        """Full audit trail of dispatched events."""
        return list(self._event_log)

    @property
    def pending(self) -> int:
        """Number of events still in the queue."""
        return len(self._queue)


# ---------------------------------------------------------------------------
# Market simulator -- converts synthetic paths to event streams
# ---------------------------------------------------------------------------


class MarketSimulator:
    """Generates ``MarketTick`` events from synthetic data without
    exposing ``true_prob``.

    Takes existing ``MarketPath`` / ``CrossPlatformPath`` data and
    converts them to event streams.  ``true_prob`` is held internally
    for settlement but never exposed to strategies.
    """

    def __init__(self, engine: EventEngine, rng: np.random.Generator) -> None:
        self._engine = engine
        self._rng = rng
        self._settlement_outcomes: dict[str, str] = {}  # market_id -> "yes"/"no"
        self._true_probs: dict[str, np.ndarray] = {}  # hidden from strategies

    # -- binary markets ----------------------------------------------------

    def load_binary_market(
        self,
        market_id: str,
        path: MarketPath,
        tick_interval: float = 1.0,
    ) -> None:
        """Schedule ``MarketTick`` events for a binary market.

        YES price = ``path.market_price`` (observable).
        NO price  = ``1.0 - market_price + noise`` (independent CLOB).
        ``true_prob`` is stored internally for settlement, never exposed.
        """
        for step in range(len(path)):
            yes_price = float(path.market_price[step])
            no_noise = self._rng.normal(0, 0.008)
            no_price = float(
                np.clip(1.0 - path.market_price[step] + no_noise, 0.001, 0.999)
            )

            tick = MarketTick(
                timestamp=step * tick_interval,
                market_id=market_id,
                yes_price=yes_price,
                no_price=no_price,
                volume_24h=float(self._rng.uniform(10_000, 500_000)),
                liquidity=float(self._rng.uniform(20_000, 200_000)),
            )
            self._engine.schedule(tick)

        self._true_probs[market_id] = path.true_prob
        self._settlement_outcomes[market_id] = "yes" if path.outcome == 1 else "no"

    # -- cross-venue -------------------------------------------------------

    def load_cross_venue(
        self,
        poly_id: str,
        predict_id: str,
        path: CrossPlatformPath,
        tick_interval: float = 1.0,
    ) -> None:
        """Schedule tick events for two venues from ``CrossPlatformPath``.

        ``price_a`` -> Polymarket ticks (always on time).
        ``price_b`` -> predict.fun ticks (with lag jitter -- predict.fun
        may update a few ticks late, simulating slower venue).
        """
        for step in range(len(path.timestamps)):
            # Polymarket tick -- always on time
            poly_tick = MarketTick(
                timestamp=step * tick_interval,
                market_id=poly_id,
                yes_price=float(path.price_a[step]),
                no_price=float(
                    np.clip(
                        1.0 - path.price_a[step] + self._rng.normal(0, 0.005),
                        0.001,
                        0.999,
                    )
                ),
                liquidity=float(self._rng.uniform(30_000, 150_000)),
            )
            self._engine.schedule(poly_tick)

            # predict.fun tick -- add latency jitter (0-3 tick intervals)
            lag = float(self._rng.uniform(0.0, 3.0)) * tick_interval
            predict_tick = MarketTick(
                timestamp=step * tick_interval + lag,
                market_id=predict_id,
                yes_price=float(path.price_b[step]),
                no_price=float(
                    np.clip(
                        1.0 - path.price_b[step] + self._rng.normal(0, 0.008),
                        0.001,
                        0.999,
                    )
                ),
                liquidity=float(self._rng.uniform(10_000, 80_000)),
            )
            self._engine.schedule(predict_tick)

        outcome = "yes" if path.outcome == 1 else "no"
        self._settlement_outcomes[poly_id] = outcome
        self._settlement_outcomes[predict_id] = outcome
        self._true_probs[poly_id] = path.true_prob
        self._true_probs[predict_id] = path.true_prob

    # -- NegRisk multi-outcome ---------------------------------------------

    def load_negrisk(
        self,
        event_id: str,
        snapshots: list[MultiOutcomeSnapshot],
        tick_interval: float = 1.0,
    ) -> None:
        """Schedule ticks for a multi-outcome NegRisk market.

        Each outcome gets its own market_id: ``f"{event_id}_outcome_{i}"``.
        """
        for step, snap in enumerate(snapshots):
            for i in range(snap.n):
                market_id = f"{event_id}_outcome_{i}"
                tick = MarketTick(
                    timestamp=step * tick_interval,
                    market_id=market_id,
                    yes_price=float(snap.yes_prices[i]),
                    no_price=float(snap.no_prices[i]),
                    liquidity=float(self._rng.uniform(15_000, 100_000)),
                )
                self._engine.schedule(tick)
                self._settlement_outcomes[market_id] = (
                    "yes" if snap.winner_index == i else "no"
                )

    # -- settlement --------------------------------------------------------

    def schedule_settlements(self, settlement_time: float) -> None:
        """Schedule ``Settlement`` events for all loaded markets."""
        for market_id, outcome in self._settlement_outcomes.items():
            event = Settlement(
                timestamp=settlement_time,
                market_id=market_id,
                outcome=outcome,
                settlement_price=1.0 if outcome == "yes" else 0.0,
            )
            self._engine.schedule(event)


# ---------------------------------------------------------------------------
# Orderbook simulator -- generates L2 depth from ticks
# ---------------------------------------------------------------------------


class OrderBookSimulator:
    """Generates realistic orderbook depth from ``MarketTick`` events.

    When a ``MarketTick`` arrives, we generate a synthetic L2 book around
    the midpoint using a configurable depth profile.
    """

    def __init__(
        self,
        engine: EventEngine,
        rng: np.random.Generator,
        n_levels: int = 5,
        base_size: float = 5_000.0,
    ) -> None:
        self._engine = engine
        self._rng = rng
        self.n_levels = n_levels
        self.base_size = base_size
        engine.register(MarketTick, self._on_tick)

    def _on_tick(self, tick: Event) -> None:
        """Generate synthetic orderbook from tick."""
        assert isinstance(tick, MarketTick)
        spread = max(0.005, float(self._rng.exponential(0.01)))
        mid = tick.yes_price

        bids: list[tuple[float, float]] = []
        asks: list[tuple[float, float]] = []
        for level in range(self.n_levels):
            bid_price = mid - spread / 2 - level * 0.005
            ask_price = mid + spread / 2 + level * 0.005
            # Size increases with distance from mid (typical book shape)
            size = float(
                self.base_size
                * (1.0 + level * 0.5)
                * self._rng.uniform(0.5, 1.5)
            )
            bids.append((max(bid_price, 0.001), size))
            asks.append((min(ask_price, 0.999), size))

        ob_event = OrderBookUpdate(
            timestamp=tick.timestamp + 0.001,  # slightly after tick
            market_id=tick.market_id,
            bids=sorted(bids, key=lambda x: -x[0]),
            asks=sorted(asks, key=lambda x: x[0]),
        )
        self._engine.schedule(ob_event)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # Events
    "Event",
    "MarketTick",
    "OrderBookUpdate",
    "OrderSubmitted",
    "OrderFill",
    "OrderReject",
    "Settlement",
    "RiskAlert",
    # Engine
    "EventEngine",
    # Simulators
    "MarketSimulator",
    "OrderBookSimulator",
]

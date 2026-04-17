"""Event-driven strategy implementations.

These strategies react to MarketTick events via callbacks, submit orders
through the OMS, and NEVER see true_prob.  They maintain internal state
across ticks and use the risk manager for dynamic position sizing.
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


# ---------------------------------------------------------------------------
# 1. NegRisk Rebalancer
# ---------------------------------------------------------------------------


class EventNegRiskRebalancer:
    """Buy all YES tokens when sum(YES) < 1.0 - threshold."""

    name = "ev_negrisk_rebalancer"

    def __init__(
        self,
        engine: EventEngine,
        oms: OrderManagementSystem,
        risk_manager: RiskManager,
        threshold: float = 0.01,
        capital_per_trade: float = 1_000.0,
        cooldown_ticks: int = 5,
    ) -> None:
        self._engine = engine
        self._oms = oms
        self._risk = risk_manager
        self.threshold = threshold
        self.capital_per_trade = capital_per_trade
        self._cooldown = cooldown_ticks

        self._yes_prices: dict[str, float] = {}
        self._events: dict[str, list[str]] = {}
        self._last_trade_time: dict[str, float] = {}
        self._pending_orders: set[str] = set()
        self._filled_count = 0
        self._rejected_count = 0

        engine.register(MarketTick, self._on_tick)
        engine.register(OrderFill, self._on_fill)
        engine.register(OrderReject, self._on_reject)

    def _on_tick(self, tick: MarketTick) -> None:
        mid = tick.market_id
        self._yes_prices[mid] = tick.yes_price

        parts = mid.rsplit("_outcome_", 1)
        if len(parts) != 2:
            return
        event_id = parts[0]

        if event_id not in self._events:
            self._events[event_id] = []
        if mid not in self._events[event_id]:
            self._events[event_id].append(mid)

        outcomes = self._events[event_id]
        if not all(m in self._yes_prices for m in outcomes):
            return

        last = self._last_trade_time.get(event_id, -999.0)
        if tick.timestamp - last < self._cooldown:
            return

        sum_yes = sum(self._yes_prices[m] for m in outcomes)
        n = len(outcomes)

        if sum_yes < 1.0 - self.threshold:
            size_mult = self._risk.recommended_size_multiplier()
            per_outcome = self.capital_per_trade * size_mult / n
            for m in outcomes:
                oid = self._oms.generate_order_id()
                self._pending_orders.add(oid)
                self._engine.schedule(OrderSubmitted(
                    timestamp=tick.timestamp,
                    order_id=oid,
                    market_id=m,
                    side="buy_yes",
                    order_type="market",
                    size=per_outcome,
                    strategy_name=self.name,
                ))
            self._last_trade_time[event_id] = tick.timestamp

        elif sum_yes > 1.0 + self.threshold:
            sum_no = sum(1.0 - self._yes_prices[m] for m in outcomes)
            if sum_no < (n - 1) - self.threshold:
                size_mult = self._risk.recommended_size_multiplier()
                per_outcome = self.capital_per_trade * size_mult / n
                for m in outcomes:
                    oid = self._oms.generate_order_id()
                    self._pending_orders.add(oid)
                    self._engine.schedule(OrderSubmitted(
                        timestamp=tick.timestamp,
                        order_id=oid,
                        market_id=m,
                        side="buy_no",
                        order_type="market",
                        size=per_outcome,
                        strategy_name=self.name,
                    ))
                self._last_trade_time[event_id] = tick.timestamp

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
            "events_tracked": len(self._events),
        }


# ---------------------------------------------------------------------------
# 2. Single Binary Rebalancer
# ---------------------------------------------------------------------------


class EventSingleBinaryRebalancer:
    """Buy YES+NO pair when sum < $1.00 - threshold."""

    name = "ev_single_binary_rebalancer"

    def __init__(
        self,
        engine: EventEngine,
        oms: OrderManagementSystem,
        risk_manager: RiskManager,
        threshold: float = 0.005,
        capital_per_trade: float = 1_000.0,
        cooldown_ticks: int = 3,
    ) -> None:
        self._engine = engine
        self._oms = oms
        self._risk = risk_manager
        self.threshold = threshold
        self.capital_per_trade = capital_per_trade
        self._cooldown = cooldown_ticks

        self._last_trade_time: dict[str, float] = {}
        self._pending_orders: set[str] = set()
        self._filled_count = 0
        self._rejected_count = 0

        engine.register(MarketTick, self._on_tick)
        engine.register(OrderFill, self._on_fill)
        engine.register(OrderReject, self._on_reject)

    def _on_tick(self, tick: MarketTick) -> None:
        if "_outcome_" in tick.market_id:
            return
        if "cv_" in tick.market_id:
            return

        last = self._last_trade_time.get(tick.market_id, -999.0)
        if tick.timestamp - last < self._cooldown:
            return

        pair_cost = tick.yes_price + tick.no_price
        size_mult = self._risk.recommended_size_multiplier()
        notional = self.capital_per_trade * size_mult

        if pair_cost < 1.0 - self.threshold:
            half = notional / 2.0
            for side in ("buy_yes", "buy_no"):
                oid = self._oms.generate_order_id()
                self._pending_orders.add(oid)
                self._engine.schedule(OrderSubmitted(
                    timestamp=tick.timestamp,
                    order_id=oid,
                    market_id=tick.market_id,
                    side=side,
                    order_type="market",
                    size=half,
                    strategy_name=self.name,
                ))
            self._last_trade_time[tick.market_id] = tick.timestamp

        elif pair_cost > 1.0 + self.threshold:
            half = notional / 2.0
            for side in ("sell_yes", "sell_no"):
                oid = self._oms.generate_order_id()
                self._pending_orders.add(oid)
                self._engine.schedule(OrderSubmitted(
                    timestamp=tick.timestamp,
                    order_id=oid,
                    market_id=tick.market_id,
                    side=side,
                    order_type="market",
                    size=half,
                    strategy_name=self.name,
                ))
            self._last_trade_time[tick.market_id] = tick.timestamp

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
        }


# ---------------------------------------------------------------------------
# 3. Statistical Arbitrage (EMA-based, no true_prob)
# ---------------------------------------------------------------------------


class EventStatArb:
    """Mean-reversion via EMA probability estimate vs market price."""

    name = "ev_statistical_arb"

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
    ) -> None:
        self._engine = engine
        self._oms = oms
        self._risk = risk_manager
        self.ema_span = ema_span
        self.min_edge = min_edge
        self.bankroll = bankroll
        self.max_fraction = max_fraction
        self._cooldown = cooldown_ticks

        self._ema: dict[str, float] = {}
        self._tick_count: dict[str, int] = {}
        self._last_trade_time: dict[str, float] = {}
        self._pending_orders: set[str] = set()
        self._filled_count = 0
        self._rejected_count = 0

        alpha = 2.0 / (ema_span + 1)
        self._alpha = alpha

        engine.register(MarketTick, self._on_tick)
        engine.register(OrderFill, self._on_fill)
        engine.register(OrderReject, self._on_reject)

    def _on_tick(self, tick: MarketTick) -> None:
        if "_outcome_" in tick.market_id:
            return
        if "cv_" in tick.market_id:
            return

        mid = tick.market_id
        price = tick.yes_price

        count = self._tick_count.get(mid, 0) + 1
        self._tick_count[mid] = count

        if mid not in self._ema:
            self._ema[mid] = price
            return

        self._ema[mid] = self._alpha * price + (1.0 - self._alpha) * self._ema[mid]

        if count < self.ema_span:
            return

        last = self._last_trade_time.get(mid, -999.0)
        if tick.timestamp - last < self._cooldown:
            return

        model_p = self._ema[mid]
        edge = model_p - price

        if abs(edge) < self.min_edge:
            return

        if edge > 0:
            f_kelly = 0.5 * (model_p - price) / max(1.0 - price, 0.01)
        else:
            f_kelly = 0.5 * (price - model_p) / max(model_p, 0.01)

        f = min(abs(f_kelly), self.max_fraction)
        if f < 0.001:
            return

        size_mult = self._risk.recommended_size_multiplier()
        notional = f * self.bankroll * size_mult

        side = "buy_yes" if edge > 0 else "buy_no"
        oid = self._oms.generate_order_id()
        self._pending_orders.add(oid)
        self._engine.schedule(OrderSubmitted(
            timestamp=tick.timestamp,
            order_id=oid,
            market_id=mid,
            side=side,
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
        }


# ---------------------------------------------------------------------------
# 4. Cross-Venue Arbitrage (Polymarket vs predict.fun)
# ---------------------------------------------------------------------------


class EventCrossVenueArb:
    """Exploits price discrepancies between two venues for the same market."""

    name = "ev_cross_venue_arb"

    def __init__(
        self,
        engine: EventEngine,
        oms: OrderManagementSystem,
        risk_manager: RiskManager,
        poly_fee_bps: float = 0.0,
        predict_fee_bps: float = 150.0,
        min_spread: float = 0.02,
        capital_per_trade: float = 1_000.0,
        settlement_risk_bps: float = 50.0,
        max_concurrent: int = 10,
        cooldown_ticks: float = 5.0,
    ) -> None:
        self._engine = engine
        self._oms = oms
        self._risk = risk_manager
        self.poly_fee = poly_fee_bps / 10_000.0
        self.predict_fee = predict_fee_bps / 10_000.0
        self.min_spread = min_spread
        self.capital_per_trade = capital_per_trade
        self.settlement_cost = settlement_risk_bps / 10_000.0
        self.max_concurrent = max_concurrent
        self._cooldown = cooldown_ticks

        self._latest_prices: dict[str, float] = {}
        self._venue_pairs: dict[str, str] = {}
        self._reverse_pairs: dict[str, str] = {}
        self._open_count = 0
        self._last_trade_time: dict[str, float] = {}
        self._pending_orders: set[str] = set()
        self._filled_count = 0
        self._rejected_count = 0

        engine.register(MarketTick, self._on_tick)
        engine.register(OrderFill, self._on_fill)
        engine.register(OrderReject, self._on_reject)

    def register_pair(self, poly_id: str, predict_id: str) -> None:
        self._venue_pairs[poly_id] = predict_id
        self._reverse_pairs[predict_id] = poly_id

    def _on_tick(self, tick: MarketTick) -> None:
        self._latest_prices[tick.market_id] = tick.yes_price

        poly_id = tick.market_id
        predict_id = self._venue_pairs.get(poly_id)
        if predict_id is None:
            predict_id = tick.market_id
            poly_id = self._reverse_pairs.get(predict_id)
            if poly_id is None:
                return

        if poly_id not in self._latest_prices or predict_id not in self._latest_prices:
            return

        if self._open_count >= self.max_concurrent:
            return

        pair_key = f"{poly_id}|{predict_id}"
        last = self._last_trade_time.get(pair_key, -999.0)
        if tick.timestamp - last < self._cooldown:
            return

        pa = self._latest_prices[poly_id]
        pb = self._latest_prices[predict_id]

        spread_buy_poly = pb - pa
        cost_buy_poly = pa * self.poly_fee + pb * self.predict_fee + self.settlement_cost
        net_buy_poly = spread_buy_poly - cost_buy_poly

        spread_buy_predict = pa - pb
        cost_buy_predict = pb * self.predict_fee + pa * self.poly_fee + self.settlement_cost
        net_buy_predict = spread_buy_predict - cost_buy_predict

        if net_buy_poly >= net_buy_predict and net_buy_poly > self.min_spread:
            buy_market, sell_market = poly_id, predict_id
            effective = net_buy_poly
        elif net_buy_predict > self.min_spread:
            buy_market, sell_market = predict_id, poly_id
            effective = net_buy_predict
        else:
            return

        size_mult = self._risk.recommended_size_multiplier()
        notional = self.capital_per_trade * size_mult

        buy_oid = self._oms.generate_order_id()
        sell_oid = self._oms.generate_order_id()
        self._pending_orders.add(buy_oid)
        self._pending_orders.add(sell_oid)

        self._engine.schedule(OrderSubmitted(
            timestamp=tick.timestamp,
            order_id=buy_oid,
            market_id=buy_market,
            side="buy_yes",
            order_type="market",
            size=notional / 2.0,
            strategy_name=self.name,
        ))
        self._engine.schedule(OrderSubmitted(
            timestamp=tick.timestamp,
            order_id=sell_oid,
            market_id=sell_market,
            side="sell_yes",
            order_type="market",
            size=notional / 2.0,
            strategy_name=self.name,
        ))

        self._open_count += 1
        self._last_trade_time[pair_key] = tick.timestamp

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
            "pairs": len(self._venue_pairs),
            "open_arbs": self._open_count,
        }


# ---------------------------------------------------------------------------
# 5. Longshot Bias Exploiter
# ---------------------------------------------------------------------------


class EventLongshotBiasExploiter:
    """Sell overpriced longshots, buy underpriced favorites."""

    name = "ev_longshot_bias"

    def __init__(
        self,
        engine: EventEngine,
        oms: OrderManagementSystem,
        risk_manager: RiskManager,
        sell_zone: tuple[float, float] = (0.02, 0.10),
        buy_zone: tuple[float, float] = (0.90, 0.98),
        capital_per_trade: float = 500.0,
    ) -> None:
        self._engine = engine
        self._oms = oms
        self._risk = risk_manager
        self.sell_lo, self.sell_hi = sell_zone
        self.buy_lo, self.buy_hi = buy_zone
        self.capital_per_trade = capital_per_trade

        self._traded_markets: set[str] = set()
        self._pending_orders: set[str] = set()
        self._filled_count = 0
        self._rejected_count = 0

        engine.register(MarketTick, self._on_tick)
        engine.register(OrderFill, self._on_fill)
        engine.register(OrderReject, self._on_reject)

    def _on_tick(self, tick: MarketTick) -> None:
        if "_outcome_" in tick.market_id:
            return
        if "cv_" in tick.market_id:
            return

        mid = tick.market_id
        key_yes = f"{mid}_yes"
        key_no = f"{mid}_no"

        size_mult = self._risk.recommended_size_multiplier()
        notional = self.capital_per_trade * size_mult

        if self.sell_lo <= tick.yes_price <= self.sell_hi and key_yes not in self._traded_markets:
            oid = self._oms.generate_order_id()
            self._pending_orders.add(oid)
            self._engine.schedule(OrderSubmitted(
                timestamp=tick.timestamp,
                order_id=oid,
                market_id=mid,
                side="sell_yes",
                order_type="market",
                size=notional,
                strategy_name=self.name,
            ))
            self._traded_markets.add(key_yes)

        elif self.buy_lo <= tick.yes_price <= self.buy_hi and key_yes not in self._traded_markets:
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
            self._traded_markets.add(key_yes)

        no_price = tick.no_price
        if self.sell_lo <= no_price <= self.sell_hi and key_no not in self._traded_markets:
            oid = self._oms.generate_order_id()
            self._pending_orders.add(oid)
            self._engine.schedule(OrderSubmitted(
                timestamp=tick.timestamp,
                order_id=oid,
                market_id=mid,
                side="sell_no",
                order_type="market",
                size=notional,
                strategy_name=self.name,
            ))
            self._traded_markets.add(key_no)

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
            "markets_traded": len(self._traded_markets),
        }


# ---------------------------------------------------------------------------
# 6. Market Maker (simplified event-driven version)
# ---------------------------------------------------------------------------


class EventMarketMaker:
    """Simplified market maker — provides liquidity on binary markets.

    Tracks price momentum and takes the opposite side.  Unlike the
    full BayesianMarketMaker, this doesn't maintain an AMM pool —
    it just places passive limit orders around the midpoint.
    """

    name = "ev_market_maker"

    def __init__(
        self,
        engine: EventEngine,
        oms: OrderManagementSystem,
        risk_manager: RiskManager,
        spread_bps: float = 30.0,
        order_size: float = 200.0,
        max_inventory: float = 5_000.0,
        rebalance_interval: int = 10,
    ) -> None:
        self._engine = engine
        self._oms = oms
        self._risk = risk_manager
        self.half_spread = spread_bps / 10_000.0
        self.order_size = order_size
        self.max_inventory = max_inventory
        self._interval = rebalance_interval

        self._inventory: dict[str, float] = {}
        self._tick_count: dict[str, int] = {}
        self._pending_orders: set[str] = set()
        self._filled_count = 0
        self._rejected_count = 0

        engine.register(MarketTick, self._on_tick)
        engine.register(OrderFill, self._on_fill)
        engine.register(OrderReject, self._on_reject)

    def _on_tick(self, tick: MarketTick) -> None:
        if "_outcome_" in tick.market_id or "cv_" in tick.market_id:
            return

        mid = tick.market_id
        count = self._tick_count.get(mid, 0) + 1
        self._tick_count[mid] = count

        if count % self._interval != 0:
            return

        inv = self._inventory.get(mid, 0.0)
        size_mult = self._risk.recommended_size_multiplier()
        size = self.order_size * size_mult

        if abs(inv) < self.max_inventory:
            bid_price = tick.yes_price * (1.0 - self.half_spread)
            ask_price = tick.yes_price * (1.0 + self.half_spread)

            bid_oid = self._oms.generate_order_id()
            self._pending_orders.add(bid_oid)
            self._engine.schedule(OrderSubmitted(
                timestamp=tick.timestamp,
                order_id=bid_oid,
                market_id=mid,
                side="buy_yes",
                order_type="limit",
                size=size,
                limit_price=bid_price,
                strategy_name=self.name,
            ))

            ask_oid = self._oms.generate_order_id()
            self._pending_orders.add(ask_oid)
            self._engine.schedule(OrderSubmitted(
                timestamp=tick.timestamp,
                order_id=ask_oid,
                market_id=mid,
                side="sell_yes",
                order_type="limit",
                size=size,
                limit_price=ask_price,
                strategy_name=self.name,
            ))

    def _on_fill(self, fill: OrderFill) -> None:
        if fill.order_id in self._pending_orders:
            self._pending_orders.discard(fill.order_id)
            self._filled_count += 1
            delta = fill.fill_size if fill.side.startswith("buy") else -fill.fill_size
            self._inventory[fill.market_id] = self._inventory.get(fill.market_id, 0.0) + delta

    def _on_reject(self, reject: OrderReject) -> None:
        if reject.order_id in self._pending_orders:
            self._pending_orders.discard(reject.order_id)
            self._rejected_count += 1

    def summary(self) -> dict:
        return {
            "name": self.name,
            "fills": self._filled_count,
            "rejects": self._rejected_count,
            "net_inventory": sum(self._inventory.values()),
        }


__all__ = [
    "EventNegRiskRebalancer",
    "EventSingleBinaryRebalancer",
    "EventStatArb",
    "EventCrossVenueArb",
    "EventLongshotBiasExploiter",
    "EventMarketMaker",
]

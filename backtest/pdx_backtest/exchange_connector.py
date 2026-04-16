"""Live exchange connector for Polymarket paper trading.

Provides two modes:
  1. REST polling: fetch midpoints every N seconds (simple, reliable)
  2. WebSocket streaming: subscribe to real-time price updates (lower latency)

Paper trading: no actual orders are placed.  The connector tracks
virtual positions and P&L against live prices.

Usage:
    connector = ExchangeConnector()
    await connector.start()
    # connector streams prices and calls strategy callbacks
    await connector.run_for(hours=5)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np

try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

from pdx_backtest.polymarket_client import (
    CLOB_BASE,
    WS_URL,
    EventInfo,
    MarketInfo,
    fetch_markets,
    fetch_midpoints,
    fetch_multi_outcome_events,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Paper position tracker
# ---------------------------------------------------------------------------


@dataclass
class PaperPosition:
    token_id: str
    market_slug: str
    side: str  # "yes" or "no"
    size: float  # number of tokens
    entry_price: float
    entry_time: float
    notional: float  # USDC spent

    @property
    def cost_basis(self) -> float:
        return self.entry_price * self.size


@dataclass
class PaperTrade:
    timestamp: float
    market_slug: str
    token_id: str
    action: str
    side: str
    size: float
    price: float
    notional: float
    pnl: float
    strategy: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class PaperPortfolio:
    initial_capital: float = 100_000.0
    cash: float = 100_000.0
    positions: list[PaperPosition] = field(default_factory=list)
    trades: list[PaperTrade] = field(default_factory=list)
    equity_history: list[tuple[float, float]] = field(default_factory=list)

    @property
    def total_notional(self) -> float:
        return sum(p.notional for p in self.positions)

    def mark_to_market(self, prices: dict[str, float]) -> float:
        """Total portfolio value at current prices."""
        pos_value = 0.0
        for p in self.positions:
            current_price = prices.get(p.token_id, p.entry_price)
            pos_value += p.size * current_price
        return self.cash + pos_value

    def record_equity(self, prices: dict[str, float]) -> None:
        mtm = self.mark_to_market(prices)
        self.equity_history.append((time.time(), mtm))

    def open_position(
        self,
        token_id: str,
        market_slug: str,
        side: str,
        price: float,
        notional: float,
        strategy: str,
        meta: dict | None = None,
    ) -> Optional[PaperTrade]:
        """Buy tokens at current price (paper)."""
        if notional > self.cash:
            return None
        size = notional / price if price > 0 else 0
        if size <= 0:
            return None

        pos = PaperPosition(
            token_id=token_id,
            market_slug=market_slug,
            side=side,
            size=size,
            entry_price=price,
            entry_time=time.time(),
            notional=notional,
        )
        self.positions.append(pos)
        self.cash -= notional

        trade = PaperTrade(
            timestamp=time.time(),
            market_slug=market_slug,
            token_id=token_id,
            action="open",
            side=side,
            size=size,
            price=price,
            notional=notional,
            pnl=0.0,
            strategy=strategy,
            meta=meta or {},
        )
        self.trades.append(trade)
        return trade

    def close_position(
        self,
        position_idx: int,
        current_price: float,
        strategy: str,
        meta: dict | None = None,
    ) -> Optional[PaperTrade]:
        """Sell position at current price (paper)."""
        if position_idx >= len(self.positions):
            return None
        pos = self.positions.pop(position_idx)
        proceeds = pos.size * current_price
        pnl = proceeds - pos.notional
        self.cash += proceeds

        trade = PaperTrade(
            timestamp=time.time(),
            market_slug=pos.market_slug,
            token_id=pos.token_id,
            action="close",
            side=pos.side,
            size=pos.size,
            price=current_price,
            notional=pos.notional,
            pnl=pnl,
            strategy=strategy,
            meta=meta or {},
        )
        self.trades.append(trade)
        return trade


# ---------------------------------------------------------------------------
# Strategy interface for live trading
# ---------------------------------------------------------------------------


class LiveStrategy:
    """Base class for live trading strategies."""

    name: str = "base_live"

    def on_tick(
        self,
        portfolio: PaperPortfolio,
        prices: dict[str, float],
        markets: list[MarketInfo],
        events: list[EventInfo],
        step: int,
    ) -> None:
        """Called every tick with current prices. Override to implement."""
        pass


# ---------------------------------------------------------------------------
# Live NegRisk rebalancer
# ---------------------------------------------------------------------------


class LiveNegRiskRebalancer(LiveStrategy):
    name = "live_negrisk"

    def __init__(self, threshold: float = 0.02, capital_per_trade: float = 500.0,
                 taker_fee_bps: float = 0.0) -> None:
        self.threshold = threshold
        self.capital_per_trade = capital_per_trade
        self.fee = taker_fee_bps / 10_000.0

    def on_tick(self, portfolio, prices, markets, events, step):
        for event in events:
            if len(event.markets) < 3:
                continue
            yes_prices = []
            token_ids = []
            for m in event.markets:
                if m.token_ids:
                    tid = m.token_ids[0]
                    p = prices.get(tid, 0)
                    if p > 0:
                        yes_prices.append(p)
                        token_ids.append(tid)

            if len(yes_prices) < 3:
                continue

            sum_yes = sum(yes_prices)
            sum_cost = sum_yes * (1.0 + self.fee)

            if sum_cost < 1.0 - self.threshold:
                edge = 1.0 - sum_cost
                units = self.capital_per_trade / sum_cost
                expected_pnl = units * edge
                for tid, p in zip(token_ids, yes_prices):
                    notional = p * units
                    portfolio.open_position(
                        token_id=tid,
                        market_slug=event.slug,
                        side="yes",
                        price=p,
                        notional=notional,
                        strategy=self.name,
                        meta={"sum_yes": sum_yes, "edge": edge,
                              "event": event.title},
                    )


# ---------------------------------------------------------------------------
# Live single-binary rebalancer
# ---------------------------------------------------------------------------


class LiveSingleBinaryRebalancer(LiveStrategy):
    name = "live_single_binary"

    def __init__(self, threshold: float = 0.005, capital_per_trade: float = 500.0,
                 taker_fee_bps: float = 0.0) -> None:
        self.threshold = threshold
        self.capital_per_trade = capital_per_trade
        self.fee = taker_fee_bps / 10_000.0

    def on_tick(self, portfolio, prices, markets, events, step):
        for m in markets:
            if not m.is_binary or len(m.token_ids) < 2:
                continue
            yes_tid, no_tid = m.token_ids[0], m.token_ids[1]
            yes_p = prices.get(yes_tid, 0)
            no_p = prices.get(no_tid, 0)
            if yes_p <= 0 or no_p <= 0:
                continue

            total_cost = (yes_p + no_p) * (1.0 + self.fee)
            if total_cost < 1.0 - self.threshold:
                edge = 1.0 - total_cost
                portfolio.open_position(
                    token_id=yes_tid,
                    market_slug=m.slug,
                    side="yes",
                    price=yes_p,
                    notional=self.capital_per_trade / 2,
                    strategy=self.name,
                    meta={"yes_p": yes_p, "no_p": no_p, "edge": edge},
                )
                portfolio.open_position(
                    token_id=no_tid,
                    market_slug=m.slug,
                    side="no",
                    price=no_p,
                    notional=self.capital_per_trade / 2,
                    strategy=self.name,
                    meta={"yes_p": yes_p, "no_p": no_p, "edge": edge},
                )


# ---------------------------------------------------------------------------
# Live stat arb
# ---------------------------------------------------------------------------


class LiveStatArb(LiveStrategy):
    name = "live_stat_arb"

    def __init__(self, min_edge: float = 0.03, capital_per_trade: float = 500.0) -> None:
        self.min_edge = min_edge
        self.capital_per_trade = capital_per_trade
        self._price_history: dict[str, list[float]] = {}

    def on_tick(self, portfolio, prices, markets, events, step):
        for m in markets:
            if not m.is_binary or not m.token_ids:
                continue
            tid = m.token_ids[0]
            p = prices.get(tid, 0)
            if p <= 0:
                continue

            hist = self._price_history.setdefault(tid, [])
            hist.append(p)

            if len(hist) < 20:
                continue

            ema = sum(hist[-20:]) / 20
            edge = ema - p
            if abs(edge) > self.min_edge:
                side = "yes" if edge > 0 else "no"
                price = p if edge > 0 else (1 - p)
                if price > 0:
                    portfolio.open_position(
                        token_id=tid,
                        market_slug=m.slug,
                        side=side,
                        price=price,
                        notional=self.capital_per_trade,
                        strategy=self.name,
                        meta={"edge": edge, "ema": ema, "market_price": p},
                    )


# ---------------------------------------------------------------------------
# Exchange connector (REST polling mode)
# ---------------------------------------------------------------------------


class ExchangeConnector:
    """Connects to Polymarket for live paper trading via REST polling."""

    def __init__(
        self,
        strategies: list[LiveStrategy] | None = None,
        initial_capital: float = 100_000.0,
        poll_interval_sec: float = 30.0,
        max_markets: int = 50,
        min_volume: float = 10_000,
    ) -> None:
        self.strategies = strategies or [
            LiveNegRiskRebalancer(),
            LiveSingleBinaryRebalancer(),
            LiveStatArb(),
        ]
        self.portfolio = PaperPortfolio(
            initial_capital=initial_capital,
            cash=initial_capital,
        )
        self.poll_interval = poll_interval_sec
        self.max_markets = max_markets
        self.min_volume = min_volume
        self._markets: list[MarketInfo] = []
        self._events: list[EventInfo] = []
        self._token_ids: list[str] = []
        self._step = 0
        self._running = False
        self._log: list[dict] = []

    def _refresh_markets(self) -> None:
        """Refresh market and event listings."""
        logger.info("Refreshing market listings…")
        self._markets = fetch_markets(
            limit=self.max_markets, active=True, closed=False,
            order="volume", ascending=False,
        )
        self._events = fetch_multi_outcome_events(min_markets=3, limit=20)

        self._token_ids = []
        for m in self._markets:
            self._token_ids.extend(m.token_ids)
        logger.info("Tracking %d markets, %d events, %d tokens",
                     len(self._markets), len(self._events), len(self._token_ids))

    def _fetch_prices(self) -> dict[str, float]:
        """Fetch current midpoints for all tracked tokens."""
        if not self._token_ids:
            return {}
        # Fetch in batches of 50 (API limit)
        prices: dict[str, float] = {}
        for i in range(0, len(self._token_ids), 50):
            batch = self._token_ids[i:i + 50]
            try:
                batch_prices = fetch_midpoints(batch)
                prices.update(batch_prices)
            except Exception as exc:
                logger.warning("Price fetch failed: %s", exc)
        return prices

    def _tick(self, prices: dict[str, float]) -> None:
        """Run all strategies on current prices."""
        for strategy in self.strategies:
            try:
                strategy.on_tick(
                    self.portfolio, prices,
                    self._markets, self._events, self._step,
                )
            except Exception as exc:
                logger.error("Strategy %s error: %s", strategy.name, exc)

        self.portfolio.record_equity(prices)

        # Close old positions (> 30 min)
        now = time.time()
        to_close = []
        for idx, pos in enumerate(self.portfolio.positions):
            if now - pos.entry_time > 1800:
                to_close.append(idx)
        for offset, idx in enumerate(to_close):
            adj_idx = idx - offset
            p = prices.get(self.portfolio.positions[adj_idx].token_id,
                           self.portfolio.positions[adj_idx].entry_price)
            self.portfolio.close_position(adj_idx, p, strategy="auto_close")

        self._step += 1

    async def run_for(self, hours: float = 5.0) -> dict:
        """Run paper trading for the specified duration."""
        duration_sec = hours * 3600
        start_time = time.time()
        refresh_interval = 300  # refresh market list every 5 min
        last_refresh = 0

        logger.info("Starting paper trading for %.1f hours…", hours)
        self._running = True

        while self._running and (time.time() - start_time) < duration_sec:
            elapsed = time.time() - start_time

            # Periodic market refresh
            if time.time() - last_refresh > refresh_interval:
                try:
                    self._refresh_markets()
                    last_refresh = time.time()
                except Exception as exc:
                    logger.error("Market refresh failed: %s", exc)

            # Fetch prices and tick
            try:
                prices = self._fetch_prices()
                if prices:
                    self._tick(prices)

                    if self._step % 10 == 0:
                        mtm = self.portfolio.mark_to_market(prices)
                        pnl = mtm - self.portfolio.initial_capital
                        n_pos = len(self.portfolio.positions)
                        n_trades = len(self.portfolio.trades)
                        logger.info(
                            "[%02d:%02d] Step %d | MTM $%.2f | PnL $%.2f | "
                            "Positions %d | Trades %d",
                            int(elapsed // 3600), int((elapsed % 3600) // 60),
                            self._step, mtm, pnl, n_pos, n_trades,
                        )
            except Exception as exc:
                logger.error("Tick failed: %s", exc)

            await asyncio.sleep(self.poll_interval)

        self._running = False
        elapsed = time.time() - start_time
        logger.info("Paper trading complete after %.1f hours, %d steps",
                     elapsed / 3600, self._step)

        return self._build_report()

    def stop(self) -> None:
        self._running = False

    def _build_report(self) -> dict:
        """Build summary report of the paper trading session."""
        trades = self.portfolio.trades
        pnl_list = [t.pnl for t in trades if t.action == "close"]
        total_pnl = sum(pnl_list)
        n_trades = len([t for t in trades if t.action == "close"])
        n_winners = len([p for p in pnl_list if p > 0])

        equity_ts = self.portfolio.equity_history
        if equity_ts:
            equity_values = [e[1] for e in equity_ts]
            max_equity = max(equity_values)
            min_equity = min(equity_values)
            max_dd = (max_equity - min_equity) / max_equity if max_equity > 0 else 0
        else:
            max_dd = 0

        # Per-strategy breakdown
        strategy_pnl: dict[str, float] = {}
        strategy_trades: dict[str, int] = {}
        for t in trades:
            if t.action == "close":
                strategy_pnl[t.strategy] = strategy_pnl.get(t.strategy, 0) + t.pnl
                strategy_trades[t.strategy] = strategy_trades.get(t.strategy, 0) + 1

        report = {
            "duration_hours": len(equity_ts) * self.poll_interval / 3600 if equity_ts else 0,
            "total_steps": self._step,
            "total_pnl": total_pnl,
            "total_trades": n_trades,
            "win_rate": n_winners / n_trades if n_trades > 0 else 0,
            "max_drawdown": max_dd,
            "final_equity": equity_ts[-1][1] if equity_ts else self.portfolio.initial_capital,
            "return_pct": total_pnl / self.portfolio.initial_capital * 100,
            "strategy_pnl": strategy_pnl,
            "strategy_trades": strategy_trades,
            "open_positions": len(self.portfolio.positions),
        }
        return report


# ---------------------------------------------------------------------------
# WebSocket connector (optional, lower latency)
# ---------------------------------------------------------------------------


class WebSocketConnector:
    """Real-time WebSocket feed from Polymarket CLOB."""

    def __init__(self, token_ids: list[str]) -> None:
        if not HAS_WEBSOCKETS:
            raise ImportError("websockets package required: pip install websockets")
        self.token_ids = token_ids
        self._prices: dict[str, float] = {}
        self._callbacks: list[Callable] = []
        self._ws = None

    def on_price_update(self, callback: Callable) -> None:
        self._callbacks.append(callback)

    @property
    def prices(self) -> dict[str, float]:
        return dict(self._prices)

    async def connect(self) -> None:
        """Connect to Polymarket WebSocket and subscribe to price updates."""
        logger.info("Connecting to Polymarket WebSocket…")
        self._ws = await websockets.connect(WS_URL)

        # Subscribe to market channels
        for tid in self.token_ids:
            sub_msg = json.dumps({
                "type": "subscribe",
                "channel": "market",
                "market": tid,
            })
            await self._ws.send(sub_msg)
        logger.info("Subscribed to %d token feeds", len(self.token_ids))

    async def listen(self) -> None:
        """Listen for price updates."""
        if not self._ws:
            await self.connect()

        async for message in self._ws:
            try:
                data = json.loads(message)
                msg_type = data.get("type", "")

                if msg_type == "price_change":
                    token_id = data.get("market", "")
                    price = float(data.get("price", 0))
                    if token_id and price > 0:
                        self._prices[token_id] = price
                        for cb in self._callbacks:
                            cb(token_id, price, data)

                elif msg_type == "book":
                    token_id = data.get("market", "")
                    bids = data.get("bids", [])
                    asks = data.get("asks", [])
                    if bids and asks:
                        mid = (float(bids[0]["price"]) + float(asks[0]["price"])) / 2
                        self._prices[token_id] = mid
                        for cb in self._callbacks:
                            cb(token_id, mid, data)

            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.debug("WS parse error: %s", exc)

    async def close(self) -> None:
        if self._ws:
            await self._ws.close()

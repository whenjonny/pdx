"""Event-driven backtest with rolling-window analytics.

Simulates production microstructure:
- Venues emit price ticks at independent cadences (Poly ~3s, PDX ~1.5s)
- Signal generation uses rolling-window EMA / volatility / liquidity
- Order submission has latency; price drifts during the gap
- Legs fill/fail independently; failures trigger hedge attempts
- Markets settle at deadline; rare settlement divergence between venues
- Full risk manager integration: Kelly, volume scaling, adverse selection

Usage:
    python stat_arb/run_event_backtest.py [--markets 20] [--hours 24] [--seeds 5]
    python stat_arb/run_event_backtest.py --scenario hostile --hours 48
"""

from __future__ import annotations

import argparse
import heapq
import logging
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto

import numpy as np

logging.disable(logging.WARNING)

from pdx_arb.config import ArbConfig, PolymarketConfig, PredictXConfig
from pdx_arb.risk.risk_manager import ArbRiskManager
from pdx_arb.strategy.spread import compute_cross_venue_arb
from pdx_arb.types import (
    ArbSignal,
    ArbTrade,
    LegOrder,
    MarketPair,
    OrderStatus,
    PricePair,
    Side,
    Venue,
    VenuePrice,
)


# ── Event system ─────────────────────────────────────────────────────────────

class EType(Enum):
    POLY_TICK = auto()
    PDX_TICK = auto()
    ORDER_ATTEMPT = auto()
    SETTLEMENT = auto()

_SEQ = 0

@dataclass(order=True)
class Event:
    t: float
    seq: int = field(compare=True)
    etype: EType = field(compare=False)
    mid: int = field(compare=False)
    data: dict = field(compare=False, default_factory=dict)


def push(heap: list, t: float, etype: EType, mid: int, data: dict | None = None):
    global _SEQ
    _SEQ += 1
    heapq.heappush(heap, Event(t, _SEQ, etype, mid, data or {}))


# ── Rolling window per market ────────────────────────────────────────────────

class RollingState:
    def __init__(self, ema_alpha: float = 0.18):
        self.poly_yes = 0.5
        self.poly_no = 0.5
        self.pdx_yes = 0.5
        self.pdx_no = 0.5
        self.poly_liq = 5_000.0
        self.pdx_liq = 3_000.0

        self._alpha = ema_alpha
        self.spread_ema = 0.0
        self.vol_ema = 0.01
        self.obs = 0

        self._prev_poly = 0.5
        self._recent_spreads: deque[float] = deque(maxlen=50)

    def update_poly(self, yes: float, liq: float):
        self._prev_poly = self.poly_yes
        self.poly_yes = yes
        self.poly_no = 1.0 - yes
        self.poly_liq = 0.9 * self.poly_liq + 0.1 * liq
        self._tick()

    def update_pdx(self, yes: float, liq: float):
        self.pdx_yes = yes
        self.pdx_no = 1.0 - yes
        self.pdx_liq = 0.9 * self.pdx_liq + 0.1 * liq
        self._tick()

    def _tick(self):
        self.obs += 1
        cost = min(self.poly_yes + self.pdx_no, self.pdx_yes + self.poly_no)
        gross_bps = (1.0 - cost) * 10_000
        self.spread_ema = (1 - self._alpha) * self.spread_ema + self._alpha * gross_bps
        self._recent_spreads.append(gross_bps)
        dp = abs(self.poly_yes - self._prev_poly)
        self.vol_ema = (1 - self._alpha) * self.vol_ema + self._alpha * dp


# ── Market path generator ────────────────────────────────────────────────────

def generate_paths(
    n_markets: int,
    hours: float,
    seed: int,
    poly_dt: float = 15.0,
    pdx_dt: float = 10.0,
    lag_s: float = 2.0,
    venue_noise: float = 0.02,
    settlement_diverge_prob: float = 0.01,
) -> tuple[list, list[MarketPair], np.random.Generator]:
    rng = np.random.default_rng(seed)
    total_s = hours * 3600
    heap: list[Event] = []
    pairs: list[MarketPair] = []

    for i in range(n_markets):
        pair = MarketPair(
            pair_id=f"evt_{i:03d}",
            question=f"Event market {i}",
            poly_condition_id=f"c_{i}",
            poly_token_ids=[f"y_{i}", f"n_{i}"],
            pdx_market_id=i,
        )
        pairs.append(pair)

        n_latent = int(total_s / 0.5) + 2
        latent = np.clip(
            0.5 + np.cumsum(rng.normal(0, 0.002, n_latent)), 0.02, 0.98,
        )

        # Poly ticks
        t = rng.exponential(poly_dt)
        while t < total_s:
            idx = min(int(t / 0.5), n_latent - 1)
            price = float(np.clip(latent[idx] + rng.normal(0, 0.005), 0.01, 0.99))
            liq = float(np.clip(5000 + rng.normal(0, 1000), 500, 30_000))
            push(heap, t, EType.POLY_TICK, i, {"yes": price, "liq": liq})
            t += rng.exponential(poly_dt)

        # PDX ticks (lagged + noisier)
        t = rng.exponential(pdx_dt)
        while t < total_s:
            idx = min(int(max(t - lag_s, 0) / 0.5), n_latent - 1)
            price = float(np.clip(latent[idx] + rng.normal(0, venue_noise), 0.01, 0.99))
            liq = float(np.clip(3000 + rng.normal(0, 800), 300, 15_000))
            push(heap, t, EType.PDX_TICK, i, {"yes": price, "liq": liq})
            t += rng.exponential(pdx_dt)

        # Settlement
        settle_t = total_s - 60 + rng.uniform(-30, 30)
        outcome = int(latent[-1] > 0.5)
        pdx_outcome = 1 - outcome if rng.random() < settlement_diverge_prob else outcome
        push(heap, settle_t, EType.SETTLEMENT, i, {
            "poly_outcome": outcome,
            "pdx_outcome": pdx_outcome,
            "latent": latent,
        })

    heapq.heapify(heap)
    return heap, pairs, rng


# ── Friction parameters ──────────────────────────────────────────────────────

@dataclass
class FrictionParams:
    latency_mean_s: float = 1.0
    latency_std_s: float = 0.3
    leg_fail_prob: float = 0.03
    impact_coeff: float = 0.003
    adverse_prob: float = 0.05
    stale_drift_factor: float = 0.5

SCENARIOS = {
    "perfect": FrictionParams(0, 0, 0, 0, 0, 0),
    "mild": FrictionParams(0.5, 0.1, 0.02, 0.002, 0.03, 0.3),
    "realistic": FrictionParams(1.0, 0.3, 0.05, 0.005, 0.10, 0.5),
    "hostile": FrictionParams(2.0, 0.5, 0.10, 0.010, 0.25, 0.8),
}


# ── Event engine ─────────────────────────────────────────────────────────────

class EventEngine:
    def __init__(
        self,
        heap: list[Event],
        pairs: list[MarketPair],
        rng: np.random.Generator,
        config: ArbConfig,
        friction: FrictionParams,
        initial_capital: float = 50_000.0,
    ):
        self.heap = heap
        self.pairs = {p.pdx_market_id: p for p in pairs}
        self.rng = rng
        self.config = config
        self.fp = friction
        self.risk = ArbRiskManager(config, initial_capital)

        self.states: dict[int, RollingState] = {
            p.pdx_market_id: RollingState() for p in pairs
        }

        self.last_signal_t: dict[int, float] = {}
        self.cooldown_s = config.cooldown_s
        self.min_obs = 6

        # Open positions: mid -> list of open trade dicts
        self.open_trades: list[dict] = []
        self.closed_trades: list[dict] = []

        # Stats
        self.n_signals = 0
        self.n_fills = 0
        self.n_leg_fails = 0
        self.n_hedges_ok = 0
        self.n_hedges_fail = 0
        self.n_adverse = 0

    def run(self) -> dict:
        while self.heap:
            ev = heapq.heappop(self.heap)
            self._dispatch(ev)
        self._force_settle_remaining()
        return self._results()

    def _dispatch(self, ev: Event):
        if ev.etype == EType.POLY_TICK:
            self.states[ev.mid].update_poly(ev.data["yes"], ev.data["liq"])
            self._maybe_signal(ev.mid, ev.t)
        elif ev.etype == EType.PDX_TICK:
            self.states[ev.mid].update_pdx(ev.data["yes"], ev.data["liq"])
            self._maybe_signal(ev.mid, ev.t)
        elif ev.etype == EType.ORDER_ATTEMPT:
            self._execute(ev)
        elif ev.etype == EType.SETTLEMENT:
            self._settle(ev)

    # ── Signal generation ────────────────────────────────────────────────

    def _maybe_signal(self, mid: int, t: float):
        st = self.states[mid]
        if st.obs < self.min_obs:
            return
        if t - self.last_signal_t.get(mid, -9999) < self.cooldown_s:
            return
        # Fast reject: no arb if both cross-venue costs >= 1
        cost_a = st.poly_yes + st.pdx_no
        cost_b = st.pdx_yes + st.poly_no
        if min(cost_a, cost_b) >= 0.99:
            return

        pair = self.pairs[mid]
        prices = PricePair(
            pair=pair,
            poly=VenuePrice(Venue.POLYMARKET, st.poly_yes, st.poly_no, st.poly_liq),
            pdx=VenuePrice(Venue.PREDICTX, st.pdx_yes, st.pdx_no, st.pdx_liq),
        )
        spread = compute_cross_venue_arb(prices, self.config)
        if spread is None or not spread.profitable:
            return
        if st.spread_ema < self.config.min_net_spread_bps * 0.7:
            return

        size = self.risk.size_position(
            cost_per_unit=spread.cost_per_unit,
            guaranteed_pnl_per_unit=spread.guaranteed_pnl_per_unit,
            pair_id=pair.pair_id,
            poly_liquidity=st.poly_liq,
            pdx_liquidity=st.pdx_liq,
        )
        if size < 10:
            return

        self.n_signals += 1
        self.last_signal_t[mid] = t

        latency = max(0, self.rng.normal(self.fp.latency_mean_s, self.fp.latency_std_s))
        push(self.heap, t + latency, EType.ORDER_ATTEMPT, mid, {
            "signal_t": t,
            "direction": spread.direction,
            "yes_price": spread.yes_price,
            "no_price": spread.no_price,
            "cost": spread.cost_per_unit,
            "gpnl": spread.guaranteed_pnl_per_unit,
            "size": size,
            "buy_venue_yes": spread.buy_venue_yes,
            "buy_venue_no": spread.buy_venue_no,
            "net_bps": spread.net_spread_bps,
            "fee_bps": spread.fee_cost_bps,
        })

    # ── Execution with frictions ─────────────────────────────────────────

    def _execute(self, ev: Event):
        d = ev.data
        mid = ev.mid
        st = self.states[mid]
        pair = self.pairs[mid]

        yes_price = d["yes_price"]
        no_price = d["no_price"]
        size = d["size"]
        cost = d["cost"]

        # Staleness: price drifted since signal
        if self.fp.stale_drift_factor > 0:
            drift = self.rng.normal(0, st.vol_ema * self.fp.stale_drift_factor)
            yes_price = max(0.01, min(0.99, yes_price + drift))
            no_price = max(0.01, min(0.99, no_price - drift * 0.5))

        # Market impact
        if self.fp.impact_coeff > 0:
            impact = self.fp.impact_coeff * np.sqrt(size / max(st.pdx_liq, 100))
            yes_price = min(0.99, yes_price + impact)
            no_price = min(0.99, no_price + impact)

        # Adverse selection
        is_adverse = self.rng.random() < self.fp.adverse_prob
        if is_adverse:
            self.n_adverse += 1
            yes_price = min(0.99, yes_price + self.rng.uniform(0.01, 0.04))
            no_price = min(0.99, no_price + self.rng.uniform(0.01, 0.04))
            self.risk.record_price_movement(pair.pair_id, adverse=True)
        else:
            self.risk.record_price_movement(pair.pair_id, adverse=False)

        actual_cost = yes_price + no_price
        actual_gpnl = 1.0 - actual_cost

        # Leg fills
        yes_filled = self.rng.random() >= self.fp.leg_fail_prob
        no_filled = self.rng.random() >= self.fp.leg_fail_prob

        self.risk.record_fill_attempt(pair.pair_id, yes_filled)
        self.risk.record_fill_attempt(pair.pair_id, no_filled)

        buy_venue_yes = d["buy_venue_yes"]
        buy_venue_no = d["buy_venue_no"]
        poly_fee_rate = self.config.polymarket.fee_bps_taker / 10_000
        pdx_fee_rate = self.config.predictx.fee_bps_normal / 10_000

        if buy_venue_yes == Venue.POLYMARKET:
            fee_yes_rate, fee_no_rate = poly_fee_rate, pdx_fee_rate
        else:
            fee_yes_rate, fee_no_rate = pdx_fee_rate, poly_fee_rate

        units = size / actual_cost if actual_cost > 0 else 0
        fee_yes = fee_yes_rate * yes_price * units
        fee_no = fee_no_rate * no_price * units

        if not yes_filled and not no_filled:
            return

        if yes_filled and no_filled:
            self.n_fills += 1
            pnl = units * actual_gpnl - fee_yes - fee_no
            trade = {
                "mid": mid, "pair_id": pair.pair_id,
                "units": units, "cost": actual_cost,
                "yes_price": yes_price, "no_price": no_price,
                "fee": fee_yes + fee_no, "pnl_locked": pnl,
                "buy_venue_yes": buy_venue_yes,
                "buy_venue_no": buy_venue_no,
                "settled": False, "final_pnl": 0.0,
                "open_t": ev.t, "size": size,
            }
            self.open_trades.append(trade)
            self._record_filled_trade(trade, pair)
            return

        # One leg failed → naked position
        self.n_leg_fails += 1
        self.risk.leg_failures._failure_count += 1

        hedge_slip = self.config.hedge_retry_slippage_bps / 10_000
        hedge_cost = size * hedge_slip + (fee_yes if yes_filled else fee_no)
        hedge_success = self.rng.random() > 0.3

        if hedge_success:
            self.n_hedges_ok += 1
            pnl = -hedge_cost
        else:
            self.n_hedges_fail += 1
            naked_loss = size * self.rng.uniform(0.02, 0.15)
            pnl = -(naked_loss + hedge_cost * 0.5)

        trade = {
            "mid": mid, "pair_id": pair.pair_id,
            "units": units, "cost": actual_cost,
            "yes_price": yes_price, "no_price": no_price,
            "fee": hedge_cost, "pnl_locked": pnl,
            "buy_venue_yes": buy_venue_yes,
            "buy_venue_no": buy_venue_no,
            "settled": True, "final_pnl": pnl,
            "open_t": ev.t, "size": size, "leg_fail": True,
        }
        self.closed_trades.append(trade)
        self._record_pnl(pnl, pair)

    def _record_filled_trade(self, trade: dict, pair: MarketPair):
        signal = self._make_signal(trade, pair)
        arb_trade = self._make_arb_trade(trade, signal)
        self.risk.record_trade(arb_trade)

    def _record_pnl(self, pnl: float, pair: MarketPair):
        self.risk.capital += pnl
        self.risk._total_pnl += pnl
        self.risk._daily_pnl += pnl
        self.risk._peak_capital = max(self.risk._peak_capital, self.risk.capital)

    # ── Settlement ───────────────────────────────────────────────────────

    def _settle(self, ev: Event):
        mid = ev.mid
        poly_out = ev.data["poly_outcome"]
        pdx_out = ev.data["pdx_outcome"]

        remaining = []
        for trade in self.open_trades:
            if trade["mid"] != mid:
                remaining.append(trade)
                continue

            buy_yes_venue = trade["buy_venue_yes"]
            buy_no_venue = trade["buy_venue_no"]
            units = trade["units"]

            if buy_yes_venue == Venue.POLYMARKET:
                yes_outcome = poly_out
                no_outcome = pdx_out
            else:
                yes_outcome = pdx_out
                no_outcome = poly_out

            yes_payout = units if yes_outcome == 1 else 0
            no_payout = units if no_outcome == 0 else 0
            total_payout = yes_payout + no_payout

            cost_total = trade["units"] * trade["cost"]
            pnl = total_payout - cost_total - trade["fee"]
            trade["settled"] = True
            trade["final_pnl"] = pnl
            self.closed_trades.append(trade)

            pair = self.pairs[mid]
            self._record_pnl(pnl, pair)

        self.open_trades = remaining

    def _force_settle_remaining(self):
        for trade in self.open_trades:
            trade["settled"] = True
            trade["final_pnl"] = trade["pnl_locked"]
            self.closed_trades.append(trade)
            pair = self.pairs[trade["mid"]]
            self._record_pnl(trade["pnl_locked"], pair)
        self.open_trades = []

    # ── Helpers ───────────────────────────────────────────────────────────

    def _make_signal(self, trade: dict, pair: MarketPair) -> ArbSignal:
        prices = PricePair(
            pair=pair,
            poly=VenuePrice(Venue.POLYMARKET, trade["yes_price"], trade["no_price"], 5000),
            pdx=VenuePrice(Venue.PREDICTX, trade["yes_price"], trade["no_price"], 3000),
        )
        return ArbSignal(
            pair=pair, prices=prices,
            direction="event", buy_venue=trade["buy_venue_yes"],
            sell_venue=trade["buy_venue_no"], buy_side=Side.BUY_YES,
            gross_spread_bps=0, net_spread_bps=0, fee_cost_bps=0,
            suggested_size_usd=trade["size"], edge=0, confidence=0,
        )

    def _make_arb_trade(self, trade: dict, signal: ArbSignal) -> ArbTrade:
        return ArbTrade(
            trade_id=f"evt_{trade['mid']}_{trade['open_t']:.0f}",
            signal=signal,
            leg_buy=LegOrder(
                venue=trade["buy_venue_yes"], market_ref=str(trade["mid"]),
                side=Side.BUY_YES, size_usd=trade["size"],
                limit_price=trade["yes_price"], status=OrderStatus.FILLED,
                fill_price=trade["yes_price"], fill_size=trade["units"],
            ),
            leg_sell=LegOrder(
                venue=trade["buy_venue_no"], market_ref=str(trade["mid"]),
                side=Side.BUY_NO, size_usd=trade["size"],
                limit_price=trade["no_price"], status=OrderStatus.FILLED,
                fill_price=trade["no_price"], fill_size=trade["units"],
            ),
            status="filled", pnl_net=trade["pnl_locked"],
        )

    # ── Results ──────────────────────────────────────────────────────────

    def _results(self) -> dict:
        pnls = [t["final_pnl"] for t in self.closed_trades]
        n = len(pnls)
        wins = sum(1 for p in pnls if p > 0)
        total_pnl = sum(pnls)

        peak = self.risk.initial_capital
        equity = self.risk.initial_capital
        max_dd = 0.0
        for p in pnls:
            equity += p
            peak = max(peak, equity)
            dd = (peak - equity) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        pnl_arr = np.array(pnls) if pnls else np.array([0.0])
        sharpe = (
            pnl_arr.mean() / pnl_arr.std() * np.sqrt(252)
            if len(pnl_arr) > 1 and pnl_arr.std() > 1e-10 else 0.0
        )

        return {
            "n_trades": n,
            "n_wins": wins,
            "win_rate": wins / n if n > 0 else 0,
            "pnl": total_pnl,
            "sharpe": sharpe,
            "max_dd_pct": max_dd * 100,
            "signals": self.n_signals,
            "fills": self.n_fills,
            "leg_failures": self.n_leg_fails,
            "hedges_ok": self.n_hedges_ok,
            "hedges_fail": self.n_hedges_fail,
            "adverse_selections": self.n_adverse,
            "final_capital": self.risk.capital,
        }


# ── Runner ───────────────────────────────────────────────────────────────────

def make_config() -> ArbConfig:
    return ArbConfig(
        min_net_spread_bps=100.0,
        max_position_usd=2_000.0,
        max_total_exposure_usd=30_000.0,
        max_positions=50,
        max_per_market_usd=10_000.0,
        kelly_fraction=0.5,
        cooldown_s=8.0,
        slippage_bps=15.0,
        settlement_risk_bps=0.0,
        min_market_volume_usd=500.0,
        thin_market_size_cap_usd=50_000.0,
        hedge_retry_slippage_bps=100.0,
        max_naked_exposure_usd=10_000.0,
        polymarket=PolymarketConfig(fee_bps_taker=80.0),
        predictx=PredictXConfig(fee_bps_normal=30.0),
    )


def run_scenario_sweep(n_markets: int, hours: float, n_seeds: int):
    print(f"\n{'=' * 90}")
    print(f"  Event-Driven Backtest: {n_markets} markets × {hours:.0f}h × {n_seeds} seeds")
    print(f"{'=' * 90}")

    header = (
        f"  {'Scenario':<14s} {'Trades':>7s} {'Win%':>7s} "
        f"{'PnL':>12s} {'Sharpe':>8s} {'MaxDD':>7s} "
        f"{'LegFail':>8s} {'Hedge%':>7s} {'Adverse':>8s}"
    )
    print(f"\n{header}")
    print(f"  {'-' * 84}")

    config = make_config()

    for name, fp in SCENARIOS.items():
        all_r: list[dict] = []
        for i in range(n_seeds):
            seed = 42 + i * 17
            heap, pairs, rng = generate_paths(
                n_markets, hours, seed,
                settlement_diverge_prob=0.01 if name != "perfect" else 0.0,
            )
            engine = EventEngine(heap, pairs, rng, config, fp)
            r = engine.run()
            all_r.append(r)

        avg = lambda key: np.mean([r[key] for r in all_r])
        total_hedges = avg("hedges_ok") + avg("hedges_fail")
        hedge_pct = avg("hedges_ok") / total_hedges * 100 if total_hedges > 0 else 0

        print(
            f"  {name:<14s} {avg('n_trades'):>7.0f} {avg('win_rate'):>6.1%} "
            f"${avg('pnl'):>+11,.0f} {avg('sharpe'):>+8.2f} "
            f"{avg('max_dd_pct'):>6.1f}% "
            f"{avg('leg_failures'):>8.0f} {hedge_pct:>6.0f}% "
            f"{avg('adverse_selections'):>8.0f}"
        )

    print()


def run_spread_sweep(n_markets: int, hours: float, n_seeds: int):
    print(f"\n{'=' * 90}")
    print(f"  Min Spread Threshold vs Realistic Frictions (event-driven)")
    print(f"{'=' * 90}")

    fp = SCENARIOS["realistic"]

    print(f"\n  {'MinSpread':>10s} {'Trades':>8s} {'Win%':>7s} {'PnL':>12s} "
          f"{'Sharpe':>8s} {'MaxDD':>7s} {'T-stat':>8s}")
    print(f"  {'-' * 64}")

    for thresh in [50, 80, 100, 150, 200, 300]:
        config = make_config()
        config.min_net_spread_bps = float(thresh)
        pnls = []

        for i in range(n_seeds):
            seed = 42 + i * 17
            heap, pairs, rng = generate_paths(n_markets, hours, seed)
            engine = EventEngine(heap, pairs, rng, config, fp)
            r = engine.run()
            pnls.append(r)

        pnl_arr = np.array([r["pnl"] for r in pnls])
        t_stat = (
            pnl_arr.mean() / (pnl_arr.std() / np.sqrt(len(pnl_arr)))
            if pnl_arr.std() > 0 else 0
        )
        avg = lambda key: np.mean([r[key] for r in pnls])

        print(
            f"  {thresh:>10d} {avg('n_trades'):>8.0f} "
            f"{avg('win_rate'):>6.1%} ${avg('pnl'):>+11,.0f} "
            f"{avg('sharpe'):>+8.2f} {avg('max_dd_pct'):>6.1f}% "
            f"{t_stat:>+8.2f}"
        )


def run_rolling_window_analysis(n_markets: int, hours: float, seed: int = 42):
    """Show how rolling-window state evolves over time for one seed."""
    print(f"\n{'=' * 90}")
    print(f"  Rolling Window Timeline (seed={seed}, {n_markets} markets, {hours:.0f}h)")
    print(f"{'=' * 90}")

    config = make_config()
    fp = SCENARIOS["realistic"]
    heap, pairs, rng = generate_paths(n_markets, hours, seed)

    # Snapshot equity at intervals
    checkpoints = [hours * 3600 * frac for frac in [0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0]]
    check_idx = 0

    engine = EventEngine(heap, pairs, rng, config, fp)

    print(f"\n  {'Time':>8s} {'Est Equity':>12s} {'Closed':>8s} {'Open':>6s} "
          f"{'Locked PnL':>12s} {'LegFails':>9s} {'Signals':>8s}")
    print(f"  {'-' * 68}")

    while engine.heap:
        ev = heapq.heappop(engine.heap)
        engine._dispatch(ev)

        if check_idx < len(checkpoints) and ev.t >= checkpoints[check_idx]:
            n_closed = len(engine.closed_trades)
            open_locked = sum(t["pnl_locked"] for t in engine.open_trades)
            est_equity = engine.risk.capital + open_locked
            h = ev.t / 3600

            print(
                f"  {h:>7.1f}h ${est_equity:>11,.0f} {n_closed:>8d} "
                f"{len(engine.open_trades):>6d} ${open_locked:>+11,.0f} "
                f"{engine.n_leg_fails:>9d} {engine.n_signals:>8d}"
            )
            check_idx += 1

    engine._force_settle_remaining()
    r = engine._results()
    print(f"\n  Final: {r['n_trades']} trades, PnL ${r['pnl']:+,.0f}, "
          f"win rate {r['win_rate']:.1%}, max DD {r['max_dd_pct']:.1f}%")


def main():
    parser = argparse.ArgumentParser(description="Event-driven cross-venue arb backtest")
    parser.add_argument("--markets", type=int, default=10)
    parser.add_argument("--hours", type=float, default=12)
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--scenario", type=str, default=None,
                        choices=list(SCENARIOS.keys()))
    parser.add_argument("--sweep", action="store_true", help="Run spread threshold sweep")
    parser.add_argument("--timeline", action="store_true", help="Show rolling window timeline")
    args = parser.parse_args()

    if args.timeline:
        run_rolling_window_analysis(args.markets, args.hours)
    elif args.sweep:
        run_spread_sweep(args.markets, args.hours, args.seeds)
    else:
        run_scenario_sweep(args.markets, args.hours, args.seeds)


if __name__ == "__main__":
    main()

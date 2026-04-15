"""End-to-end sanity tests for strategies."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

from pdx_backtest.data import (
    generate_binary_path,
    generate_negrisk_scenario,
)
from pdx_backtest.strategies import (
    BayesianMarketMaker,
    NegRiskRebalancer,
    StatisticalArb,
    TimeArb,
)


# ---------------------------------------------------------------------------
# NegRisk
# ---------------------------------------------------------------------------


def test_negrisk_arb_profits_are_nonnegative_in_guaranteed_regime():
    """A NegRisk arb is guaranteed profit when cost < guaranteed payout.

    Given our threshold=0 and fee=0, *every* executed trade must
    produce pnl >= 0 by construction.
    """
    snaps = generate_negrisk_scenario(n_outcomes=5, n_snapshots=300,
                                      yes_mispricing=0.05,
                                      opportunity_rate=0.5,
                                      seed=1)
    strat = NegRiskRebalancer(threshold=0.0, taker_fee_bps=0.0,
                              capital_per_trade=1_000.0)
    result = strat.run(snaps)
    # Every executed trade is a guaranteed profit.
    assert (result.pnl_per_trade >= 0).all()
    assert result.n_trades > 0


def test_negrisk_respects_threshold():
    """With a huge threshold, no trades fire even if opportunities exist."""
    snaps = generate_negrisk_scenario(n_outcomes=5, n_snapshots=200, seed=3)
    strat = NegRiskRebalancer(threshold=1.0, capital_per_trade=100.0)
    result = strat.run(snaps)
    assert result.n_trades == 0


# ---------------------------------------------------------------------------
# Market maker
# ---------------------------------------------------------------------------


def test_market_maker_collects_some_fees_regardless_of_outcome():
    path = generate_binary_path(n_steps=200, seed=42)
    mm = BayesianMarketMaker(initial_liquidity=10_000.0, prior_yes=0.5,
                             trader_intensity=5.0, informed_fraction=0.2)
    result = mm.run(path, seed=42)
    assert result.notes["fees_collected"] > 0
    assert result.notes["cash_inflow"] > 0


def test_market_maker_seeded_pool_reflects_prior():
    """When prior_yes=0.7, the pool should seed with price ≈ 0.7."""
    path = generate_binary_path(n_steps=10, seed=42)
    mm = BayesianMarketMaker(initial_liquidity=10_000.0, prior_yes=0.7,
                             trader_intensity=0.0,    # no flow → price stable
                             informed_fraction=0.0)
    result = mm.run(path, seed=42)
    assert result.notes["final_price_yes"] == pytest.approx(0.7, abs=1e-6)


def test_adverse_selection_reduces_mm_pnl():
    """Pure informed flow should be net negative for the MM."""
    path = generate_binary_path(n_steps=200, seed=99, vol=0.02)
    mm_informed = BayesianMarketMaker(initial_liquidity=10_000.0,
                                      informed_fraction=1.0,
                                      trader_intensity=20.0)
    mm_uninformed = BayesianMarketMaker(initial_liquidity=10_000.0,
                                        informed_fraction=0.0,
                                        trader_intensity=20.0)
    r_informed = mm_informed.run(path, seed=99)
    r_uninformed = mm_uninformed.run(path, seed=99)
    # Informed flow wrt uninformed flow → smaller (or negative) MM PnL.
    assert r_informed.notes["final_pnl"] < r_uninformed.notes["final_pnl"]


# ---------------------------------------------------------------------------
# Statistical arbitrage
# ---------------------------------------------------------------------------


def test_stat_arb_runs_some_trades_when_edge_present():
    paths = [generate_binary_path(n_steps=100, seed=i) for i in range(50)]
    sa = StatisticalArb(taker_fee_bps=120.0, min_edge=0.01)
    result = sa.run(paths, seed=1)
    # With min_edge=1¢ there should definitely be some trades.
    assert result.n_trades > 0


def test_stat_arb_no_trades_when_edge_too_high():
    paths = [generate_binary_path(n_steps=100, seed=i) for i in range(10)]
    sa = StatisticalArb(taker_fee_bps=120.0, min_edge=0.99)
    result = sa.run(paths, seed=1)
    assert result.n_trades == 0


# ---------------------------------------------------------------------------
# Time arbitrage
# ---------------------------------------------------------------------------


def test_time_arb_only_trades_high_probability_outcomes():
    """Low-probability paths should never clear the fair_floor filter."""
    paths = [generate_binary_path(n_steps=60, initial_prob=0.2, seed=i)
             for i in range(20)]
    ta = TimeArb(fair_prob_floor=0.80, min_edge=0.02)
    result = ta.run(paths, seed=5)
    assert result.n_trades == 0


def test_time_arb_produces_trades_on_favourable_path():
    paths = [generate_binary_path(
        n_steps=60, initial_prob=0.9, vol=0.002,
        longshot_bias=0.1, seed=i,
    ) for i in range(30)]
    ta = TimeArb(fair_prob_floor=0.75, min_edge=0.02,
                 taker_fee_bps=0.0)
    result = ta.run(paths, seed=0)
    assert result.n_trades > 0

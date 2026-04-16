"""Tests for the six newly added strategies."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

from pdx_backtest.data import (
    generate_binary_path,
    generate_cross_platform_path,
)
from pdx_backtest.strategies import (
    CrossAssetArb,
    CrossPlatformArb,
    LongshotBiasExploiter,
    LVRArb,
    SingleBinaryRebalancer,
    VolatilityEventStrategy,
)


# ---------------------------------------------------------------------------
# Single-binary rebalancer
# ---------------------------------------------------------------------------


def test_single_binary_all_trades_profitable():
    path = generate_binary_path(n_steps=300, seed=10)
    sb = SingleBinaryRebalancer(threshold=0.0, taker_fee_bps=0.0,
                                capital_per_trade=100.0, no_noise_std=0.02)
    result = sb.run(path, seed=10)
    if result.n_trades > 0:
        assert (result.pnl_per_trade >= -1e-9).all()


def test_single_binary_no_trades_with_huge_threshold():
    path = generate_binary_path(n_steps=100, seed=1)
    sb = SingleBinaryRebalancer(threshold=1.0)
    result = sb.run(path, seed=1)
    assert result.n_trades == 0


# ---------------------------------------------------------------------------
# Cross-platform
# ---------------------------------------------------------------------------


def test_cross_platform_finds_opportunities():
    paths = [generate_cross_platform_path(seed=i, mean_spread=0.04)
             for i in range(10)]
    cp = CrossPlatformArb(min_spread=0.02, capital_per_trade=500.0)
    result = cp.run(paths, seed=42)
    assert result.n_trades > 0
    # All cross-platform arbs should be profitable (guaranteed spread > fee).
    assert (result.pnl_per_trade > 0).all()


def test_cross_platform_no_trades_when_spread_tight():
    paths = [generate_cross_platform_path(seed=i, mean_spread=0.001,
                                          lead_lag=0, vol=0.001)
             for i in range(10)]
    cp = CrossPlatformArb(min_spread=0.10)  # very high bar
    result = cp.run(paths)
    assert result.n_trades == 0


# ---------------------------------------------------------------------------
# Longshot bias
# ---------------------------------------------------------------------------


def test_longshot_sells_low_priced_contracts():
    # Generate paths starting at 0.05 (long-shot territory).
    paths = [generate_binary_path(n_steps=50, initial_prob=0.05, vol=0.003,
                                  longshot_bias=0.05, seed=i)
             for i in range(20)]
    lb = LongshotBiasExploiter(sell_zone=(0.02, 0.15), taker_fee_bps=0.0)
    result = lb.run(paths)
    assert result.n_trades > 0
    # Check that sell_longshot_yes trades exist.
    assert any("sell_longshot" in t.action for t in result.trades)


def test_longshot_buys_high_priced_favourites():
    paths = [generate_binary_path(n_steps=50, initial_prob=0.95, vol=0.003,
                                  longshot_bias=0.05, seed=i)
             for i in range(20)]
    lb = LongshotBiasExploiter(buy_zone=(0.85, 0.98), taker_fee_bps=0.0)
    result = lb.run(paths)
    assert result.n_trades > 0


# ---------------------------------------------------------------------------
# LVR
# ---------------------------------------------------------------------------


def test_lvr_opens_and_closes_positions():
    path = generate_binary_path(n_steps=100, vol=0.02, seed=55)
    lvr = LVRArb(pool_liquidity=100_000.0, trade_size=100.0,
                 min_edge=0.02, hold_steps=3)
    result = lvr.run(path, seed=55)
    assert result.n_trades > 0
    open_count = sum(1 for t in result.trades if "open" in t.action)
    close_count = sum(1 for t in result.trades if "close" in t.action)
    assert close_count > 0
    assert open_count > 0


# ---------------------------------------------------------------------------
# Cross-asset arb
# ---------------------------------------------------------------------------


def test_cross_asset_runs():
    paths = [generate_binary_path(n_steps=100, seed=i) for i in range(30)]
    ca = CrossAssetArb(min_edge=0.02, taker_fee_bps=120.0)
    result = ca.run(paths, seed=42)
    assert result.n_trades > 0


def test_cross_asset_no_trades_large_edge():
    paths = [generate_binary_path(n_steps=100, seed=i) for i in range(10)]
    ca = CrossAssetArb(min_edge=0.99)
    result = ca.run(paths)
    assert result.n_trades == 0


# ---------------------------------------------------------------------------
# Volatility event
# ---------------------------------------------------------------------------


def test_vol_event_fires_when_panic_present():
    ve = VolatilityEventStrategy(capital_per_event=1000.0, panic_threshold=0.03)
    result = ve.run(n_events=30, seed=42)
    assert result.n_trades > 0


def test_vol_event_no_trades_high_threshold():
    ve = VolatilityEventStrategy(panic_threshold=1.0)
    result = ve.run(n_events=10, seed=42)
    assert result.n_trades == 0

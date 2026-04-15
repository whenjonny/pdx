"""Sanity tests for the CPMM simulator.

These mirror assertions that hold in the on-chain contract so if
PDXMarket.sol math ever changes, the backtest will also fail loudly.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from pdx_backtest.amm import CPMM, FeeSchedule


def test_initial_seed_is_50_50():
    pool = CPMM(initial_liquidity=10_000.0)
    assert pool.reserve_yes == pytest.approx(5_000.0)
    assert pool.reserve_no == pytest.approx(5_000.0)
    assert pool.price_yes == pytest.approx(0.5)


def test_buy_yes_moves_price_up():
    pool = CPMM(10_000.0)
    p0 = pool.price_yes
    pool.buy(100.0, is_yes=True)
    assert pool.price_yes > p0


def test_buy_no_moves_price_down():
    pool = CPMM(10_000.0)
    p0 = pool.price_yes
    pool.buy(100.0, is_yes=False)
    assert pool.price_yes < p0


def test_fee_schedule_with_and_without_evidence():
    fs = FeeSchedule()
    assert fs.rate(False) == pytest.approx(0.003)   # 0.30%
    assert fs.rate(True) == pytest.approx(0.001)    # 0.10%


def test_buy_then_sell_round_trip_has_loss_equal_to_fees_plus_slippage():
    """If you immediately sell the tokens you just bought you always
    lose money — the difference is fee + slippage."""
    pool = CPMM(100_000.0)
    usdc_in = 1_000.0
    tokens = pool.buy(usdc_in, is_yes=True)
    usdc_out = pool.sell(tokens, is_yes=True)
    # Round-trip must be a (small) loss.
    assert usdc_out < usdc_in
    # And the loss must be at least the fee (0.3% × 1000 = $3).
    assert (usdc_in - usdc_out) >= 0.003 * usdc_in * 0.9  # ~fees lower bound


def test_prices_sum_to_one_on_binary_market():
    pool = CPMM(10_000.0)
    pool.buy(250.0, is_yes=True)
    # priceYes + priceNo == 1 by construction (CPMM binary).
    assert pool.price_yes + pool.price_no == pytest.approx(1.0)


def test_k_is_invariant_post_seed():
    """The on-chain contract intentionally keeps k constant after
    the initial seed — trades converge through it."""
    pool = CPMM(10_000.0)
    k0 = pool.k
    for _ in range(5):
        pool.buy(100.0, is_yes=True)
    assert pool.k == pytest.approx(k0)


def test_buy_rejects_zero():
    pool = CPMM(10_000.0)
    with pytest.raises(ValueError):
        pool.buy(0.0, is_yes=True)

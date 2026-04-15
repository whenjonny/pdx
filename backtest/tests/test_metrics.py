"""Tests for metric computations."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

from pdx_backtest.metrics import compute_metrics, half_kelly, kelly_fraction


def test_empty_returns_yields_zero_metrics():
    m = compute_metrics(np.array([]), capital_base=1.0)
    assert m.n_trades == 0
    assert m.sharpe == 0.0
    assert m.total_return == 0.0


def test_constant_positive_pnl_gives_inf_profit_factor():
    pnl = np.array([10.0, 10.0, 10.0])
    ret = pnl / 1000.0
    m = compute_metrics(ret, pnl_per_trade=pnl, capital_base=1000.0, periods_per_year=252)
    assert m.win_rate == 1.0
    assert m.profit_factor == float("inf")
    assert m.total_pnl == pytest.approx(30.0)
    assert m.total_return == pytest.approx(0.03)


def test_mixed_pnl_computes_profit_factor_correctly():
    pnl = np.array([20.0, -5.0, 15.0, -10.0])
    ret = pnl / 100.0
    m = compute_metrics(ret, pnl_per_trade=pnl, capital_base=100.0)
    assert m.gross_profit == pytest.approx(35.0)
    assert m.gross_loss == pytest.approx(15.0)
    assert m.profit_factor == pytest.approx(35.0 / 15.0)
    assert m.win_rate == pytest.approx(0.5)


def test_max_drawdown_is_negative_or_zero():
    pnl = np.array([-10.0, -10.0, 5.0, 5.0])
    ret = pnl / 100.0
    m = compute_metrics(ret, pnl_per_trade=pnl, capital_base=100.0)
    assert m.max_drawdown < 0.0


def test_kelly_fraction_long():
    # Subjective 70%, market 50% → strong long.
    f = kelly_fraction(0.7, 0.5)
    assert f > 0
    assert f == pytest.approx(0.4)


def test_kelly_fraction_short():
    f = kelly_fraction(0.3, 0.5)
    assert f < 0


def test_half_kelly_is_half_of_kelly():
    p, pm = 0.6, 0.5
    assert half_kelly(p, pm) == pytest.approx(0.5 * kelly_fraction(p, pm))


def test_sharpe_positive_when_returns_beat_risk_free():
    rng = np.random.default_rng(0)
    ret = rng.normal(0.002, 0.01, size=252)  # 0.2% per day, 1% vol
    m = compute_metrics(ret, capital_base=1.0, periods_per_year=252, risk_free=0.04)
    # Should be clearly positive Sharpe.
    assert m.sharpe > 0.5


def test_kelly_clamps_to_bounds():
    # Kelly is (p-pm)/(1-pm).  With pm=0.01: (0.99-0.01)/0.99 ≈ 0.9899.
    # Always within [-1, 1] by construction; no actual clamp triggers here.
    f = kelly_fraction(0.99, 0.01)
    assert -1.0 <= f <= 1.0
    assert f == pytest.approx(0.98 / 0.99)

    # Market out of range → strategy returns 0 (cannot trade).
    assert kelly_fraction(0.5, 0.0) == 0.0
    assert kelly_fraction(0.5, 1.0) == 0.0

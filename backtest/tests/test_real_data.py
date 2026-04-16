"""Tests for real data infrastructure (offline — uses mocked API responses)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

from pdx_backtest.data import MarketPath, MultiOutcomeSnapshot, CrossPlatformPath
from pdx_backtest.exchange_connector import (
    LiveNegRiskRebalancer,
    LiveSingleBinaryRebalancer,
    LiveStatArb,
    PaperPortfolio,
)
from pdx_backtest.historical_data import _candles_to_market_path
from pdx_backtest.polymarket_client import (
    EventInfo,
    MarketInfo,
    PriceCandle,
)


# ---------------------------------------------------------------------------
# Candle → MarketPath conversion
# ---------------------------------------------------------------------------


def _make_candles(prices: list[float]) -> list[PriceCandle]:
    return [
        PriceCandle(timestamp=i * 60, open=p, high=p + 0.01,
                     low=p - 0.01, close=p)
        for i, p in enumerate(prices)
    ]


def test_candles_to_market_path_basic():
    candles = _make_candles([0.5, 0.52, 0.54, 0.53, 0.55])
    path = _candles_to_market_path(candles)
    assert isinstance(path, MarketPath)
    assert len(path) == 5
    assert path.market_price[0] == pytest.approx(0.5, abs=0.01)
    assert path.market_price[-1] == pytest.approx(0.55, abs=0.01)
    assert path.outcome in (0, 1)


def test_candles_to_market_path_ema_smoothing():
    prices = [0.5] * 10 + [0.8] * 10
    candles = _make_candles(prices)
    path = _candles_to_market_path(candles)
    # EMA should be smoother than raw prices
    assert path.true_prob[10] < 0.8  # not yet caught up
    assert path.true_prob[-1] > path.true_prob[10]  # trending up


def test_candles_to_market_path_empty():
    with pytest.raises(ValueError):
        _candles_to_market_path([])


def test_candles_to_market_path_outcome_from_final_price():
    candles = _make_candles([0.9, 0.92, 0.95])  # high → YES outcome
    path = _candles_to_market_path(candles)
    assert path.outcome == 1

    candles = _make_candles([0.1, 0.08, 0.05])  # low → NO outcome
    path = _candles_to_market_path(candles)
    assert path.outcome == 0


# ---------------------------------------------------------------------------
# Paper portfolio
# ---------------------------------------------------------------------------


def test_paper_portfolio_open_close():
    pf = PaperPortfolio(initial_capital=10_000, cash=10_000)
    trade = pf.open_position(
        token_id="tok1", market_slug="test", side="yes",
        price=0.50, notional=500, strategy="test_strat",
    )
    assert trade is not None
    assert pf.cash == 9_500
    assert len(pf.positions) == 1
    assert pf.positions[0].size == pytest.approx(1000.0)

    prices = {"tok1": 0.55}
    mtm = pf.mark_to_market(prices)
    assert mtm == pytest.approx(9_500 + 1000 * 0.55)

    close_trade = pf.close_position(0, current_price=0.55, strategy="test_strat")
    assert close_trade is not None
    assert close_trade.pnl == pytest.approx(50.0)  # (0.55 - 0.50) * 1000
    assert pf.cash == pytest.approx(10_050.0)
    assert len(pf.positions) == 0


def test_paper_portfolio_insufficient_cash():
    pf = PaperPortfolio(initial_capital=100, cash=100)
    trade = pf.open_position(
        token_id="tok1", market_slug="test", side="yes",
        price=0.50, notional=200, strategy="test",
    )
    assert trade is None
    assert pf.cash == 100


def test_paper_portfolio_equity_history():
    pf = PaperPortfolio(initial_capital=10_000, cash=10_000)
    pf.record_equity({"tok1": 0.5})
    assert len(pf.equity_history) == 1
    assert pf.equity_history[0][1] == 10_000


# ---------------------------------------------------------------------------
# Live strategies (unit tests with mock data)
# ---------------------------------------------------------------------------


def _make_market_info(slug, token_ids, outcomes=None, outcome_prices=None):
    return MarketInfo(
        condition_id="cond1",
        question=f"Will {slug} happen?",
        slug=slug,
        outcomes=outcomes or ["Yes", "No"],
        outcome_prices=outcome_prices or [0.5, 0.5],
        token_ids=token_ids,
        volume=100_000,
        liquidity=50_000,
        active=True,
        closed=False,
        group_item_title=slug,
        end_date="2026-12-31",
    )


def _make_event_info(slug, markets):
    return EventInfo(slug=slug, title=f"Event {slug}", markets=markets)


def test_live_negrisk_fires_on_mispricing():
    pf = PaperPortfolio(initial_capital=50_000, cash=50_000)
    strat = LiveNegRiskRebalancer(threshold=0.02, capital_per_trade=1000.0)

    markets_in_event = [
        _make_market_info(f"outcome_{i}", [f"tok_{i}"])
        for i in range(5)
    ]
    event = _make_event_info("election", markets_in_event)

    # Prices sum to 0.90 (< 1.0 - 0.02 = 0.98) → should trade
    prices = {f"tok_{i}": 0.18 for i in range(5)}
    strat.on_tick(pf, prices, [], [event], step=0)
    assert len(pf.trades) > 0
    assert all(t.strategy == "live_negrisk" for t in pf.trades)


def test_live_negrisk_no_trade_fair_value():
    pf = PaperPortfolio(initial_capital=50_000, cash=50_000)
    strat = LiveNegRiskRebalancer(threshold=0.02, capital_per_trade=1000.0)

    markets_in_event = [
        _make_market_info(f"outcome_{i}", [f"tok_{i}"])
        for i in range(5)
    ]
    event = _make_event_info("election", markets_in_event)

    # Prices sum to ~1.0 → no trade
    prices = {f"tok_{i}": 0.20 for i in range(5)}
    strat.on_tick(pf, prices, [], [event], step=0)
    assert len(pf.trades) == 0


def test_live_single_binary_fires_on_mispricing():
    pf = PaperPortfolio(initial_capital=50_000, cash=50_000)
    strat = LiveSingleBinaryRebalancer(threshold=0.005, capital_per_trade=500.0)

    m = _make_market_info("test", ["yes_tok", "no_tok"])
    # yes + no = 0.45 + 0.50 = 0.95 < 1.0 - 0.005 → arb
    prices = {"yes_tok": 0.45, "no_tok": 0.50}
    strat.on_tick(pf, prices, [m], [], step=0)
    assert len(pf.trades) == 2  # buys both yes and no


def test_live_single_binary_no_trade_fair():
    pf = PaperPortfolio(initial_capital=50_000, cash=50_000)
    strat = LiveSingleBinaryRebalancer(threshold=0.005, capital_per_trade=500.0)

    m = _make_market_info("test", ["yes_tok", "no_tok"])
    prices = {"yes_tok": 0.50, "no_tok": 0.50}
    strat.on_tick(pf, prices, [m], [], step=0)
    assert len(pf.trades) == 0


def test_live_stat_arb_needs_history():
    pf = PaperPortfolio(initial_capital=50_000, cash=50_000)
    strat = LiveStatArb(min_edge=0.03, capital_per_trade=500.0)

    m = _make_market_info("test", ["tok1"])
    # First 19 ticks: no trade (needs 20 history)
    for i in range(19):
        strat.on_tick(pf, {"tok1": 0.50}, [m], [], step=i)
    assert len(pf.trades) == 0


def test_live_stat_arb_fires_on_deviation():
    pf = PaperPortfolio(initial_capital=50_000, cash=50_000)
    strat = LiveStatArb(min_edge=0.03, capital_per_trade=500.0)

    m = _make_market_info("test", ["tok1"])
    # Build 20-step history at 0.50
    for i in range(20):
        strat.on_tick(pf, {"tok1": 0.50}, [m], [], step=i)

    # Now price drops to 0.40 → edge = 0.50 - 0.40 = 0.10 > 0.03
    strat.on_tick(pf, {"tok1": 0.40}, [m], [], step=20)
    assert len(pf.trades) > 0

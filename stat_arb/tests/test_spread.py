"""Tests for cross-venue arbitrage spread calculator and strategy logic."""

from __future__ import annotations

import numpy as np
import pytest

from pdx_arb.config import ArbConfig, PolymarketConfig, PredictXConfig
from pdx_arb.strategy.spread import compute_cross_venue_arb, compute_spread
from pdx_arb.types import (
    ArbSignal, ArbTrade, LegOrder, MarketPair, OrderStatus,
    PricePair, Side, Venue, VenuePrice,
)


def _config(**kwargs) -> ArbConfig:
    defaults = dict(
        min_net_spread_bps=80.0,
        slippage_bps=15.0,
        settlement_risk_bps=0.0,
        min_market_volume_usd=1_000.0,
        thin_market_size_cap_usd=50_000.0,
        polymarket=PolymarketConfig(fee_bps_taker=80.0),
        predictx=PredictXConfig(fee_bps_normal=30.0),
    )
    defaults.update(kwargs)
    return ArbConfig(**defaults)


def _pair() -> MarketPair:
    return MarketPair(
        pair_id="test_001",
        question="Test market",
        poly_condition_id="cond_001",
        poly_token_ids=["tok_yes", "tok_no"],
        pdx_market_id=0,
    )


def _prices(poly_yes: float, pdx_yes: float) -> PricePair:
    return PricePair(
        pair=_pair(),
        poly=VenuePrice(Venue.POLYMARKET, poly_yes, 1 - poly_yes, 10000),
        pdx=VenuePrice(Venue.PREDICTX, pdx_yes, 1 - pdx_yes, 5000),
    )


class TestCrossVenueArb:
    def test_no_arb_when_prices_equal(self):
        """When prices match, cross-venue cost = 1.0, no arb."""
        prices = _prices(0.55, 0.55)
        result = compute_cross_venue_arb(prices, _config())
        assert result is not None
        assert result.cost_per_unit == pytest.approx(1.0, abs=0.001)
        assert result.gross_spread_bps == pytest.approx(0, abs=5)

    def test_arb_exists_when_prices_diverge(self):
        """When poly=0.50 and pdx=0.60, there's arb: buy YES@0.50 + NO@0.40 = 0.90."""
        prices = _prices(0.50, 0.60)
        result = compute_cross_venue_arb(prices, _config(min_net_spread_bps=10.0))
        assert result is not None
        assert result.cost_per_unit < 1.0
        assert result.guaranteed_pnl_per_unit > 0
        assert result.gross_spread_bps > 0

    def test_buys_yes_on_cheaper_venue(self):
        """Buy YES where it's cheapest."""
        prices = _prices(0.40, 0.60)
        result = compute_cross_venue_arb(prices, _config())
        assert result is not None
        assert result.buy_venue_yes == Venue.POLYMARKET
        assert result.yes_price == pytest.approx(0.40)

    def test_buys_no_on_cheaper_venue(self):
        """Buy NO where it's cheapest (Poly NO = 0.40, PDX NO = 0.60)."""
        prices = _prices(0.60, 0.40)
        result = compute_cross_venue_arb(prices, _config())
        assert result is not None
        # poly_yes=0.60 + pdx_no=0.60 = 1.20
        # pdx_yes=0.40 + poly_no=0.40 = 0.80 ← cheaper
        assert result.buy_venue_yes == Venue.PREDICTX
        assert result.buy_venue_no == Venue.POLYMARKET
        assert result.cost_per_unit == pytest.approx(0.80, abs=0.01)

    def test_guaranteed_profit_formula(self):
        """Guaranteed profit = 1.0 - cost."""
        prices = _prices(0.45, 0.58)
        result = compute_cross_venue_arb(prices, _config())
        assert result is not None
        expected_profit = 1.0 - result.cost_per_unit
        assert result.guaranteed_pnl_per_unit == pytest.approx(expected_profit)

    def test_fees_reduce_net_spread(self):
        prices = _prices(0.45, 0.58)
        result = compute_cross_venue_arb(prices, _config())
        assert result is not None
        assert result.net_spread_bps < result.gross_spread_bps

    def test_large_divergence_is_profitable(self):
        prices = _prices(0.35, 0.65)
        result = compute_cross_venue_arb(prices, _config(min_net_spread_bps=50.0))
        assert result is not None
        assert result.profitable
        assert result.guaranteed_pnl_per_unit > 0

    def test_tiny_divergence_not_profitable(self):
        prices = _prices(0.50, 0.51)
        result = compute_cross_venue_arb(prices, _config(min_net_spread_bps=200.0))
        assert result is not None
        assert not result.profitable

    def test_zero_price_returns_none(self):
        prices = _prices(0.0, 0.55)
        result = compute_cross_venue_arb(prices, _config())
        assert result is None

    def test_symmetric_opportunities(self):
        """Both directions should be considered."""
        r1 = compute_cross_venue_arb(_prices(0.40, 0.60), _config())
        r2 = compute_cross_venue_arb(_prices(0.60, 0.40), _config())
        assert r1 is not None and r2 is not None
        assert r1.cost_per_unit == pytest.approx(r2.cost_per_unit, abs=0.001)

    def test_backward_compat_wrapper(self):
        """compute_spread delegates to cross-venue arb."""
        prices = _prices(0.45, 0.55)
        r1 = compute_spread(prices, _config())
        r2 = compute_cross_venue_arb(prices, _config())
        assert r1 is not None and r2 is not None
        assert r1.net_spread_bps == r2.net_spread_bps


class TestBacktest:
    def test_synthetic_path_generation(self):
        from stat_arb.run_backtest import generate_cross_venue_paths
        markets = generate_cross_venue_paths(n_markets=5, n_steps=100, seed=42)
        assert len(markets) == 5
        for m in markets:
            assert len(m["poly_yes"]) == 100
            assert len(m["pdx_yes"]) == 100
            assert m["outcome"] in (0, 1)
            assert np.all(m["poly_yes"] >= 0.01)
            assert np.all(m["poly_yes"] <= 0.99)

    def test_single_backtest_runs(self):
        from stat_arb.run_backtest import run_single_backtest
        result = run_single_backtest(n_markets=5, n_steps=100, seed=42)
        assert "n_trades" in result
        assert "pnl" in result
        assert "win_rate" in result
        assert isinstance(result["pnl"], float)

    def test_backtest_produces_trades(self):
        from stat_arb.run_backtest import run_single_backtest
        config = ArbConfig(
            min_net_spread_bps=30.0,
            max_position_usd=2000.0,
            max_total_exposure_usd=30000.0,
            max_positions=50,
            kelly_fraction=0.5,
            cooldown_s=0.0,
            slippage_bps=10.0,
            settlement_risk_bps=0.0,
            min_market_volume_usd=1_000.0,
            thin_market_size_cap_usd=50_000.0,
            polymarket=PolymarketConfig(fee_bps_taker=50.0),
            predictx=PredictXConfig(fee_bps_normal=20.0),
        )
        result = run_single_backtest(n_markets=20, n_steps=300, seed=42, config=config)
        assert result["n_trades"] > 0

    def test_cross_seed_determinism(self):
        from stat_arb.run_backtest import run_single_backtest
        r1 = run_single_backtest(n_markets=10, n_steps=200, seed=42)
        r2 = run_single_backtest(n_markets=10, n_steps=200, seed=42)
        assert r1["n_trades"] == r2["n_trades"]
        assert r1["pnl"] == pytest.approx(r2["pnl"])

    def test_risk_free_arb_high_win_rate(self):
        """Cross-venue arb should have near-100% win rate before fees."""
        from stat_arb.run_backtest import run_single_backtest
        config = ArbConfig(
            min_net_spread_bps=0.0,
            max_position_usd=5000.0,
            max_total_exposure_usd=50000.0,
            max_positions=100,
            kelly_fraction=0.5,
            cooldown_s=0.0,
            slippage_bps=0.0,
            settlement_risk_bps=0.0,
            min_market_volume_usd=1_000.0,
            thin_market_size_cap_usd=50_000.0,
            polymarket=PolymarketConfig(fee_bps_taker=0.0),
            predictx=PredictXConfig(fee_bps_normal=0.0),
        )
        result = run_single_backtest(n_markets=20, n_steps=300, seed=42, config=config)
        if result["n_trades"] > 0:
            assert result["win_rate"] > 0.90


class TestRiskManager:
    def test_drawdown_limit(self):
        from pdx_arb.risk.risk_manager import ArbRiskManager
        config = _config(max_drawdown_pct=10.0)
        rm = ArbRiskManager(config, initial_capital=10_000)
        rm.capital = 8_500
        rm._peak_capital = 10_000
        signal = _signal(net_spread=200)
        passed, reason = rm.check(signal)
        assert not passed
        assert "drawdown" in reason

    def test_position_limit(self):
        from pdx_arb.risk.risk_manager import ArbRiskManager
        config = _config(max_positions=2)
        rm = ArbRiskManager(config)
        rm._open_positions = {"a": 1000, "b": 1000}
        signal = _signal(net_spread=200)
        passed, reason = rm.check(signal)
        assert not passed
        assert "max positions" in reason

    def test_size_multiplier(self):
        from pdx_arb.risk.risk_manager import ArbRiskManager
        config = _config(max_drawdown_pct=20.0)
        rm = ArbRiskManager(config, initial_capital=10_000)
        assert rm.recommended_size_multiplier() == 1.0
        rm.capital = 8_500
        assert 0 < rm.recommended_size_multiplier() < 1.0

    def test_healthy_signal_passes(self):
        from pdx_arb.risk.risk_manager import ArbRiskManager
        config = _config()
        rm = ArbRiskManager(config, initial_capital=100_000)
        signal = _signal(net_spread=200, size=1000)
        passed, _ = rm.check(signal)
        assert passed


class TestPortfolio:
    def test_equity_tracking(self):
        from pdx_arb.portfolio import PortfolioTracker
        tracker = PortfolioTracker(initial_capital=10_000)
        assert tracker.equity == 10_000

        signal = _signal()
        trade = ArbTrade(
            trade_id="t1",
            signal=signal,
            leg_buy=LegOrder(Venue.POLYMARKET, "cond", Side.BUY_YES, 500, 0.45,
                             OrderStatus.FILLED, 0.45, 1000, 3.6),
            leg_sell=LegOrder(Venue.PREDICTX, "0", Side.BUY_NO, 500, 0.45,
                              OrderStatus.FILLED, 0.45, 1000, 1.35),
            status="filled",
            pnl_net=50.0,
        )
        tracker.record_open(trade)
        tracker.record_close(trade)
        assert tracker.equity == pytest.approx(10_050.0)


class TestExecutor:
    def test_paper_fill(self):
        from pdx_arb.execution.executor import ArbExecutor
        config = _config()
        executor = ArbExecutor(config, dry_run=True)
        signal = _signal()
        trade = executor.execute(signal)
        assert trade.status == "filled"
        assert trade.leg_buy.status == OrderStatus.FILLED
        assert trade.leg_sell.status == OrderStatus.FILLED
        assert trade.leg_buy.fee_paid > 0


def _signal(net_spread=200, size=1000) -> ArbSignal:
    pair = _pair()
    prices = _prices(0.45, 0.55)
    return ArbSignal(
        pair=pair,
        prices=prices,
        direction="yes_poly_no_pdx",
        buy_venue=Venue.POLYMARKET,
        sell_venue=Venue.PREDICTX,
        buy_side=Side.BUY_YES,
        gross_spread_bps=net_spread + 50,
        net_spread_bps=net_spread,
        fee_cost_bps=50,
        suggested_size_usd=size,
        edge=net_spread / 10_000,
        confidence=0.7,
    )

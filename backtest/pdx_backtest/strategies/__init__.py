"""Strategy implementations for the PDX backtester."""

from pdx_backtest.strategies.base import Strategy, StrategyResult, Trade
from pdx_backtest.strategies.cross_asset import CrossAssetArb
from pdx_backtest.strategies.cross_platform import CrossPlatformArb
from pdx_backtest.strategies.longshot_bias import LongshotBiasExploiter
from pdx_backtest.strategies.lvr_arb import LVRArb
from pdx_backtest.strategies.market_making import BayesianMarketMaker
from pdx_backtest.strategies.negrisk import NegRiskRebalancer
from pdx_backtest.strategies.single_binary import SingleBinaryRebalancer
from pdx_backtest.strategies.stat_arb import StatisticalArb
from pdx_backtest.strategies.time_arb import TimeArb
from pdx_backtest.strategies.vol_event import VolatilityEventStrategy

__all__ = [
    "Strategy",
    "StrategyResult",
    "Trade",
    "BayesianMarketMaker",
    "CrossAssetArb",
    "CrossPlatformArb",
    "LongshotBiasExploiter",
    "LVRArb",
    "NegRiskRebalancer",
    "SingleBinaryRebalancer",
    "StatisticalArb",
    "TimeArb",
    "VolatilityEventStrategy",
]

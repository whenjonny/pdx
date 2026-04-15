"""PDX backtest package.

Event-driven backtester for prediction-market arbitrage and
market-making strategies.  Mirrors PDXMarket.sol's CPMM math so
results are directly transferable to the on-chain contract.
"""

from pdx_backtest.amm import CPMM, FeeSchedule
from pdx_backtest.data import (
    MarketPath,
    MultiOutcomeSnapshot,
    generate_binary_path,
    generate_multi_outcome_paths,
    generate_negrisk_scenario,
)
from pdx_backtest.engine import BacktestEngine, BacktestResult
from pdx_backtest.metrics import PerformanceMetrics, compute_metrics

__all__ = [
    "CPMM",
    "FeeSchedule",
    "MarketPath",
    "MultiOutcomeSnapshot",
    "generate_binary_path",
    "generate_multi_outcome_paths",
    "generate_negrisk_scenario",
    "BacktestEngine",
    "BacktestResult",
    "PerformanceMetrics",
    "compute_metrics",
]

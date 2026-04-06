"""PDX Prediction Market Agent SDK."""

from pdx_sdk.types import (
    Market,
    Evidence,
    TradeResult,
    Prediction,
    MonteCarloResult,
)

__all__ = [
    "PDXClient",
    "Market",
    "Evidence",
    "TradeResult",
    "Prediction",
    "MonteCarloResult",
]

__version__ = "0.1.0"


def __getattr__(name: str):
    """Lazy-load PDXClient so the package can be imported without web3/requests
    installed (useful for lightweight usage of types/compute/evidence)."""
    if name == "PDXClient":
        from pdx_sdk.client import PDXClient

        return PDXClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

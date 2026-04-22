"""Price sources. yfinance is lazy-imported so tests/backtest work offline
with StubPriceSource."""
from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import date, timedelta


class PriceSource(ABC):
    @abstractmethod
    def close_on(self, ticker: str, d: date) -> float | None:
        """Return the official close price on `d`, or None if unavailable.
        Implementations may look back a few business days for holidays."""
        ...


class StubPriceSource(PriceSource):
    """Deterministic synthetic prices. Generates a sinusoidal + trend per ticker
    so backtests produce non-trivial P&L without network access."""

    def __init__(self, seed_prices: dict[str, float] | None = None, daily_drift_pct: float = 0.001):
        self.seed = seed_prices or {}
        self.drift = daily_drift_pct
        self._epoch = date(2024, 1, 1)

    def close_on(self, ticker: str, d: date) -> float | None:
        base = self.seed.get(ticker, 100.0)
        days = (d - self._epoch).days
        import math
        cycle = math.sin(days / 30.0) * 0.05  # +/- 5%
        drift = (1.0 + self.drift) ** days
        ticker_offset = sum(ord(c) for c in ticker) % 17
        return round(base * drift * (1 + cycle) * (1 + ticker_offset * 0.001), 2)


class YFinancePriceSource(PriceSource):
    """Real historical close from Yahoo Finance. Requires `yfinance`."""

    def __init__(self):
        try:
            import yfinance  # noqa: F401
        except ImportError as e:
            raise ImportError("YFinancePriceSource requires yfinance. pip install yfinance") from e
        self._cache: dict[tuple[str, str], float] = {}

    def close_on(self, ticker: str, d: date) -> float | None:
        import yfinance as yf
        key = (ticker, d.isoformat())
        if key in self._cache:
            return self._cache[key]
        # Look back up to 5 business days for holidays/weekends
        end = d + timedelta(days=1)
        start = d - timedelta(days=7)
        try:
            df = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
            if df.empty:
                return None
            price = float(df["Close"].iloc[-1])
            self._cache[key] = price
            return price
        except Exception:
            return None

"""Paper trader. Two modes:

  - SimulatedPaperTrader: pure in-memory simulation (for backtest + tests)
  - AlpacaPaperTrader: wraps alpaca-py (lazy import). Requires
    ALPACA_API_KEY and ALPACA_SECRET in env.

Both honor playbook risk_gates and return the same OrderReport shape.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from trumptrade.types import BasketLeg
from trumptrade.execution.position_sizer import size_basket, SizingResult


@dataclass
class Order:
    ticker: str
    side: Literal["buy", "sell_short", "close"]
    shares: int
    limit_price: float | None = None
    notional: float = 0.0
    note: str = ""


@dataclass
class OrderReport:
    emitted_at: datetime
    account_value: float
    orders: list[Order] = field(default_factory=list)
    skipped: list[SizingResult] = field(default_factory=list)
    dry_run: bool = True

    def summary(self) -> str:
        lines = [f"[OrderReport {self.emitted_at.isoformat()}] account=${self.account_value:,.2f} dry_run={self.dry_run}"]
        for o in self.orders:
            lines.append(f"  {o.side:10s} {o.shares:>5d}  {o.ticker:5s} @ {o.limit_price or 'mkt':<8} notional=${o.notional:,.2f}  {o.note}")
        for s in self.skipped:
            lines.append(f"  SKIP        -  {s.ticker:5s}  ({s.capped_by})")
        return "\n".join(lines)


class SimulatedPaperTrader:
    """Reference implementation. Logs orders; never hits a broker."""

    def __init__(self, playbook_risk: dict):
        self.playbook_risk = playbook_risk

    def submit_basket(
        self,
        basket: list[BasketLeg],
        prices: dict[str, float],
        account_value: float,
        available_cash: float,
    ) -> OrderReport:
        sized = size_basket(basket, prices, account_value, available_cash, self.playbook_risk)
        report = OrderReport(emitted_at=datetime.now(timezone.utc), account_value=account_value, dry_run=True)
        for leg, result in zip(basket, sized):
            if result.shares <= 0:
                report.skipped.append(result)
                continue
            side = "buy" if leg.side == "long" else "sell_short"
            report.orders.append(
                Order(
                    ticker=leg.ticker,
                    side=side,
                    shares=result.shares,
                    limit_price=prices[leg.ticker],
                    notional=result.notional,
                    note=leg.thesis,
                )
            )
        return report


class AlpacaPaperTrader:
    """Wraps alpaca-py. Lazy import so the package works without alpaca installed."""

    def __init__(self, playbook_risk: dict, api_key: str, api_secret: str):
        try:
            from alpaca.trading.client import TradingClient
        except ImportError as e:
            raise ImportError(
                "AlpacaPaperTrader requires alpaca-py. Install with: pip install alpaca-py"
            ) from e
        self.playbook_risk = playbook_risk
        self.client = TradingClient(api_key, api_secret, paper=True)

    def submit_basket(
        self,
        basket: list[BasketLeg],
        prices: dict[str, float],
        account_value: float | None = None,
        available_cash: float | None = None,
    ) -> OrderReport:
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        account = self.client.get_account()
        account_value = account_value or float(account.portfolio_value)
        available_cash = available_cash or float(account.cash)

        sized = size_basket(basket, prices, account_value, available_cash, self.playbook_risk)
        report = OrderReport(
            emitted_at=datetime.now(timezone.utc),
            account_value=account_value,
            dry_run=False,
        )

        for leg, result in zip(basket, sized):
            if result.shares <= 0:
                report.skipped.append(result)
                continue
            side = OrderSide.BUY if leg.side == "long" else OrderSide.SELL
            req = MarketOrderRequest(
                symbol=leg.ticker,
                qty=result.shares,
                side=side,
                time_in_force=TimeInForce.DAY,
            )
            self.client.submit_order(req)
            report.orders.append(
                Order(
                    ticker=leg.ticker,
                    side="buy" if leg.side == "long" else "sell_short",
                    shares=result.shares,
                    limit_price=prices[leg.ticker],
                    notional=result.notional,
                    note=leg.thesis,
                )
            )
        return report

"""Backtest harness: given an alerts.jsonl and a price source, simulate
paper trades with hold_days exit and compute basic P&L stats.

Simplifications:
- Open at alert emission date's close price (no intraday)
- Close after `hold_days` trading days (not calendar)  — approximate with date skip
- No slippage / commissions
- Walk-back closes use the walk-back timestamp close price
- Shorts pay no borrow cost in the sim
"""
from __future__ import annotations
import json
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from trumptrade.types import Alert
from trumptrade.backtest.prices import PriceSource
from trumptrade.execution.position_sizer import size_basket
from trumptrade.execution.walkback import WalkbackDetector


@dataclass
class Trade:
    ticker: str
    side: str               # "long" | "short"
    open_date: date
    close_date: date | None
    open_price: float
    close_price: float | None
    shares: int
    pnl: float = 0.0
    close_reason: str = ""  # "hold_expired" | "walk_back"

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "side": self.side,
            "open_date": self.open_date.isoformat(),
            "close_date": self.close_date.isoformat() if self.close_date else None,
            "open_price": self.open_price,
            "close_price": self.close_price,
            "shares": self.shares,
            "pnl": round(self.pnl, 2),
            "close_reason": self.close_reason,
        }


@dataclass
class BacktestResult:
    initial_capital: float
    final_equity: float
    trades: list[Trade] = field(default_factory=list)

    @property
    def total_pnl(self) -> float:
        return sum(t.pnl for t in self.trades)

    @property
    def n_trades(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float:
        closed = [t for t in self.trades if t.close_date is not None]
        if not closed:
            return 0.0
        return sum(1 for t in closed if t.pnl > 0) / len(closed)

    @property
    def total_return_pct(self) -> float:
        return (self.final_equity - self.initial_capital) / self.initial_capital

    def summary(self) -> str:
        lines = [
            f"BACKTEST RESULT",
            f"  capital start : ${self.initial_capital:,.2f}",
            f"  capital end   : ${self.final_equity:,.2f}",
            f"  total P&L     : ${self.total_pnl:,.2f}  ({self.total_return_pct:+.2%})",
            f"  trades        : {self.n_trades}",
            f"  win rate      : {self.win_rate:.1%}",
        ]
        if self.trades:
            wins = [t.pnl for t in self.trades if t.pnl > 0]
            losses = [t.pnl for t in self.trades if t.pnl <= 0]
            if wins:
                lines.append(f"  avg win       : ${sum(wins)/len(wins):,.2f}")
            if losses:
                lines.append(f"  avg loss      : ${sum(losses)/len(losses):,.2f}")
        return "\n".join(lines)


class Backtester:
    def __init__(
        self,
        price_source: PriceSource,
        playbook: dict,
        initial_capital: float = 100_000.0,
        hold_days: int = 5,
        use_walkback: bool = True,
    ):
        self.prices = price_source
        self.playbook = playbook
        self.initial_capital = initial_capital
        self.hold_days = hold_days
        self.use_walkback = use_walkback

    def run(self, alerts_path: Path) -> BacktestResult:
        alerts = self._load(alerts_path)
        alerts.sort(key=lambda a: a.emitted_at)

        result = BacktestResult(
            initial_capital=self.initial_capital,
            final_equity=self.initial_capital,
        )
        equity = self.initial_capital
        open_trades: list[Trade] = []
        detector = WalkbackDetector() if self.use_walkback else None

        for alert in alerts:
            # Open at signal post date for realistic backtest (not the time we ran the pipeline)
            open_date = alert.signal.timestamp.date()

            # 1. Close any trades whose hold_days have elapsed
            still_open: list[Trade] = []
            for t in open_trades:
                days_held = (open_date - t.open_date).days
                if days_held >= self.hold_days:
                    self._close_trade(t, open_date, "hold_expired")
                    result.trades.append(t)
                    equity += t.pnl
                else:
                    still_open.append(t)
            open_trades = still_open

            # 2. Walk-back: close prior opposite-sentiment same-category trades
            if detector:
                closures = detector.feed(alert)
                if closures:
                    cats_to_close = {prior.classification.category for prior, _ in closures}
                    still_open2: list[Trade] = []
                    for t in open_trades:
                        if t.ticker in self._tickers_for_categories(cats_to_close):
                            self._close_trade(t, open_date, "walk_back")
                            result.trades.append(t)
                            equity += t.pnl
                        else:
                            still_open2.append(t)
                    open_trades = still_open2

            # 3. Size and open new positions
            prices_today = {
                leg.ticker: self.prices.close_on(leg.ticker, open_date)
                for leg in alert.basket
            }
            prices_today = {k: v for k, v in prices_today.items() if v is not None}
            sized = size_basket(
                alert.basket, prices_today, equity, equity,
                self.playbook.get("risk_gates", {}),
            )
            for leg, s in zip(alert.basket, sized):
                if s.shares <= 0 or leg.ticker not in prices_today:
                    continue
                open_trades.append(
                    Trade(
                        ticker=leg.ticker,
                        side=leg.side,
                        open_date=open_date,
                        close_date=None,
                        open_price=prices_today[leg.ticker],
                        close_price=None,
                        shares=s.shares,
                    )
                )

        # Final close: mark remaining open at last signal date
        if alerts and open_trades:
            final_date = alerts[-1].signal.timestamp.date() + timedelta(days=self.hold_days)
            for t in open_trades:
                self._close_trade(t, final_date, "hold_expired_eos")
                result.trades.append(t)
                equity += t.pnl

        result.final_equity = equity
        return result

    def _close_trade(self, t: Trade, d: date, reason: str) -> None:
        price = self.prices.close_on(t.ticker, d) or t.open_price
        t.close_date = d
        t.close_price = price
        t.close_reason = reason
        if t.side == "long":
            t.pnl = (price - t.open_price) * t.shares
        else:
            t.pnl = (t.open_price - price) * t.shares

    def _tickers_for_categories(self, categories: set[str]) -> set[str]:
        out: set[str] = set()
        cats = self.playbook.get("categories", {})
        for cat_name in categories:
            cfg = cats.get(cat_name, {})
            for key in ("hawkish_long", "hawkish_short", "dovish_long", "dovish_short"):
                for leg in cfg.get(key, []) or []:
                    out.add(leg["ticker"])
        return out

    @staticmethod
    def _load(path: Path) -> list[Alert]:
        alerts: list[Alert] = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    alerts.append(Alert(**json.loads(line)))
        return alerts

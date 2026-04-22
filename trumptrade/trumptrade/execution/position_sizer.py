"""Risk-based position sizing. Pure function — no broker dependency.

Formula:
    risk_dollars = account_value * risk_per_trade_pct
    shares_raw   = risk_dollars / (entry_price * stop_loss_pct)
    notional_raw = shares_raw * entry_price

Caps applied in order:
    1. max_single_ticker_notional_pct of account
    2. available cash

Returns 0 shares if the math produces less than 1 share or if caps eliminate it.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class SizingResult:
    ticker: str
    shares: int
    notional: float
    risk_dollars: float
    capped_by: str | None  # "single_ticker_cap" | "cash" | None


def size_position(
    ticker: str,
    side: str,
    entry_price: float,
    account_value: float,
    available_cash: float,
    risk_per_trade_pct: float = 0.01,
    stop_loss_pct: float = 0.08,
    max_single_ticker_notional_pct: float = 0.03,
    conviction: float = 1.0,
) -> SizingResult:
    if entry_price <= 0 or account_value <= 0:
        return SizingResult(ticker, 0, 0.0, 0.0, None)

    risk_dollars = account_value * risk_per_trade_pct * conviction
    shares_by_risk = risk_dollars / (entry_price * stop_loss_pct)

    capped_by: str | None = None
    notional_cap = account_value * max_single_ticker_notional_pct
    shares_by_notional_cap = notional_cap / entry_price
    if shares_by_notional_cap < shares_by_risk:
        shares_by_risk = shares_by_notional_cap
        capped_by = "single_ticker_cap"

    # Shorts use margin — skip the cash cap for shorts
    if side == "long":
        shares_by_cash = available_cash / entry_price
        if shares_by_cash < shares_by_risk:
            shares_by_risk = shares_by_cash
            capped_by = "cash"

    shares = max(0, int(shares_by_risk))
    notional = round(shares * entry_price, 2)
    return SizingResult(ticker, shares, notional, round(risk_dollars, 2), capped_by)


def size_basket(
    basket,  # list[BasketLeg]
    prices: dict[str, float],
    account_value: float,
    available_cash: float,
    playbook_risk: dict,
) -> list[SizingResult]:
    results: list[SizingResult] = []
    max_basket = playbook_risk.get("max_basket_notional_pct", 0.10) * account_value
    max_single = playbook_risk.get("max_single_ticker_notional_pct", 0.03)
    stop_pct = playbook_risk.get("mandatory_stop_loss_pct", 0.08)

    cash_remaining = available_cash
    basket_notional = 0.0
    for leg in basket:
        price = prices.get(leg.ticker)
        if price is None or price <= 0:
            results.append(SizingResult(leg.ticker, 0, 0.0, 0.0, "no_price"))
            continue
        remaining_basket = max(0.0, max_basket - basket_notional)
        if remaining_basket <= 0:
            results.append(SizingResult(leg.ticker, 0, 0.0, 0.0, "basket_cap"))
            continue

        r = size_position(
            leg.ticker,
            leg.side,
            price,
            account_value,
            cash_remaining,
            risk_per_trade_pct=0.01,
            stop_loss_pct=stop_pct,
            max_single_ticker_notional_pct=max_single,
            conviction=leg.weight,
        )
        # Honor basket-level cap
        if r.notional > remaining_basket:
            shares_capped = int(remaining_basket / price)
            r = SizingResult(
                r.ticker, shares_capped, round(shares_capped * price, 2),
                r.risk_dollars, "basket_cap",
            )

        if leg.side == "long":
            cash_remaining = max(0.0, cash_remaining - r.notional)
        basket_notional += r.notional
        results.append(r)

    return results

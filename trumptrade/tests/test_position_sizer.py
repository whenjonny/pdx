from trumptrade.execution import size_position, size_basket
from trumptrade.types import BasketLeg


def test_risk_based_sizing():
    # $100k account, 1% risk, 8% stop, $50 stock
    # risk = $1000; per-share-risk = $50 * 0.08 = $4; shares = 250
    # single-ticker cap 3% = $3000; $3000/$50 = 60 shares -> capped
    r = size_position("AAPL", "long", entry_price=50.0, account_value=100_000,
                      available_cash=100_000, risk_per_trade_pct=0.01, stop_loss_pct=0.08,
                      max_single_ticker_notional_pct=0.03, conviction=1.0)
    assert r.shares == 60
    assert r.capped_by == "single_ticker_cap"


def test_sizing_scales_with_conviction():
    r_full = size_position("X", "long", 100.0, 100_000, 100_000, conviction=1.0)
    r_half = size_position("X", "long", 100.0, 100_000, 100_000, conviction=0.5)
    # Half conviction -> half the risk_dollars -> roughly half the sizing (before cap)
    assert r_half.shares <= r_full.shares


def test_basket_basket_cap_enforced():
    legs = [BasketLeg(ticker=f"T{i}", side="long", weight=1.0, thesis="t") for i in range(20)]
    prices = {l.ticker: 50.0 for l in legs}
    playbook_risk = {
        "max_basket_notional_pct": 0.05,     # $5k total
        "max_single_ticker_notional_pct": 0.03,
        "mandatory_stop_loss_pct": 0.08,
    }
    results = size_basket(legs, prices, 100_000, 100_000, playbook_risk)
    total_notional = sum(r.notional for r in results)
    assert total_notional <= 5_000 + 50  # small rounding tolerance
    # At least one leg should be capped
    assert any(r.capped_by == "basket_cap" for r in results)


def test_no_price_returns_zero_shares():
    legs = [BasketLeg(ticker="UNK", side="long", weight=1.0, thesis="t")]
    results = size_basket(legs, {}, 100_000, 100_000, {})
    assert results[0].shares == 0
    assert results[0].capped_by == "no_price"

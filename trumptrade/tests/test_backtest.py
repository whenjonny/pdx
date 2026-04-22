import json
from datetime import datetime, timezone, date
from pathlib import Path
from trumptrade.backtest import Backtester, StubPriceSource
from trumptrade.types import Alert, Signal, Classification, BasketLeg


def _make_alerts_file(tmp_path: Path) -> Path:
    alerts = [
        Alert(
            signal=Signal(id="a1", author="x", timestamp=datetime(2026, 1, 5, tzinfo=timezone.utc),
                          text="tariff", source="t"),
            classification=Classification(category="tariff_china", sentiment="hawkish",
                                          follow_through=0.7, rationale="r", confidence=0.9,
                                          original_excerpt="..."),
            basket=[
                BasketLeg(ticker="NUE", side="long", weight=0.5, thesis="t"),
                BasketLeg(ticker="FXI", side="short", weight=0.5, thesis="t"),
            ],
            effective_confidence=0.63,
            emitted_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
        ),
    ]
    p = tmp_path / "alerts.jsonl"
    p.write_text("\n".join(a.model_dump_json() for a in alerts) + "\n")
    return p


def test_backtest_runs_end_to_end(tmp_path):
    alerts_path = _make_alerts_file(tmp_path)
    playbook = {
        "categories": {"tariff_china": {"hawkish_long": [{"ticker": "NUE", "weight": 0.5, "thesis": "t"}]}},
        "risk_gates": {"max_basket_notional_pct": 0.10, "max_single_ticker_notional_pct": 0.03,
                       "mandatory_stop_loss_pct": 0.08},
    }
    bt = Backtester(StubPriceSource(seed_prices={"NUE": 120.0, "FXI": 25.0}),
                    playbook, initial_capital=100_000, hold_days=3)
    result = bt.run(alerts_path)
    assert result.n_trades >= 1
    # Every trade should be closed since alerts are in the past
    for t in result.trades:
        assert t.close_date is not None
        assert t.close_price is not None
    assert isinstance(result.total_pnl, float)


def test_stub_price_source_deterministic():
    src = StubPriceSource(seed_prices={"AAPL": 200.0})
    p1 = src.close_on("AAPL", date(2026, 1, 15))
    p2 = src.close_on("AAPL", date(2026, 1, 15))
    assert p1 == p2
    assert p1 > 0

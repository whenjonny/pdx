from datetime import datetime, timezone, timedelta
from trumptrade.execution import WalkbackDetector
from trumptrade.types import Alert, Signal, Classification, BasketLeg


def _alert(ts, category, sentiment, basket_side="long"):
    return Alert(
        signal=Signal(id=f"s-{ts}", author="x", timestamp=ts, text="...", source="t"),
        classification=Classification(
            category=category, sentiment=sentiment, follow_through=0.7,
            rationale="t", confidence=0.9, original_excerpt="...",
        ),
        basket=[BasketLeg(ticker="NUE", side=basket_side, weight=0.5, thesis="t")],
        effective_confidence=0.63,
        emitted_at=ts,
    )


def test_walkback_detects_opposite_sentiment_within_window():
    det = WalkbackDetector(window_hours=48)
    t0 = datetime.now(timezone.utc)
    # T=0: hawkish tariff -> longs
    det.feed(_alert(t0, "tariff_china", "hawkish", "long"))
    # T=+24h: dovish tariff -> should close
    closures = det.feed(_alert(t0 + timedelta(hours=24), "tariff_china", "dovish", "long"))
    assert len(closures) == 1
    _, close_legs = closures[0]
    assert close_legs[0].side == "short"  # long inverted
    assert close_legs[0].ticker == "NUE"


def test_walkback_outside_window_ignored():
    det = WalkbackDetector(window_hours=48)
    t0 = datetime.now(timezone.utc)
    det.feed(_alert(t0, "tariff_china", "hawkish"))
    closures = det.feed(_alert(t0 + timedelta(hours=72), "tariff_china", "dovish"))
    assert closures == []


def test_walkback_different_category_ignored():
    det = WalkbackDetector(window_hours=48)
    t0 = datetime.now(timezone.utc)
    det.feed(_alert(t0, "tariff_china", "hawkish"))
    closures = det.feed(_alert(t0 + timedelta(hours=1), "energy_oil_gas", "dovish"))
    assert closures == []

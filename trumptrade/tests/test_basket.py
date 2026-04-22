from trumptrade.execution.basket import expand_basket
from trumptrade.types import Classification

PLAYBOOK = {
    "categories": {
        "tariff_china": {
            "hawkish_long": [
                {"ticker": "NUE", "weight": 0.9, "thesis": "steel"},
            ],
            "hawkish_short": [
                {"ticker": "FXI", "weight": 0.85, "thesis": "china etf"},
            ],
            "dovish_long": [
                {"ticker": "KWEB", "weight": 0.8, "thesis": "china unwind"},
            ],
        }
    }
}


def test_hawkish_basket_scales_by_confidence():
    c = Classification(
        category="tariff_china",
        sentiment="hawkish",
        follow_through=0.5,
        rationale="test",
        confidence=0.8,
        original_excerpt="...",
    )
    legs = expand_basket(c, PLAYBOOK)
    assert len(legs) == 2
    nue = next(l for l in legs if l.ticker == "NUE")
    # 0.9 * 0.8 * 0.5 = 0.36
    assert nue.side == "long"
    assert abs(nue.weight - 0.36) < 1e-6


def test_unknown_category_empty():
    c = Classification(
        category="unknown",
        sentiment="neutral",
        follow_through=0.0,
        rationale="off-topic",
        confidence=0.0,
        original_excerpt="...",
    )
    assert expand_basket(c, PLAYBOOK) == []


def test_dovish_falls_through_to_dovish_long():
    c = Classification(
        category="tariff_china",
        sentiment="dovish",
        follow_through=1.0,
        rationale="test",
        confidence=1.0,
        original_excerpt="...",
    )
    legs = expand_basket(c, PLAYBOOK)
    assert len(legs) == 1
    assert legs[0].ticker == "KWEB"
    assert legs[0].side == "long"

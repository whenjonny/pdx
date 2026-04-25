"""Unit tests for matcher + detector + scanner using fake clients."""
from datetime import datetime, timezone, timedelta
from trumptrade.markets.base import PredictionMarketClient
from trumptrade.markets.types import MarketRef, Quote
from trumptrade.arb.matcher import match_rules
from trumptrade.arb.detector import detect
from trumptrade.arb.scanner import ArbScanner


def _ref(venue, mid, title, closes=None):
    return MarketRef(
        venue=venue, market_id=mid, title=title,
        closes_at=closes or datetime(2026, 6, 1, tzinfo=timezone.utc),
        url=f"https://{venue}.com/{mid}",
    )


def _quote(ref, yes_bid, yes_ask, no_bid, no_ask):
    return Quote(
        market=ref, yes_bid=yes_bid, yes_ask=yes_ask, no_bid=no_bid, no_ask=no_ask,
        fetched_at=datetime.now(timezone.utc),
    )


def test_match_rules_finds_token_overlap():
    poly = [_ref("polymarket", "p1", "Will Trump impose new tariffs on China by July 2026?")]
    kalshi = [
        _ref("kalshi", "k1", "Trump China tariff announcement before July 2026"),
        _ref("kalshi", "k2", "Will the Fed cut rates in June?"),
    ]
    matches = match_rules(poly, kalshi, min_similarity=0.2)
    assert len(matches) >= 1
    assert matches[0].kalshi.market_id == "k1"
    # Fed-cut market should be filtered out
    assert all(m.kalshi.market_id != "k2" for m in matches)


def test_detect_finds_arb_when_round_trip_below_one():
    p = _ref("polymarket", "p1", "Will Trump impose new China tariffs by July?")
    k = _ref("kalshi", "k1", "Trump impose China tariffs by July?")
    matches = match_rules([p], [k], min_similarity=0.1)
    assert matches
    # Polymarket YES cheap (0.40), Kalshi NO cheap (0.45) -> total 0.85, lock 0.15
    pq = _quote(p, 0.39, 0.40, 0.59, 0.61)
    kq = _quote(k, 0.50, 0.55, 0.43, 0.45)
    opp = detect(matches[0], pq, kq, fee_per_dollar=0.0, min_edge=0.01)
    assert opp is not None
    assert opp.cost_per_pair == 0.85
    assert abs(opp.profit_per_pair - 0.15) < 1e-6
    assert opp.long_yes.venue == "polymarket"
    assert opp.long_no.venue == "kalshi"


def test_detect_returns_none_when_no_arb():
    p = _ref("polymarket", "p1", "Will Trump tariff China")
    k = _ref("kalshi", "k1", "Will Trump tariff China")
    matches = match_rules([p], [k], min_similarity=0.0)
    assert matches  # sanity
    pq = _quote(p, 0.55, 0.58, 0.41, 0.45)
    kq = _quote(k, 0.55, 0.58, 0.41, 0.45)  # 0.58 + 0.45 = 1.03 -> no arb
    assert detect(matches[0], pq, kq, min_edge=0.01) is None


# ---------- Fake clients for ArbScanner -----------------------------------

class _FakePoly(PredictionMarketClient):
    venue = "polymarket"

    def __init__(self, markets, quotes):
        self._markets = markets
        self._quotes = quotes

    def search_markets(self, query, limit=20, only_active=True):
        return self._markets

    def get_quote(self, market_id):
        return self._quotes.get(market_id)


class _FakeKalshi(_FakePoly):
    venue = "kalshi"


def test_scanner_end_to_end():
    p_ref = _ref("polymarket", "p1", "Will Trump impose new China tariff by July 2026?")
    k_ref = _ref("kalshi", "k1", "Trump impose China tariff before July 2026")
    poly = _FakePoly([p_ref], {"p1": _quote(p_ref, 0.39, 0.40, 0.59, 0.61)})
    kalshi = _FakeKalshi([k_ref], {"k1": _quote(k_ref, 0.50, 0.55, 0.43, 0.45)})
    scanner = ArbScanner(poly, kalshi, use_llm_matcher=False, min_edge=0.01)
    report = scanner.scan("tariff")
    assert len(report.candidates) >= 1
    assert len(report.opportunities) == 1
    o = report.opportunities[0]
    assert o.long_yes.venue == "polymarket"
    assert o.long_no.venue == "kalshi"

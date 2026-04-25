from datetime import datetime, timezone
from trumptrade.signals.market_signal import PriceJumpSource, ArbOpportunitySource


# ---- PriceJumpSource ----------------------------------------------------

class _StubQuote:
    def __init__(self, mid):
        self._mid = mid
        from types import SimpleNamespace
        self.market = SimpleNamespace(url="http://x", title="X")

    def yes_mid(self):
        return self._mid


class _StubClient:
    def __init__(self):
        self.next_mid = 0.50

    def get_quote(self, market_id):
        return _StubQuote(self.next_mid)


def test_price_jump_no_signal_first_poll():
    c = _StubClient()
    src = PriceJumpSource({"v": c}, [("v", "m1")], threshold_pct=0.05)
    sigs = src.poll()
    assert sigs == []   # first poll seeds last_mid, no delta yet


def test_price_jump_emits_when_above_threshold():
    c = _StubClient()
    src = PriceJumpSource({"v": c}, [("v", "m1")], threshold_pct=0.05)
    src.poll()                      # seed
    c.next_mid = 0.60               # +20% jump
    sigs = src.poll()
    assert len(sigs) == 1
    assert "Price jump" in sigs[0].text
    assert sigs[0].metadata["prior_mid"] == 0.50
    assert sigs[0].metadata["current_mid"] == 0.60


def test_price_jump_quiet_when_below_threshold():
    c = _StubClient()
    src = PriceJumpSource({"v": c}, [("v", "m1")], threshold_pct=0.10)
    src.poll()
    c.next_mid = 0.52   # +4%, below 10%
    assert src.poll() == []


def test_price_jump_unknown_venue_is_silent():
    src = PriceJumpSource({}, [("missing", "m1")], threshold_pct=0.05)
    assert src.poll() == []


# ---- ArbOpportunitySource ------------------------------------------------

class _Opp:
    def __init__(self, edge=0.05, cost=0.93):
        from types import SimpleNamespace
        self.long_yes = SimpleNamespace(venue="poly", market_id="p1")
        self.long_no = SimpleNamespace(venue="kalshi", market_id="k1")
        self.cost_per_pair = cost
        self.profit_per_pair = edge


class _Report:
    def __init__(self, opps):
        self.opportunities = opps


class _StubScanner:
    def __init__(self, opps):
        self.opps = opps

    def scan(self, query, per_venue_limit=20):
        return _Report(self.opps)


def test_arb_source_emits_per_unique_opportunity():
    s = ArbOpportunitySource(_StubScanner([_Opp(0.05, 0.93)]),
                             ["tariff"], min_edge=0.01)
    sigs = s.poll()
    assert len(sigs) == 1
    assert sigs[0].source == "market_signal:arb"
    # Same opportunity again -> deduped
    assert s.poll() == []


def test_arb_source_filters_by_min_edge():
    s = ArbOpportunitySource(_StubScanner([_Opp(0.001, 0.99)]),
                             ["x"], min_edge=0.01)
    assert s.poll() == []

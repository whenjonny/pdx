from datetime import timedelta
from trumptrade.markets import MockMarketClient


def test_search_returns_n_markets():
    c = MockMarketClient(per_query_markets=3)
    refs = c.search_markets("trump tariff", limit=10)
    assert len(refs) == 3
    assert all("trump-tariff" in r.market_id for r in refs)


def test_quote_yes_no_sum_to_one_minus_spread():
    c = MockMarketClient(base_yes_price=0.45)
    q = c.get_quote("any-market")
    yes_mid = (q.yes_bid + q.yes_ask) / 2
    no_mid = (q.no_bid + q.no_ask) / 2
    assert abs(yes_mid + no_mid - 1.0) < 0.001


def test_drift_advances_mid():
    c = MockMarketClient(base_yes_price=0.50, price_drift_per_call=0.05,
                         random_walk_amplitude=0.0)
    q1 = c.get_quote("m")
    q2 = c.get_quote("m")
    q3 = c.get_quote("m")
    # call counter increments each call -> mid drifts up
    m1, m2, m3 = q1.yes_bid + q1.yes_ask, q2.yes_bid + q2.yes_ask, q3.yes_bid + q3.yes_ask
    assert m3 > m2 > m1

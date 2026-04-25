"""Smoke-tests for Polymarket / Kalshi clients. They should fail-soft when
network is unreachable and produce no exceptions."""
from trumptrade.markets import PolymarketClient, KalshiClient


def test_polymarket_search_unreachable_returns_empty():
    c = PolymarketClient(http_timeout=0.5)
    # Override the module constant to a clearly-unreachable host
    import trumptrade.markets.polymarket as poly_mod
    orig_g = poly_mod._GAMMA
    orig_c = poly_mod._CLOB
    poly_mod._GAMMA = "http://127.0.0.1:1"
    poly_mod._CLOB = "http://127.0.0.1:1"
    try:
        assert c.search_markets("anything") == []
        assert c.get_quote("any") is None
    finally:
        poly_mod._GAMMA = orig_g
        poly_mod._CLOB = orig_c


def test_kalshi_search_unreachable_returns_empty():
    c = KalshiClient(host="http://127.0.0.1:1", http_timeout=0.5)
    assert c.search_markets("anything") == []
    assert c.get_quote("any") is None


def test_kalshi_login_returns_none_without_creds():
    c = KalshiClient(host="http://127.0.0.1:1", http_timeout=0.5,
                     email=None, password=None)
    assert c.login() is None

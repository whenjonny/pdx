import pytest
from trumptrade.markets import VenueRegistry, VenueMetadata, PolymarketClient, KalshiClient


def _meta(name="poly", vc="onchain_evm", topics=("crypto_friendly",)):
    return VenueMetadata(
        name=name, venue_class=vc, base_currency="USDC",
        chain="polygon", topics=list(topics),
    )


def test_register_and_get():
    r = VenueRegistry()
    r.register(PolymarketClient(), _meta())
    assert "poly" in r
    c, m = r.get("poly")
    assert isinstance(c, PolymarketClient)


def test_query_filters():
    r = VenueRegistry()
    r.register(PolymarketClient(), _meta(name="poly", topics=("crypto_friendly",)))
    r.register(KalshiClient(), VenueMetadata(
        name="kalshi", venue_class="regulated_us", base_currency="USD",
        topics=["macro"]))
    res = r.query(venue_class="regulated_us")
    assert {m.name for _, m in res} == {"kalshi"}
    res = r.query(topic="crypto_friendly")
    assert {m.name for _, m in res} == {"poly"}


def test_double_register_raises():
    r = VenueRegistry()
    r.register(PolymarketClient(), _meta())
    with pytest.raises(ValueError):
        r.register(PolymarketClient(), _meta())

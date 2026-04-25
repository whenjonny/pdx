from trumptrade.markets.predict_fun import PredictFunClient, _market_to_ref, _f


def test_constructor_defaults_to_mainnet():
    c = PredictFunClient()
    assert c.host.endswith("predict.fun")
    assert not c.testnet


def test_testnet_constructor():
    c = PredictFunClient(testnet=True)
    assert "testnet" in c.host


def test_market_to_ref_picks_question_or_title():
    m = {"id": "x1", "question": "Will Trump tariff?", "slug": "trump-tariff"}
    ref = _market_to_ref(m)
    assert ref.market_id == "x1"
    assert ref.title == "Will Trump tariff?"
    assert ref.url and "predict.fun" in ref.url
    assert ref.metadata["chain"] == "bnb"


def test_price_normalizer_handles_cents_and_unit():
    assert _f(0.55) == 0.55
    assert _f(55.0) == 0.55     # 0-100 cents -> 0-1
    assert _f(None) is None
    assert _f("not a number") is None


def test_search_with_no_network_returns_empty():
    # Use a clearly unreachable host so requests fails fast
    c = PredictFunClient(host="http://127.0.0.1:1", http_timeout=0.5)
    assert c.search_markets("anything") == []
    assert c.get_quote("any") is None

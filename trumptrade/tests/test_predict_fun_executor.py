import pytest
from trumptrade.orders import PredictFunExecutor, Order
from trumptrade.orders.predict_fun_executor import _split_side


def test_split_side_all_variants():
    assert _split_side("BUY_YES")  == ("buy", "YES")
    assert _split_side("BUY_NO")   == ("buy", "NO")
    assert _split_side("SELL_YES") == ("sell", "YES")
    assert _split_side("SELL_NO")  == ("sell", "NO")


def test_split_side_unknown_raises():
    with pytest.raises(ValueError):
        _split_side("HOLD")


def test_constructor_refuses_mainnet_without_confirm():
    with pytest.raises(RuntimeError) as e:
        PredictFunExecutor(testnet=False, api_key="x", confirm_live=False)
    assert "confirm_live" in str(e.value)


def test_constructor_refuses_mainnet_without_api_key():
    with pytest.raises(RuntimeError) as e:
        PredictFunExecutor(testnet=False, api_key=None, confirm_live=True)
    assert "API_KEY" in str(e.value)


def test_testnet_constructor_ok():
    ex = PredictFunExecutor(testnet=True)
    assert ex.testnet
    assert "testnet" in ex.host


def test_submit_unreachable_host_marks_error():
    ex = PredictFunExecutor(testnet=True, host="http://127.0.0.1:1", http_timeout=0.5)
    o = Order(venue="predict.fun", market_id="m1", side="BUY_YES",
              qty_contracts=10, limit_price=0.40)
    ex.submit(o)
    assert o.status == "error"
    assert o.error and len(o.error) > 0


def test_cancel_unfinalized_marks_cancelled():
    ex = PredictFunExecutor(testnet=True, host="http://127.0.0.1:1", http_timeout=0.5)
    o = Order(venue="predict.fun", market_id="m1", side="BUY_YES",
              qty_contracts=10, limit_price=0.40, venue_order_id="abc")
    o.status = "submitted"
    ex.cancel(o)
    assert o.status == "cancelled"


def test_cancel_finalized_is_noop():
    ex = PredictFunExecutor(testnet=True, host="http://127.0.0.1:1", http_timeout=0.5)
    o = Order(venue="predict.fun", market_id="m1", side="BUY_YES",
              qty_contracts=10, limit_price=0.40)
    o.status = "filled"
    ex.cancel(o)
    assert o.status == "filled"   # unchanged

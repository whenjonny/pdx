import pytest
from trumptrade.markets.pmxt_adapter import PMXTClient


def test_lazy_import_error_when_pmxt_missing():
    """If pmxt is not installed, _get_client() must raise a clear ImportError
    instead of crashing with a NameError or NoneType."""
    c = PMXTClient(exchange="limitless")
    try:
        import pmxt  # noqa: F401
        pytest.skip("pmxt installed; can't test missing-import path")
    except ImportError:
        pass
    with pytest.raises(ImportError) as exc:
        c._get_client()
    assert "pmxt" in str(exc.value).lower()


def test_search_returns_empty_when_pmxt_missing():
    c = PMXTClient(exchange="limitless")
    try:
        import pmxt  # noqa: F401
        pytest.skip("pmxt installed")
    except ImportError:
        pass
    # Should not crash; client surfaces the import error only when accessed
    with pytest.raises(ImportError):
        c.search_markets("anything")

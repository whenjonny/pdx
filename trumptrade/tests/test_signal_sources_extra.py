"""Smoke-tests for sources we didn't cover directly."""
import pytest
from trumptrade.signals import (
    FederalRegisterSource, TruthSocialSource, MockFileSource,
)


def test_truth_social_stub_raises_on_poll():
    s = TruthSocialSource(username="realDonaldTrump")
    with pytest.raises(NotImplementedError):
        s.poll()


def test_federal_register_unreachable_host_returns_empty():
    # Use a clearly-unreachable host; poll() should return [] not raise
    s = FederalRegisterSource()
    # Patch internal URL to bad host
    import trumptrade.signals.federal_register as fr_mod
    original = fr_mod._BASE
    fr_mod._BASE = "http://127.0.0.1:1/api/v1/documents.json"
    try:
        sigs = s.poll()
    finally:
        fr_mod._BASE = original
    assert sigs == []


def test_mock_file_source_dedupes_by_id(tmp_path):
    import json
    p = tmp_path / "p.json"
    p.write_text(json.dumps([
        {"id": "x1", "author": "a", "timestamp": "2026-01-01T00:00:00+00:00",
         "text": "t", "source": "test"},
    ]))
    s = MockFileSource(p)
    assert len(s.poll()) == 1
    assert s.poll() == []      # second call: already seen

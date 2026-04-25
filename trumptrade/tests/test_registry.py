import json
import pytest
from pathlib import Path
from trumptrade.signals import (
    SourceRegistry, SourceMetadata, MockFileSource,
    SourceNotFound, SourceAlreadyRegistered,
)


def _meta(name="m1", domain="us_policy", markets=("us_equities",), industries=("energy",)):
    return SourceMetadata(
        name=name, domain=domain, markets=list(markets), industries=list(industries),
    )


def test_register_and_lookup(tmp_path):
    posts = tmp_path / "p.json"
    posts.write_text(json.dumps([]))
    r = SourceRegistry()
    src = MockFileSource(posts)
    r.register(src, _meta())
    assert "m1" in r
    s2, m2 = r.get("m1")
    assert s2 is src
    assert m2.name == "m1"


def test_double_register_raises(tmp_path):
    posts = tmp_path / "p.json"; posts.write_text("[]")
    r = SourceRegistry()
    r.register(MockFileSource(posts), _meta())
    with pytest.raises(SourceAlreadyRegistered):
        r.register(MockFileSource(posts), _meta())


def test_unregister(tmp_path):
    posts = tmp_path / "p.json"; posts.write_text("[]")
    r = SourceRegistry()
    r.register(MockFileSource(posts), _meta())
    r.unregister("m1")
    assert "m1" not in r
    with pytest.raises(SourceNotFound):
        r.unregister("m1")


def test_query_filters(tmp_path):
    posts = tmp_path / "p.json"; posts.write_text("[]")
    r = SourceRegistry()
    r.register(MockFileSource(posts), _meta(name="energy", industries=("energy",)))
    r.register(MockFileSource(posts), _meta(name="tariff", industries=("tariff",)))
    r.register(MockFileSource(posts), _meta(name="cross", industries=()))

    only_energy = r.query(industry="energy")
    assert {m.name for _, m in only_energy} == {"energy"}

    all_us_eq = r.query(market="us_equities")
    assert len(all_us_eq) == 3

    foreign = r.query(market="fx")
    assert foreign == []


def test_yaml_load_and_poll(tmp_path):
    posts = tmp_path / "p.json"
    posts.write_text(json.dumps([{
        "id": "r1", "author": "x", "timestamp": "2026-01-01T00:00:00+00:00",
        "text": "test", "source": "yaml-test",
    }]))
    cfg = tmp_path / "src.yaml"
    cfg.write_text(f"""
sources:
  - name: m1
    factory: trumptrade.signals.mock:MockFileSource
    args:
      path: {posts}
    metadata:
      domain: us_policy
      markets: [us_equities]
      industries: [energy]
      update_cadence: irregular
      auth_required: false
      cost_per_request_usd: 0
      reliability: 1.0
""")
    r = SourceRegistry.from_yaml(cfg)
    assert "m1" in r
    polled = r.poll_all()
    assert "m1" in polled
    assert len(polled["m1"]) == 1
    assert polled["m1"][0].id == "r1"

from datetime import datetime, timezone
from trumptrade.agents import PolicyAgent, ExitAgent, AgentContext, TradeDecision
from trumptrade.markets import VenueRegistry, VenueMetadata, PolymarketClient
from trumptrade.markets.types import MarketRef, Quote
from trumptrade.types import Signal, Classification
from trumptrade.monitor import PositionStore, OpenPosition


def _signal():
    return Signal(
        id="s1", author="x", timestamp=datetime.now(timezone.utc),
        text="35% tariff on China", source="t",
    )


def _classify(s, p):
    return Classification(
        category="tariff_china", sentiment="hawkish",
        follow_through=0.7, rationale="t", confidence=0.9,
        original_excerpt="...",
    )


class _FakeVenueClient:
    venue = "fake"
    def __init__(self, refs):
        self._refs = refs
    def search_markets(self, query, limit=20, only_active=True):
        return self._refs[:limit]
    def get_quote(self, market_id):
        return None


def test_policy_agent_emits_decisions(tmp_path):
    refs = [
        MarketRef(venue="fake", market_id="m1", title="Will Trump tariff China?"),
        MarketRef(venue="fake", market_id="m2", title="Trump China tariff May 2026?"),
    ]
    client = _FakeVenueClient(refs)
    reg = VenueRegistry()
    reg.register(client, VenueMetadata(
        name="fake", venue_class="onchain_evm", base_currency="USDC",
        topics=["tariff_china"]))

    playbook = {
        "categories": {"tariff_china": {"keywords": ["china", "tariff"]}},
    }
    agent = PolicyAgent(classify_fn=_classify, default_size_contracts=100,
                        confidence_floor=0.5)
    ctx = AgentContext(playbook=playbook, venue_registry=reg)
    decisions = agent.analyze(_signal(), ctx)
    assert len(decisions) == 2
    assert all(d.action == "open" for d in decisions)
    assert all(d.side == "BUY_YES" for d in decisions)  # hawkish -> YES
    assert decisions[0].agent_name == "policy"
    assert decisions[0].category == "tariff_china"


def test_policy_agent_dovish_maps_to_buy_no():
    def dovish(s, p):
        return Classification(
            category="tariff_china", sentiment="dovish",
            follow_through=0.7, rationale="t", confidence=0.9,
            original_excerpt="...",
        )
    refs = [MarketRef(venue="fake", market_id="m1", title="Will Trump tariff?")]
    reg = VenueRegistry()
    reg.register(_FakeVenueClient(refs), VenueMetadata(
        name="fake", venue_class="onchain_evm", topics=["tariff_china"]))
    playbook = {"categories": {"tariff_china": {"keywords": ["tariff"]}}}
    agent = PolicyAgent(classify_fn=dovish, confidence_floor=0.5)
    ctx = AgentContext(playbook=playbook, venue_registry=reg)
    [d] = agent.analyze(_signal(), ctx)
    assert d.side == "BUY_NO"


def test_policy_agent_below_confidence_floor_emits_nothing():
    def low(s, p):
        return Classification(
            category="tariff_china", sentiment="hawkish",
            follow_through=0.1, rationale="t", confidence=0.3,    # eff = 0.03
            original_excerpt="...",
        )
    reg = VenueRegistry()
    reg.register(_FakeVenueClient([]), VenueMetadata(
        name="fake", venue_class="onchain_evm", topics=["tariff_china"]))
    agent = PolicyAgent(classify_fn=low, confidence_floor=0.5)
    ctx = AgentContext(playbook={"categories": {"tariff_china": {}}}, venue_registry=reg)
    assert agent.analyze(_signal(), ctx) == []


# ---- exit agent ----------------------------------------------------------


class _FakeMarket:
    closes_at = None


class _FakeQuote:
    market = _FakeMarket()
    yes_bid = 0.20
    yes_ask = 0.22
    no_bid = 0.78
    no_ask = 0.80
    last = 0.21
    volume_24h = 5000.0


def test_exit_agent_produces_close_decision_on_stop_loss(tmp_path):
    store = PositionStore(tmp_path / "p.jsonl")
    p = OpenPosition(
        venue="polymarket", market_id="m1", market_title="t",
        side="BUY_YES", entry_price=0.40, size_contracts=100,
        entry_at=datetime.now(timezone.utc),
        stop_loss_price=0.30,
    )
    store.open(p)

    agent = ExitAgent(quote_fn=lambda v, m: _FakeQuote(),
                      walkback_fn=lambda p: None)
    ctx = AgentContext(playbook={}, position_store=store)
    decisions = agent.analyze(_signal(), ctx)
    assert len(decisions) == 1
    d = decisions[0]
    assert d.action == "close"
    assert d.side == "SELL_YES"
    assert d.target_position_id == p.id
    assert "stop_loss" in d.rationale

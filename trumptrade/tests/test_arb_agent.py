from datetime import datetime, timezone
from trumptrade.agents import ArbAgent, AgentContext
from trumptrade.markets import MockMarketClient
from trumptrade.types import Signal


def test_arb_agent_emits_linked_pairs_when_spread_exists():
    # Two mock venues with different base prices -> Polymarket cheap, Kalshi rich
    poly = MockMarketClient(venue_name="polymarket", base_yes_price=0.30,
                            per_query_markets=1, random_walk_amplitude=0.0)
    kalshi = MockMarketClient(venue_name="kalshi", base_yes_price=0.50,
                              per_query_markets=1, random_walk_amplitude=0.0)
    agent = ArbAgent(polymarket_client=poly, kalshi_client=kalshi,
                     default_size_contracts=10, min_edge=0.001)

    sig = Signal(id="s", author="x", timestamp=datetime.now(timezone.utc),
                 text="trump tariff china", source="t")
    decisions = agent.analyze(sig, AgentContext(playbook={}))

    # ArbAgent emits 2 decisions per opportunity (long YES + long NO),
    # linked via linked_decision_id
    assert len(decisions) == 2 and decisions[0].linked_decision_id == decisions[1].id


def test_arb_agent_silent_with_empty_query():
    poly = MockMarketClient(venue_name="polymarket")
    kalshi = MockMarketClient(venue_name="kalshi")
    agent = ArbAgent(polymarket_client=poly, kalshi_client=kalshi)
    sig = Signal(id="s", author="x", timestamp=datetime.now(timezone.utc),
                 text="", source="t")
    assert agent.analyze(sig, AgentContext(playbook={})) == []

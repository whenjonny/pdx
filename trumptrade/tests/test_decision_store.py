from datetime import datetime
from trumptrade.agents.base import TradeDecision
from trumptrade.decisions import DecisionStore


def _d(action="open"):
    return TradeDecision(
        action=action, venue="v", market_id="m", market_title="t",
        side="BUY_YES" if action == "open" else "SELL_YES",
        size_contracts=10, confidence=0.7, agent_name="policy",
    )


def test_record_and_load_round_trip(tmp_path):
    s = DecisionStore(tmp_path / "decisions.jsonl")
    s.record(_d("open"))
    s.record(_d("close"))
    loaded = s.all()
    assert len(loaded) == 2
    assert {d.action for d in loaded} == {"open", "close"}


def test_record_many(tmp_path):
    s = DecisionStore(tmp_path / "decisions.jsonl")
    s.record_many([_d("open"), _d("open"), _d("close")])
    assert len(s.all()) == 3

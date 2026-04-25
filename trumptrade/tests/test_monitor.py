from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from trumptrade.monitor import (
    OpenPosition, PositionStore, build_default_rules,
    StopLossRule, TakeProfitRule, TimeDecayRule, LiquidityDropRule, WalkbackRule,
    ArbConvergenceRule, CloseExecutor, MonitorLoop,
)
from trumptrade.monitor.exit_rules import MarketContext


def _open(**overrides):
    base = dict(
        venue="polymarket", market_id="m1", market_title="t",
        side="BUY_YES", entry_price=0.40, size_contracts=100,
        entry_at=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return OpenPosition(**base)


def test_store_round_trip(tmp_path: Path):
    s = PositionStore(tmp_path / "positions.jsonl")
    p = _open()
    s.open(p)
    assert len(s.open_positions()) == 1
    # reload
    s2 = PositionStore(tmp_path / "positions.jsonl")
    assert s2.get(p.id).market_id == "m1"


def test_stop_loss_triggers_when_below():
    p = _open(stop_loss_price=0.30)
    ctx = MarketContext(current_yes_bid=0.28, current_yes_ask=0.30)
    d = StopLossRule().evaluate(p, ctx)
    assert d.should_close
    assert d.reason == "stop_loss"


def test_stop_loss_no_trigger_when_above():
    p = _open(stop_loss_price=0.30)
    ctx = MarketContext(current_yes_bid=0.45, current_yes_ask=0.46)
    assert not StopLossRule().evaluate(p, ctx).should_close


def test_take_profit_triggers_when_above():
    p = _open(take_profit_price=0.55)
    ctx = MarketContext(current_yes_bid=0.56, current_yes_ask=0.57)
    d = TakeProfitRule().evaluate(p, ctx)
    assert d.should_close
    assert d.reason == "take_profit"


def test_time_decay_uses_market_close_time():
    soon = datetime.now(timezone.utc) + timedelta(hours=12)
    p = _open()
    ctx = MarketContext(closes_at=soon)
    d = TimeDecayRule(hours_before_close=24).evaluate(p, ctx)
    assert d.should_close
    assert d.reason == "time_decay"


def test_time_decay_silent_when_far():
    far = datetime.now(timezone.utc) + timedelta(days=10)
    p = _open()
    ctx = MarketContext(closes_at=far)
    assert not TimeDecayRule().evaluate(p, ctx).should_close


def test_liquidity_drop_triggers():
    p = _open()
    ctx = MarketContext(volume_24h=100.0)
    d = LiquidityDropRule(min_volume_24h=1000.0).evaluate(p, ctx)
    assert d.should_close
    assert d.reason == "liquidity_drop"


def test_walkback_rule():
    p = _open()
    ctx = MarketContext(walkback_triggered=True, walkback_category="tariff_china")
    d = WalkbackRule().evaluate(p, ctx)
    assert d.should_close
    assert d.reason == "walkback"


def test_default_rules_count_and_priority():
    rules = build_default_rules()
    # walkback first (most urgent), then arb convergence
    assert rules[0].name == "walkback"
    assert rules[1].name == "arb_convergence"


# ------ MonitorLoop integration -------------------------------------------

class _FakeQuote:
    def __init__(self, yes_bid, yes_ask, no_bid, no_ask, volume_24h=10000, closes_at=None):
        self.yes_bid = yes_bid
        self.yes_ask = yes_ask
        self.no_bid = no_bid
        self.no_ask = no_ask
        self.last = (yes_bid + yes_ask) / 2 if yes_bid and yes_ask else None
        self.volume_24h = volume_24h
        self.market = type("M", (), {"closes_at": closes_at})()


def test_monitor_loop_closes_on_stop_loss(tmp_path):
    store = PositionStore(tmp_path / "positions.jsonl")
    p = _open(stop_loss_price=0.30)
    store.open(p)

    quotes = {("polymarket", "m1"): _FakeQuote(0.25, 0.27, 0.73, 0.75)}
    executor = CloseExecutor(mode="paper", log_path=tmp_path / "close.jsonl")

    loop = MonitorLoop(
        store=store,
        executor=executor,
        quote_fn=lambda v, m: quotes.get((v, m)),
    )
    stats = loop.run_once()
    assert stats["closed"] == 1
    p2 = store.get(p.id)
    assert p2.status == "closed"
    assert p2.exit_reason == "stop_loss"

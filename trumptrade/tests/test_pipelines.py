"""End-to-end tests for TradePipeline + MonitorPipeline using offline mocks."""
import json
from datetime import datetime, timezone
from pathlib import Path

from trumptrade.signals import SourceRegistry, SourceMetadata, MockFileSource
from trumptrade.markets import VenueRegistry, VenueMetadata, MockMarketClient
from trumptrade.monitor import PositionStore
from trumptrade.orders import OrderStore, OrderRouter, SimulatedExecutor
from trumptrade.risk import RiskLimits, RiskChecker
from trumptrade.agents import PolicyAgent, ExitAgent, AgentContext
from trumptrade.classifier import fake_classify
from trumptrade.pipelines import TradePipeline, MonitorPipeline, SignalLog
from trumptrade.decisions import DecisionStore


def _make_posts(tmp_path: Path) -> Path:
    p = tmp_path / "posts.json"
    p.write_text(json.dumps([
        {
            "id": "p1", "author": "trump",
            "timestamp": "2026-04-21T14:03:00+00:00",
            "text": "New 35% tariff on Chinese EVs effective May 1st",
            "source": "test",
        },
        {
            "id": "p2", "author": "trump",
            "timestamp": "2026-04-22T10:00:00+00:00",
            "text": "Just signed Executive Order on Strategic Bitcoin Reserve. Crypto going to the MOON!",
            "source": "test",
        },
    ]))
    return p


def _wire(tmp_path: Path):
    sreg = SourceRegistry()
    sreg.register(
        MockFileSource(_make_posts(tmp_path)),
        SourceMetadata(name="m", domain="us_policy",
                       markets=["prediction_markets"], industries=["tariff"]),
    )

    vreg = VenueRegistry()
    vreg.register(MockMarketClient(venue_name="polymarket", base_yes_price=0.40),
                  VenueMetadata(name="polymarket", venue_class="onchain_evm",
                                topics=["tariff_china", "crypto_friendly"]))
    vreg.register(MockMarketClient(venue_name="kalshi", base_yes_price=0.50),
                  VenueMetadata(name="kalshi", venue_class="regulated_us",
                                topics=["tariff_china", "crypto_friendly"]))

    pstore = PositionStore(tmp_path / "positions.jsonl")
    ostore = OrderStore(tmp_path / "orders.jsonl")
    sig_log = SignalLog(tmp_path / "signals.jsonl")
    dec_store = DecisionStore(tmp_path / "decisions.jsonl")
    risk = RiskChecker(RiskLimits(account_value_usd=10_000), pstore)

    venue_clients = {n: c for c, m in vreg.all() for n in [m.name]}

    def quote_fn(v, m):
        return venue_clients.get(v).get_quote(m) if venue_clients.get(v) else None

    executors = {n: SimulatedExecutor(n, quote_fn=quote_fn) for n in venue_clients}
    router = OrderRouter(ostore, pstore, executors, risk_checker=risk)

    playbook = {
        "categories": {
            "tariff_china": {"keywords": ["china", "tariff"]},
            "crypto_friendly": {"keywords": ["bitcoin", "crypto"]},
        },
    }
    ctx = AgentContext(playbook=playbook, position_store=pstore,
                       venue_registry=vreg, risk_checker=risk)

    return sreg, vreg, pstore, ostore, sig_log, dec_store, router, ctx


def test_trade_pipeline_signal_to_position(tmp_path):
    sreg, vreg, pstore, ostore, sig_log, dec_store, router, ctx = _wire(tmp_path)
    agent = PolicyAgent(classify_fn=fake_classify, default_size_contracts=10,
                        confidence_floor=0.50, per_venue_market_limit=2)
    pipe = TradePipeline(sreg, [agent], router, ctx, sig_log, dec_store)
    result = pipe.run_once()

    assert result.signals == 2
    assert result.new_decisions > 0
    assert result.accepted > 0
    # Each accepted decision became a position
    assert len(pstore.open_positions()) == result.accepted
    # logs are persisted
    assert (tmp_path / "signals.jsonl").exists()
    assert (tmp_path / "decisions.jsonl").exists()
    assert (tmp_path / "orders.jsonl").exists()
    assert (tmp_path / "positions.jsonl").exists()


def test_monitor_pipeline_closes_on_stop_loss(tmp_path):
    sreg, vreg, pstore, ostore, sig_log, dec_store, router, ctx = _wire(tmp_path)
    # Open a position with an aggressive stop_loss so the next quote (~0.40) fails
    from trumptrade.monitor import OpenPosition
    p = OpenPosition(
        venue="polymarket", market_id="any", market_title="t",
        side="BUY_YES", entry_price=0.55, size_contracts=100,
        entry_at=datetime.now(timezone.utc),
        stop_loss_price=0.50,                     # mock yes_bid will be ~0.39 -> trigger
    )
    pstore.open(p)

    venue_clients = {n: c for c, m in vreg.all() for n in [m.name]}

    def quote_fn(v, m):
        return venue_clients.get(v).get_quote(m) if venue_clients.get(v) else None

    pipe = MonitorPipeline(
        ExitAgent(quote_fn=quote_fn),
        router, ctx, decision_store=dec_store,
    )
    tick = pipe.run_once()
    assert tick.decisions >= 1
    assert tick.closed >= 1
    p2 = pstore.get(p.id)
    assert p2.status == "closed"
    assert p2.exit_reason == "stop_loss"


def test_full_e2e_open_then_close(tmp_path):
    """Open via TradePipeline, then close via MonitorPipeline next tick."""
    sreg, vreg, pstore, ostore, sig_log, dec_store, router, ctx = _wire(tmp_path)
    agent = PolicyAgent(classify_fn=fake_classify, default_size_contracts=10,
                        confidence_floor=0.50, per_venue_market_limit=1)
    trade = TradePipeline(sreg, [agent], router, ctx, sig_log, dec_store)
    trade.run_once()
    n_open = len(pstore.open_positions())
    assert n_open > 0

    venue_clients = {n: c for c, m in vreg.all() for n in [m.name]}

    def quote_fn(v, m):
        return venue_clients.get(v).get_quote(m) if venue_clients.get(v) else None

    # Mutate the open positions to have aggressive take_profit so monitor closes them
    for pos in pstore.open_positions():
        pos.take_profit_price = 0.0   # trivially below any mark -> fires
        pstore.update(pos)

    mon = MonitorPipeline(ExitAgent(quote_fn=quote_fn), router, ctx, dec_store)
    tick = mon.run_once()
    assert tick.closed == n_open
    assert all(p.status == "closed" for p in pstore.all())

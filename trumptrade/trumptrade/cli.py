from __future__ import annotations
import logging
import sys
from pathlib import Path
import click
from trumptrade.config import load_playbook, data_dir
from trumptrade.pipeline import Pipeline
from trumptrade.signals import MockFileSource, RSSFeedSource
from trumptrade.classifier import classify, fake_classify
from trumptrade.types import Signal
from datetime import datetime, timezone


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Debug logging.")
def cli(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s  %(message)s")


@cli.command()
@click.option("--source", type=click.Choice(["mock", "rss"]), default="mock")
@click.option("--path", type=click.Path(exists=False), default="data/sample_posts/posts.json",
              help="(mock) path to posts JSON")
@click.option("--url", type=str, default=None, help="(rss) feed URL")
@click.option("--interval", type=int, default=30, help="Poll interval seconds.")
@click.option("--once", is_flag=True, help="Poll once and exit (useful for testing).")
@click.option("--fake", is_flag=True, help="Use keyword-based fake classifier (no API key needed).")
def watch(source: str, path: str, url: str | None, interval: int, once: bool, fake: bool) -> None:
    """Watch a signal source and emit alerts."""
    if source == "mock":
        src = MockFileSource(path)
    elif source == "rss":
        if not url:
            click.echo("--url required for rss source", err=True)
            sys.exit(2)
        src = RSSFeedSource(url)
    else:  # pragma: no cover
        sys.exit(2)

    classify_fn = fake_classify if fake else None
    pipe = Pipeline(src, classify_fn=classify_fn)
    if once:
        pipe.run_once()
    else:
        pipe.run_loop(interval_sec=interval)


@cli.command()
@click.argument("text")
@click.option("--author", default="realDonaldTrump")
@click.option("--url", default=None)
@click.option("--fake", is_flag=True, help="Use keyword-based fake classifier (no API key).")
def analyze(text: str, author: str, url: str | None, fake: bool) -> None:
    """One-shot analysis of arbitrary post text. Useful for manual QA."""
    signal = Signal(
        id=f"adhoc-{datetime.now(timezone.utc).isoformat()}",
        author=author,
        timestamp=datetime.now(timezone.utc),
        text=text,
        url=url,
        source="cli",
    )
    playbook = load_playbook()
    classification = (fake_classify if fake else classify)(signal, playbook)
    from trumptrade.execution import expand_basket, Alerter
    basket = expand_basket(classification, playbook)
    Alerter(min_confidence=0.0, log_path=data_dir() / "alerts.jsonl").maybe_emit(signal, classification, basket)


@cli.command()
@click.option("--alerts", "alerts_path", type=click.Path(exists=True), default="data/alerts.jsonl")
@click.option("--capital", type=float, default=100_000.0)
@click.option("--hold-days", type=int, default=5)
@click.option("--price-source", type=click.Choice(["stub", "yfinance"]), default="stub")
@click.option("--no-walkback", is_flag=True, help="Disable walk-back close logic.")
def backtest(alerts_path: str, capital: float, hold_days: int, price_source: str, no_walkback: bool) -> None:
    """Replay alerts.jsonl through a simulated paper trader and compute P&L."""
    from trumptrade.backtest import Backtester, StubPriceSource, YFinancePriceSource
    playbook = load_playbook()
    if price_source == "stub":
        prices = StubPriceSource()
    else:
        prices = YFinancePriceSource()
    bt = Backtester(prices, playbook, initial_capital=capital, hold_days=hold_days, use_walkback=not no_walkback)
    result = bt.run(Path(alerts_path))
    click.echo(result.summary())
    click.echo("")
    click.echo("trades:")
    for t in result.trades:
        click.echo(
            f"  {t.open_date} -> {t.close_date}  {t.side:5s} {t.ticker:5s} "
            f"shares={t.shares:>4d} open=${t.open_price:.2f} close=${t.close_price:.2f} "
            f"pnl=${t.pnl:>+9.2f}  [{t.close_reason}]"
        )


@cli.command("arb-scan")
@click.option("--query", "-q", required=True, help="Free-text query, e.g. 'tariff china'.")
@click.option("--limit", type=int, default=25, help="Markets per venue.")
@click.option("--min-edge", type=float, default=0.01, help="Minimum gross profit per $1 pair.")
@click.option("--fee", type=float, default=0.0, help="Combined round-trip fee per $1.")
@click.option("--use-llm", is_flag=True, help="Use Claude Haiku for semantic match (more accurate, costs ~$0.01/pair).")
def arb_scan(query: str, limit: int, min_edge: float, fee: float, use_llm: bool) -> None:
    """Scan Polymarket vs Kalshi for cross-market arbitrage opportunities."""
    from trumptrade.markets import PolymarketClient, KalshiClient
    from trumptrade.arb import ArbScanner
    scanner = ArbScanner(
        polymarket=PolymarketClient(),
        kalshi=KalshiClient(),
        use_llm_matcher=use_llm,
        fee_per_dollar=fee,
        min_edge=min_edge,
    )
    report = scanner.scan(query, per_venue_limit=limit)
    click.echo(report.summary())


@cli.command("report")
@click.option("--out", type=click.Path(), default=None,
              help="Write JSON report alongside the human-readable text.")
def report_cmd(out: str | None) -> None:
    """Generate a result-summary report from data/*.jsonl logs."""
    from trumptrade.reports import build_summary
    import json
    summary = build_summary(data_dir())
    click.echo(summary.render_text())
    if out:
        Path(out).write_text(json.dumps({
            "generated_at": summary.generated_at.isoformat(),
            "window_start": summary.window_start.isoformat() if summary.window_start else None,
            "window_end": summary.window_end.isoformat() if summary.window_end else None,
            "signals": {
                "total": summary.n_signals, "by_source": summary.signals_by_source,
            },
            "decisions": {
                "total": summary.n_decisions,
                "by_agent": summary.decisions_by_agent,
                "by_action": summary.decisions_by_action,
            },
            "orders": {
                "total": summary.n_orders,
                "fill_rate": summary.fill_rate,
                "by_status": summary.orders_by_status,
                "rejected_top_reasons": summary.rejected_top_reasons,
            },
            "positions": {
                "open": summary.n_open, "closed": summary.n_closed,
                "winning": summary.n_winning, "losing": summary.n_losing,
                "win_rate": summary.win_rate,
                "realized_pnl": summary.realized_pnl,
                "unrealized_pnl": summary.unrealized_pnl,
                "avg_win": summary.avg_win, "avg_loss": summary.avg_loss,
                "largest_win": summary.largest_win, "largest_loss": summary.largest_loss,
                "by_exit_reason": summary.by_exit_reason,
                "by_venue": summary.by_venue,
            },
        }, indent=2, default=str))
        click.echo(f"\n(json written to {out})")


@cli.command("trade-loop")
@click.option("--sources-config", type=click.Path(exists=True), default="config/sources.yaml")
@click.option("--markets-config", type=click.Path(exists=True), default="config/markets.yaml")
@click.option("--risk-config", type=click.Path(exists=True), default="config/risk_limits.yaml")
@click.option("--mode", type=click.Choice(["paper", "alert", "live"]), default="paper",
              help="paper = SimulatedExecutor; alert = log only, no orders; live = real broker.")
@click.option("--use-fake-classifier", is_flag=True, default=True,
              help="Use offline keyword classifier (no ANTHROPIC_API_KEY needed). Default ON.")
@click.option("--no-fake", is_flag=True, help="Force real Claude classifier.")
@click.option("--interval", type=int, default=30)
@click.option("--once", is_flag=True, help="One sweep then exit.")
def trade_loop(sources_config: str, markets_config: str, risk_config: str,
               mode: str, use_fake_classifier: bool, no_fake: bool,
               interval: int, once: bool) -> None:
    """End-to-end paper trade loop:

    Sources -> Agents -> Router -> Orders -> Positions

    Logs every signal, decision, order, position to data/*.jsonl.
    """
    from trumptrade.signals import SourceRegistry
    from trumptrade.markets import VenueRegistry
    from trumptrade.monitor import PositionStore
    from trumptrade.orders import OrderStore, SimulatedExecutor, OrderRouter
    from trumptrade.risk import load_risk_limits, RiskChecker
    from trumptrade.agents import PolicyAgent, ArbAgent, AgentContext
    from trumptrade.classifier import classify as real_classify, fake_classify
    from trumptrade.pipelines import TradePipeline, SignalLog
    from trumptrade.decisions import DecisionStore

    sources = SourceRegistry.from_yaml(Path(sources_config))
    venues = VenueRegistry.from_yaml(Path(markets_config))
    venue_clients = {meta.name: client for client, meta in venues.all()}

    pstore = PositionStore(data_dir() / "positions.jsonl")
    ostore = OrderStore(data_dir() / "orders.jsonl")
    sig_log = SignalLog(data_dir() / "signals.jsonl")
    dec_store = DecisionStore(data_dir() / "decisions.jsonl")

    limits = load_risk_limits(risk_config)
    risk = RiskChecker(limits, pstore)

    if mode == "alert":
        # alert mode = build a no-op executor map; everything will reject at routing
        executors = {}
    else:
        # Both paper and live use SimulatedExecutor for now (live wiring is per-venue)
        def quote_lookup(venue, market_id):
            client = venue_clients.get(venue)
            return client.get_quote(market_id) if client else None
        executors = {
            name: SimulatedExecutor(name, quote_fn=quote_lookup)
            for name in venue_clients.keys()
        }
        if mode == "live":
            click.echo("WARNING: --mode live falls back to SimulatedExecutor for unwired venues.")

    router = OrderRouter(ostore, pstore, executors, risk_checker=risk)

    cls_fn = fake_classify if (use_fake_classifier and not no_fake) else real_classify
    playbook = load_playbook()

    agents = [
        PolicyAgent(classify_fn=cls_fn, default_size_contracts=100, confidence_floor=0.55),
    ]
    poly = venue_clients.get("polymarket")
    kalshi = venue_clients.get("kalshi")
    if poly is not None and kalshi is not None:
        agents.append(ArbAgent(polymarket_client=poly, kalshi_client=kalshi,
                               default_size_contracts=100, min_edge=0.005))

    ctx = AgentContext(playbook=playbook, position_store=pstore,
                       venue_registry=venues, risk_checker=risk)

    pipe = TradePipeline(
        source_registry=sources,
        agents=agents,
        router=router,
        agent_ctx=ctx,
        signal_log=sig_log,
        decision_store=dec_store,
    )

    if once:
        result = pipe.run_once()
        click.echo(result.summary())
    else:
        pipe.run_forever(interval_sec=interval)


@cli.command("monitor-loop")
@click.option("--markets-config", type=click.Path(exists=True), default="config/markets.yaml")
@click.option("--mode", type=click.Choice(["paper", "alert", "live"]), default="paper")
@click.option("--interval", type=int, default=30)
@click.option("--once", is_flag=True)
def monitor_loop_cmd(markets_config: str, mode: str, interval: int, once: bool) -> None:
    """Continuous position monitor using the new ExitAgent + OrderRouter path."""
    from trumptrade.markets import VenueRegistry
    from trumptrade.monitor import PositionStore
    from trumptrade.orders import OrderStore, SimulatedExecutor, OrderRouter
    from trumptrade.agents import ExitAgent, AgentContext
    from trumptrade.pipelines import MonitorPipeline
    from trumptrade.decisions import DecisionStore

    venues = VenueRegistry.from_yaml(Path(markets_config))
    venue_clients = {meta.name: client for client, meta in venues.all()}

    pstore = PositionStore(data_dir() / "positions.jsonl")
    ostore = OrderStore(data_dir() / "orders.jsonl")
    dec_store = DecisionStore(data_dir() / "decisions.jsonl")

    def quote_lookup(venue, market_id):
        client = venue_clients.get(venue)
        return client.get_quote(market_id) if client else None

    if mode == "alert":
        executors = {}
    else:
        executors = {
            name: SimulatedExecutor(name, quote_fn=quote_lookup)
            for name in venue_clients.keys()
        }

    router = OrderRouter(ostore, pstore, executors, risk_checker=None)
    exit_agent = ExitAgent(quote_fn=quote_lookup)
    ctx = AgentContext(playbook=load_playbook(), position_store=pstore,
                       venue_registry=venues)
    pipe = MonitorPipeline(exit_agent, router, ctx, decision_store=dec_store)

    if once:
        click.echo(pipe.run_once().summary())
    else:
        pipe.run_forever(interval_sec=interval)


@cli.command("paper-run")
@click.option("--interval", type=int, default=30,
              help="Trade-loop interval (monitor runs every tick too).")
@click.option("--ticks", type=int, default=0, help="Stop after N ticks (0 = forever).")
@click.option("--sources-config", type=click.Path(exists=True), default="config/sources.yaml")
@click.option("--markets-config", type=click.Path(exists=True), default="config/markets.yaml")
@click.option("--risk-config", type=click.Path(exists=True), default="config/risk_limits.yaml")
@click.option("--use-fake-classifier", is_flag=True, default=True)
@click.option("--no-fake", is_flag=True)
def paper_run(interval: int, ticks: int, sources_config: str, markets_config: str,
              risk_config: str, use_fake_classifier: bool, no_fake: bool) -> None:
    """One-process paper run: trade loop + monitor loop interleaved.

    On each tick:
      1) trade pipeline polls sources, routes new opens
      2) monitor pipeline evaluates all open positions, routes closes
    Everything logged to data/{signals,decisions,orders,positions}.jsonl.
    """
    import time
    from trumptrade.signals import SourceRegistry
    from trumptrade.markets import VenueRegistry
    from trumptrade.monitor import PositionStore
    from trumptrade.orders import OrderStore, SimulatedExecutor, OrderRouter
    from trumptrade.risk import load_risk_limits, RiskChecker
    from trumptrade.agents import PolicyAgent, ArbAgent, ExitAgent, AgentContext
    from trumptrade.classifier import classify as real_classify, fake_classify
    from trumptrade.pipelines import TradePipeline, MonitorPipeline, SignalLog
    from trumptrade.decisions import DecisionStore

    sources = SourceRegistry.from_yaml(Path(sources_config))
    venues = VenueRegistry.from_yaml(Path(markets_config))
    venue_clients = {meta.name: client for client, meta in venues.all()}

    pstore = PositionStore(data_dir() / "positions.jsonl")
    ostore = OrderStore(data_dir() / "orders.jsonl")
    sig_log = SignalLog(data_dir() / "signals.jsonl")
    dec_store = DecisionStore(data_dir() / "decisions.jsonl")
    limits = load_risk_limits(risk_config)
    risk = RiskChecker(limits, pstore)

    def quote_lookup(venue, market_id):
        client = venue_clients.get(venue)
        return client.get_quote(market_id) if client else None

    executors = {
        name: SimulatedExecutor(name, quote_fn=quote_lookup)
        for name in venue_clients.keys()
    }
    router = OrderRouter(ostore, pstore, executors, risk_checker=risk)
    cls_fn = fake_classify if (use_fake_classifier and not no_fake) else real_classify

    agents = [PolicyAgent(classify_fn=cls_fn, default_size_contracts=100, confidence_floor=0.55)]
    poly = venue_clients.get("polymarket"); kalshi = venue_clients.get("kalshi")
    if poly is not None and kalshi is not None:
        agents.append(ArbAgent(polymarket_client=poly, kalshi_client=kalshi,
                               default_size_contracts=100))

    ctx = AgentContext(playbook=load_playbook(), position_store=pstore,
                       venue_registry=venues, risk_checker=risk)
    trade_pipe = TradePipeline(sources, agents, router, ctx, sig_log, dec_store)
    mon_pipe = MonitorPipeline(ExitAgent(quote_fn=quote_lookup), router, ctx, dec_store)

    n = 0
    try:
        while True:
            t = trade_pipe.run_once()
            click.echo(t.summary())
            m = mon_pipe.run_once()
            click.echo(m.summary())
            n += 1
            if ticks and n >= ticks:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        click.echo("paper-run stopped by user")


@cli.command("signals-tail")
@click.option("--n", type=int, default=20)
def signals_tail(n: int) -> None:
    from trumptrade.pipelines import SignalLog
    log = SignalLog(data_dir() / "signals.jsonl")
    rows = log.tail(n)
    if not rows:
        click.echo("(no signals logged)")
        return
    for r in rows:
        s = r.get("signal", {})
        click.echo(f"  {s.get('timestamp', '?')[:19]}  src={r.get('source', '?'):20s}  "
                   f"{s.get('id', '?'):24s}  {(s.get('text') or '')[:80]}")


@cli.command("decisions-tail")
@click.option("--n", type=int, default=20)
def decisions_tail(n: int) -> None:
    from trumptrade.decisions import DecisionStore
    store = DecisionStore(data_dir() / "decisions.jsonl")
    decisions = store.all()[-n:]
    if not decisions:
        click.echo("(no decisions logged)")
        return
    for d in decisions:
        click.echo(f"  {d.created_at.isoformat()[:19]}  {d.agent_name:8s}  {d.action:10s}  "
                   f"{d.venue:11s} {d.side:8s}  size={d.size_contracts:>4d}  conf={d.confidence:.2f}  "
                   f"{d.market_title[:50]}")


@cli.command("orders-tail")
@click.option("--n", type=int, default=20)
def orders_tail(n: int) -> None:
    from trumptrade.orders import OrderStore
    store = OrderStore(data_dir() / "orders.jsonl")
    orders = store.all()[-n:]
    if not orders:
        click.echo("(no orders logged)")
        return
    for o in orders:
        avg = o.avg_fill_price or o.limit_price or 0.0
        click.echo(f"  {o.created_at.isoformat()[:19]}  {o.venue:11s} {o.side:8s} "
                   f"qty={o.qty_contracts:>4d} px={avg:.3f}  status={o.status:14s} "
                   f"{(o.market_title or '')[:40]}")


@cli.command("sources-list")
@click.option("--config", "config_path", type=click.Path(exists=True),
              default="config/sources.yaml")
def sources_list(config_path: str) -> None:
    """List all signal sources declared in the YAML manifest."""
    from trumptrade.signals import SourceRegistry
    r = SourceRegistry.from_yaml(Path(config_path))
    click.echo(f"{len(r)} source(s) registered")
    for src, meta in r.all():
        click.echo(f"  - {meta.name}")
        click.echo(f"      domain    : {meta.domain}")
        click.echo(f"      markets   : {', '.join(meta.markets) or '(none)'}")
        click.echo(f"      industries: {', '.join(meta.industries) or '(cross-sector)'}")
        click.echo(f"      cadence   : {meta.update_cadence}  auth={meta.auth_required}  "
                   f"cost=${meta.cost_per_request_usd:.4f}/req  reliability={meta.reliability:.2f}")
        if meta.description:
            click.echo(f"      desc      : {meta.description}")


@cli.command("markets-list")
@click.option("--config", "config_path", type=click.Path(exists=True),
              default="config/markets.yaml")
@click.option("--topic", default=None, help="Filter venues by topic.")
@click.option("--venue-class", default=None,
              type=click.Choice(["regulated_us", "onchain_evm", "onchain_solana",
                                 "onchain_other", "play_money", "research"]))
def markets_list(config_path: str, topic: str | None, venue_class: str | None) -> None:
    """List all prediction-market venues, optionally filtered by topic / class."""
    from trumptrade.markets import VenueRegistry
    r = VenueRegistry.from_yaml(Path(config_path))
    venues = r.query(topic=topic, venue_class=venue_class)
    click.echo(f"{len(venues)} venue(s) (of {len(r)} total)")
    for client, meta in venues:
        click.echo(f"  - {meta.name}  [{meta.venue_class}]")
        click.echo(f"      chain={meta.chain or '-'}  ccy={meta.base_currency}  "
                   f"fees~{meta.fee_estimate_per_dollar:.4f}/$  reliability={meta.reliability:.2f}")
        click.echo(f"      auth_read={meta.auth_required_for_read}  "
                   f"auth_trade={meta.auth_required_for_trade}  "
                   f"limit_orders={meta.supports_limit_orders}  ws={meta.supports_websocket}")
        if meta.topics:
            click.echo(f"      topics    : {', '.join(meta.topics)}")
        if meta.description:
            click.echo(f"      desc      : {meta.description}")


@cli.command("positions")
@click.option("--show-closed", is_flag=True, help="Include closed positions.")
def positions_cmd(show_closed: bool) -> None:
    """List current open (and optionally closed) positions."""
    from trumptrade.monitor import PositionStore
    store = PositionStore(data_dir() / "positions.jsonl")
    opens = store.open_positions()
    click.echo(f"{len(opens)} open position(s)")
    for p in opens:
        mark = p.current_mark
        upnl = p.unrealized_pnl
        click.echo(f"  {p.id}  {p.venue:11s} {p.side:8s} entry={p.entry_price:.3f} "
                   f"size={p.size_contracts}  mark={mark if mark is not None else '-':<6} "
                   f"upnl={upnl if upnl is not None else '-':<8}  {p.market_title[:40]}")
    if show_closed:
        closed = store.closed_positions()
        click.echo(f"\n{len(closed)} closed position(s)")
        for p in closed[-30:]:
            click.echo(f"  {p.id}  {p.venue:11s} {p.side:8s} entry={p.entry_price:.3f} "
                       f"exit={p.exit_price or 0:.3f}  pnl={p.realized_pnl or 0:+.2f}  "
                       f"reason={p.exit_reason}  {p.market_title[:40]}")


@cli.command("close-position")
@click.argument("position_id")
@click.option("--exit-price", type=float, required=True, help="Manual exit price (mark).")
def close_position(position_id: str, exit_price: float) -> None:
    """Manually close a position (logs to positions.jsonl, no broker call)."""
    from trumptrade.monitor import PositionStore
    store = PositionStore(data_dir() / "positions.jsonl")
    p = store.close(position_id, exit_price=exit_price, reason="manual")
    click.echo(f"closed {p.id}  exit={p.exit_price:.3f}  pnl={p.realized_pnl:+.2f}")


@cli.command("monitor")
@click.option("--mode", type=click.Choice(["alert", "paper", "live"]), default="alert")
@click.option("--interval", type=int, default=30)
@click.option("--once", is_flag=True, help="One sweep then exit.")
@click.option("--markets-config", type=click.Path(exists=True),
              default="config/markets.yaml")
def monitor_cmd(mode: str, interval: int, once: bool, markets_config: str) -> None:
    """Continuous position monitor: poll quotes, evaluate exit rules,
    emit close orders. Default mode is `alert` (no real orders submitted)."""
    from trumptrade.monitor import (
        PositionStore, MonitorLoop, CloseExecutor, build_default_rules,
    )
    from trumptrade.markets import VenueRegistry

    store = PositionStore(data_dir() / "positions.jsonl")
    venues = VenueRegistry.from_yaml(Path(markets_config))
    venue_clients = {meta.name: client for client, meta in venues.all()}

    def quote_fn(venue: str, market_id: str):
        client = venue_clients.get(venue)
        if client is None:
            return None
        return client.get_quote(market_id)

    executor = CloseExecutor(
        mode=mode,
        log_path=data_dir() / "close_orders.jsonl",
        venue_clients=venue_clients,
    )
    loop = MonitorLoop(store=store, rules=build_default_rules(),
                       executor=executor, quote_fn=quote_fn)

    if once:
        stats = loop.run_once()
        click.echo(f"tick stats: {stats}")
    else:
        loop.run_forever(interval_sec=interval)


@cli.command("risk-status")
@click.option("--config", "config_path", type=click.Path(exists=True),
              default="config/risk_limits.yaml")
def risk_status(config_path: str) -> None:
    """Show current portfolio exposure vs risk limits."""
    from trumptrade.monitor import PositionStore
    from trumptrade.risk import load_risk_limits, RiskChecker
    limits = load_risk_limits(config_path)
    store = PositionStore(data_dir() / "positions.jsonl")
    opens = store.open_positions()
    total = sum(p.notional_at_entry for p in opens)
    click.echo(f"account_value = ${limits.account_value_usd:,.2f}")
    click.echo(f"open positions = {len(opens)} / max {limits.max_open_positions}")
    click.echo(f"total exposure = ${total:,.2f}  "
               f"({total/limits.account_value_usd:.1%} of acct, "
               f"cap {limits.max_per_venue_pct:.0%})")
    by_venue: dict[str, float] = {}
    for p in opens:
        by_venue[p.venue] = by_venue.get(p.venue, 0.0) + p.notional_at_entry
    if by_venue:
        click.echo("by venue:")
        for v, n in sorted(by_venue.items(), key=lambda kv: kv[1], reverse=True):
            click.echo(f"  {v:11s} ${n:,.2f}  ({n/limits.account_value_usd:.1%})")


@cli.command("dashboard")
@click.option("--port", type=int, default=8501)
def dashboard_cmd(port: int) -> None:
    """Launch the Streamlit dashboard."""
    import subprocess, sys
    app_path = Path(__file__).resolve().parent / "dashboard" / "app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", str(port)]
    click.echo(f"launching: {' '.join(cmd)}")
    subprocess.run(cmd)


@cli.command("paper-trade")
@click.option("--alert-id", type=str, required=False, help="Trade most recent alert if omitted.")
@click.option("--alerts", "alerts_path", type=click.Path(exists=True), default="data/alerts.jsonl")
@click.option("--capital", type=float, default=100_000.0, help="Simulated account value (sim mode).")
@click.option("--mode", type=click.Choice(["sim", "alpaca"]), default="sim")
@click.option("--price-source", type=click.Choice(["stub", "yfinance"]), default="stub")
def paper_trade(alert_id: str | None, alerts_path: str, capital: float, mode: str, price_source: str) -> None:
    """Turn a saved alert into an order report (sim mode) or live paper orders (alpaca)."""
    import json, os
    from trumptrade.types import Alert
    from trumptrade.execution import SimulatedPaperTrader, AlpacaPaperTrader
    from trumptrade.backtest import StubPriceSource, YFinancePriceSource
    from datetime import date

    playbook = load_playbook()
    alerts = [Alert(**json.loads(l)) for l in Path(alerts_path).read_text().splitlines() if l.strip()]
    if not alerts:
        click.echo("no alerts", err=True)
        sys.exit(1)
    alert = next((a for a in alerts if a.signal.id == alert_id), alerts[-1]) if alert_id else alerts[-1]
    click.echo(f"trading alert: {alert.signal.id} ({alert.classification.category}/{alert.classification.sentiment})")

    prices_src = StubPriceSource() if price_source == "stub" else YFinancePriceSource()
    today = date.today()
    prices = {leg.ticker: prices_src.close_on(leg.ticker, today) for leg in alert.basket}
    prices = {k: v for k, v in prices.items() if v is not None}

    if mode == "sim":
        trader = SimulatedPaperTrader(playbook.get("risk_gates", {}))
        report = trader.submit_basket(alert.basket, prices, account_value=capital, available_cash=capital)
    else:
        api_key = os.environ.get("ALPACA_API_KEY")
        api_secret = os.environ.get("ALPACA_SECRET")
        if not api_key or not api_secret:
            click.echo("ALPACA_API_KEY and ALPACA_SECRET required for --mode alpaca", err=True)
            sys.exit(2)
        trader = AlpacaPaperTrader(playbook.get("risk_gates", {}), api_key, api_secret)
        report = trader.submit_basket(alert.basket, prices)

    click.echo(report.summary())


if __name__ == "__main__":
    cli()

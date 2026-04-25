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

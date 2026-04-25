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

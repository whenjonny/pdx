from __future__ import annotations
import logging
import sys
from pathlib import Path
import click
from trumptrade.config import load_playbook, data_dir
from trumptrade.pipeline import Pipeline
from trumptrade.signals import MockFileSource, RSSFeedSource
from trumptrade.classifier import classify
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
def watch(source: str, path: str, url: str | None, interval: int, once: bool) -> None:
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

    pipe = Pipeline(src)
    if once:
        pipe.run_once()
    else:
        pipe.run_loop(interval_sec=interval)


@cli.command()
@click.argument("text")
@click.option("--author", default="realDonaldTrump")
@click.option("--url", default=None)
def analyze(text: str, author: str, url: str | None) -> None:
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
    classification = classify(signal, playbook)
    from trumptrade.execution import expand_basket, Alerter
    basket = expand_basket(classification, playbook)
    Alerter(min_confidence=0.0, log_path=data_dir() / "alerts.jsonl").maybe_emit(signal, classification, basket)


if __name__ == "__main__":
    cli()

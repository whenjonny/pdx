from __future__ import annotations
from datetime import datetime, timezone
from trumptrade.signals.base import SignalSource
from trumptrade.types import Signal


class RSSFeedSource(SignalSource):
    """Pulls signals from an RSS feed (e.g., WH press briefing, news wire).
    Author defaults to the feed title; override via `author=` for specificity.

    feedparser is imported lazily so the package works without it installed
    when only MockFileSource is used.
    """

    def __init__(self, url: str, author: str | None = None, source_label: str = "rss"):
        self.url = url
        self.author_override = author
        self.source_label = source_label
        self._seen: set[str] = set()

    def poll(self) -> list[Signal]:
        try:
            import feedparser
        except ImportError as e:
            raise ImportError(
                "RSSFeedSource requires feedparser. Install with: pip install feedparser"
            ) from e
        feed = feedparser.parse(self.url)
        new: list[Signal] = []
        feed_author = self.author_override or (feed.feed.get("title") if feed.feed else "rss")
        for entry in feed.entries:
            entry_id = entry.get("id") or entry.get("link") or entry.get("title", "")
            if not entry_id or entry_id in self._seen:
                continue
            self._seen.add(entry_id)
            published = entry.get("published_parsed")
            ts = datetime(*published[:6], tzinfo=timezone.utc) if published else datetime.now(timezone.utc)
            text_parts = [entry.get("title", ""), entry.get("summary", "")]
            text = "\n".join(p for p in text_parts if p)
            new.append(
                Signal(
                    id=entry_id,
                    author=feed_author,
                    timestamp=ts,
                    text=text,
                    url=entry.get("link"),
                    source=self.source_label,
                )
            )
        return new

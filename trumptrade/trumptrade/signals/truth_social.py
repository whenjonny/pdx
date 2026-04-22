from __future__ import annotations
from trumptrade.signals.base import SignalSource
from trumptrade.types import Signal


class TruthSocialSource(SignalSource):
    """Stub. Truth Social has no official public API.

    To implement in production, consider:
    - truthbrush (third-party, ToS-ambiguous): https://github.com/stanfordio/truthbrush
    - Authenticated browser cookies + HTML scraping
    - A paid aggregator that republishes Trump posts via webhook
    """

    def __init__(self, username: str = "realDonaldTrump"):
        self.username = username

    def poll(self) -> list[Signal]:
        raise NotImplementedError(
            "TruthSocialSource is a stub. Install truthbrush or provide a custom "
            "implementation. For Week 1 MVP, use MockFileSource."
        )

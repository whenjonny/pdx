from __future__ import annotations
from abc import ABC, abstractmethod
from trumptrade.types import Signal


class SignalSource(ABC):
    @abstractmethod
    def poll(self) -> list[Signal]:
        """Return all signals newer than the last poll. Must be idempotent per-id."""
        ...

"""VenueExecutor abstract base. Concrete subclasses talk to a single venue."""
from __future__ import annotations
from abc import ABC, abstractmethod
from trumptrade.orders.order import Order


class VenueExecutor(ABC):
    venue: str

    @abstractmethod
    def submit(self, order: Order) -> Order:
        """Submit an order. Mutates+returns the order with status updated."""
        ...

    @abstractmethod
    def cancel(self, order: Order) -> Order:
        ...

    def supports_close(self) -> bool:
        """Whether this executor accepts SELL_YES / SELL_NO orders directly.
        Override if a venue requires position-level close semantics instead."""
        return True

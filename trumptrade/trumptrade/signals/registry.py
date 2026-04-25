"""SourceRegistry: register / unregister / query signal sources at runtime.

Two ways to populate:
  - Programmatic: `registry.register(my_source, my_metadata)`
  - Config-driven: load from `config/sources.yaml`
"""
from __future__ import annotations
from pathlib import Path
from typing import Iterator
import yaml
from trumptrade.signals.base import SignalSource
from trumptrade.signals.metadata import SourceMetadata


class SourceNotFound(KeyError):
    pass


class SourceAlreadyRegistered(ValueError):
    pass


class SourceRegistry:
    def __init__(self):
        self._sources: dict[str, tuple[SignalSource, SourceMetadata]] = {}

    def register(self, source: SignalSource, metadata: SourceMetadata) -> None:
        if metadata.name in self._sources:
            raise SourceAlreadyRegistered(metadata.name)
        self._sources[metadata.name] = (source, metadata)

    def unregister(self, name: str) -> None:
        if name not in self._sources:
            raise SourceNotFound(name)
        del self._sources[name]

    def get(self, name: str) -> tuple[SignalSource, SourceMetadata]:
        if name not in self._sources:
            raise SourceNotFound(name)
        return self._sources[name]

    def __contains__(self, name: str) -> bool:
        return name in self._sources

    def __len__(self) -> int:
        return len(self._sources)

    def all(self) -> Iterator[tuple[SignalSource, SourceMetadata]]:
        return iter(self._sources.values())

    def query(
        self,
        domain: str | None = None,
        market: str | None = None,
        industry: str | None = None,
    ) -> list[tuple[SignalSource, SourceMetadata]]:
        return [(s, m) for s, m in self._sources.values() if m.matches(domain, market, industry)]

    def poll_all(self) -> dict[str, list]:
        """Poll every registered source. Returns {source_name: [Signal, ...]}."""
        out = {}
        for src, meta in self._sources.values():
            try:
                out[meta.name] = src.poll()
            except NotImplementedError:
                out[meta.name] = []
        return out

    @classmethod
    def from_yaml(cls, path: Path) -> "SourceRegistry":
        """Load sources declared in a YAML manifest. Each entry:
            - name: my-rss
              factory: trumptrade.signals.rss:RSSFeedSource
              args: {url: https://example.com/feed}
              metadata:
                domain: us_policy
                markets: [us_equities]
                industries: [energy]
                update_cadence: minutes
                auth_required: false
                cost_per_request_usd: 0
                reliability: 1.0
                description: WH press feed
        """
        registry = cls()
        with open(path) as f:
            spec = yaml.safe_load(f) or {}
        for entry in spec.get("sources", []):
            registry.register(
                _instantiate(entry["factory"], entry.get("args", {})),
                SourceMetadata(name=entry["name"], **entry["metadata"]),
            )
        return registry


def _instantiate(dotted: str, kwargs: dict):
    """Resolve `module.path:Class` and call Class(**kwargs)."""
    if ":" not in dotted:
        raise ValueError(f"factory must be 'module.path:ClassName', got {dotted!r}")
    module_path, cls_name = dotted.split(":", 1)
    mod = __import__(module_path, fromlist=[cls_name])
    cls = getattr(mod, cls_name)
    return cls(**kwargs)

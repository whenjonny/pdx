from __future__ import annotations
import time
import logging
from pathlib import Path
from typing import Callable
import anthropic
from trumptrade.config import load_playbook, data_dir
from trumptrade.signals.base import SignalSource
from trumptrade.classifier import classify
from trumptrade.execution import expand_basket, Alerter
from trumptrade.types import Classification, Signal

log = logging.getLogger(__name__)

# Type alias for a classifier function (so tests can inject a fake)
ClassifyFn = Callable[[Signal, dict], Classification]


class Pipeline:
    def __init__(
        self,
        source: SignalSource,
        playbook: dict | None = None,
        alerter: Alerter | None = None,
        client: anthropic.Anthropic | None = None,
        classify_fn: ClassifyFn | None = None,
    ):
        self.source = source
        self.playbook = playbook or load_playbook()
        self.alerter = alerter or Alerter(
            min_confidence=self.playbook.get("risk_gates", {}).get("min_confidence_to_alert", 0.55),
            log_path=data_dir() / "alerts.jsonl",
        )
        self._client = client
        self._classify_fn = classify_fn or self._default_classify

    def _default_classify(self, signal: Signal, playbook: dict) -> Classification:
        return classify(signal, playbook, client=self._client)

    def run_once(self) -> int:
        signals = self.source.poll()
        if not signals:
            return 0
        count = 0
        for sig in signals:
            log.info("processing signal %s", sig.id)
            classification = self._classify_fn(sig, self.playbook)
            basket = expand_basket(classification, self.playbook)
            if self.alerter.maybe_emit(sig, classification, basket):
                count += 1
        return count

    def run_loop(self, interval_sec: int = 30) -> None:
        log.info("starting watch loop, polling every %ds", interval_sec)
        try:
            while True:
                n = self.run_once()
                log.info("processed %d new signal(s)", n)
                time.sleep(interval_sec)
        except KeyboardInterrupt:
            log.info("stopped by user")

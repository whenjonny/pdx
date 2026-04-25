"""TradePipeline: end-to-end, paper-mode by default.

  SourceRegistry.poll_all()
       └── for each Signal:
              └── for each Agent in [PolicyAgent, ArbAgent, ...]:
                     decisions = agent.analyze(signal, ctx)
                     log -> DecisionStore
                     route -> OrderRouter -> OrderStore + PositionStore

Every step is logged. The pipeline never modifies positions directly — it
goes through the OrderRouter so risk gates, executors, and reconciliation
all run consistently with the live path.
"""
from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from trumptrade.agents.base import Agent, AgentContext, TradeDecision
from trumptrade.signals.registry import SourceRegistry
from trumptrade.orders.router import OrderRouter
from trumptrade.pipelines.signal_log import SignalLog
from trumptrade.decisions import DecisionStore
from trumptrade.types import Signal

log = logging.getLogger(__name__)


@dataclass
class TickResult:
    timestamp: datetime
    signals: int = 0
    new_decisions: int = 0
    accepted: int = 0
    rejected: int = 0
    errors: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    by_agent: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"[{self.timestamp.isoformat(timespec='seconds')}] "
            f"signals={self.signals} decisions={self.new_decisions} "
            f"accepted={self.accepted} rejected={self.rejected} errors={self.errors} "
            f"by_source={self.by_source} by_agent={self.by_agent}"
        )


class TradePipeline:
    def __init__(
        self,
        source_registry: SourceRegistry,
        agents: list[Agent],
        router: OrderRouter,
        agent_ctx: AgentContext,
        signal_log: SignalLog | None = None,
        decision_store: DecisionStore | None = None,
    ):
        self.sources = source_registry
        self.agents = list(agents)
        self.router = router
        self.ctx = agent_ctx
        self.signal_log = signal_log
        self.decision_store = decision_store

    def run_once(self) -> TickResult:
        result = TickResult(timestamp=datetime.now(timezone.utc))
        try:
            polled = self.sources.poll_all()
        except Exception as e:
            log.exception("source poll failed: %s", e)
            result.errors += 1
            return result

        all_decisions: list[TradeDecision] = []
        for source_name, signals in polled.items():
            if not signals:
                continue
            result.signals += len(signals)
            result.by_source[source_name] = len(signals)
            if self.signal_log is not None:
                self.signal_log.record_many(source_name, signals)
            for sig in signals:
                for agent in self.agents:
                    try:
                        decisions = agent.analyze(sig, self.ctx)
                    except Exception as e:
                        log.exception("agent %s failed on %s: %s", agent.name, sig.id, e)
                        result.errors += 1
                        continue
                    if not decisions:
                        continue
                    result.by_agent[agent.name] = result.by_agent.get(agent.name, 0) + len(decisions)
                    if self.decision_store is not None:
                        self.decision_store.record_many(decisions)
                    all_decisions.extend(decisions)
        result.new_decisions = len(all_decisions)

        if all_decisions:
            outcomes = self.router.route(all_decisions)
            for o in outcomes:
                if o.accepted:
                    result.accepted += 1
                else:
                    result.rejected += 1
        return result

    def run_forever(self, interval_sec: int = 30) -> None:
        log.info("trade pipeline started, interval=%ds", interval_sec)
        try:
            while True:
                tick = self.run_once()
                log.info("%s", tick.summary())
                time.sleep(interval_sec)
        except KeyboardInterrupt:
            log.info("trade pipeline stopped by user")

"""Result-summary reporter. Reads jsonl logs (signals/decisions/orders/
positions) and computes the headline numbers a TL would ask for:

  - signals: total observed, by source, by domain
  - decisions: total emitted, by agent, action mix
  - orders: total submitted, fill rate, rejected reasons
  - positions: open / closed counts, win rate, avg win/loss, P&L curve
  - risk: current usage vs caps
  - by-category: signal -> decision -> filled order -> realized P&L

No external deps beyond stdlib + pydantic types we already have.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class SummaryReport:
    generated_at: datetime
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None

    # signals
    n_signals: int = 0
    signals_by_source: dict[str, int] = field(default_factory=dict)

    # decisions
    n_decisions: int = 0
    decisions_by_agent: dict[str, int] = field(default_factory=dict)
    decisions_by_action: dict[str, int] = field(default_factory=dict)

    # orders
    n_orders: int = 0
    orders_by_status: dict[str, int] = field(default_factory=dict)
    fill_rate: float = 0.0
    rejected_top_reasons: list[tuple[str, int]] = field(default_factory=list)

    # positions
    n_open: int = 0
    n_closed: int = 0
    n_winning: int = 0
    n_losing: int = 0
    win_rate: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    by_exit_reason: dict[str, int] = field(default_factory=dict)
    by_venue: dict[str, dict[str, float]] = field(default_factory=dict)

    def render_text(self) -> str:
        lines = [
            "================================================================",
            "  TRUMPTRADE — RESULT SUMMARY",
            f"  generated_at : {self.generated_at.isoformat(timespec='seconds')}",
        ]
        if self.window_start and self.window_end:
            lines.append(f"  window       : {self.window_start.isoformat(timespec='minutes')}"
                         f" -> {self.window_end.isoformat(timespec='minutes')}")
        lines.append("================================================================")

        lines.append("\n[SIGNALS]")
        lines.append(f"  total: {self.n_signals}")
        for src, n in sorted(self.signals_by_source.items(), key=lambda kv: -kv[1]):
            lines.append(f"    {src:30s} {n}")

        lines.append("\n[DECISIONS]")
        lines.append(f"  total: {self.n_decisions}")
        lines.append(f"  by agent : {dict(self.decisions_by_agent)}")
        lines.append(f"  by action: {dict(self.decisions_by_action)}")

        lines.append("\n[ORDERS]")
        lines.append(f"  total: {self.n_orders}   fill_rate: {self.fill_rate:.1%}")
        for st, n in sorted(self.orders_by_status.items(), key=lambda kv: -kv[1]):
            lines.append(f"    {st:18s} {n}")
        if self.rejected_top_reasons:
            lines.append("  top rejection reasons:")
            for reason, n in self.rejected_top_reasons:
                lines.append(f"    {reason:30s} {n}")

        lines.append("\n[POSITIONS]")
        lines.append(f"  open      : {self.n_open}")
        lines.append(f"  closed    : {self.n_closed}")
        lines.append(f"  winning   : {self.n_winning}")
        lines.append(f"  losing    : {self.n_losing}")
        lines.append(f"  win rate  : {self.win_rate:.1%}")
        lines.append(f"  realized  : ${self.realized_pnl:+,.2f}")
        lines.append(f"  unrealized: ${self.unrealized_pnl:+,.2f}")
        lines.append(f"  avg win   : ${self.avg_win:+,.2f}    avg loss   : ${self.avg_loss:+,.2f}")
        lines.append(f"  best win  : ${self.largest_win:+,.2f}    worst loss : ${self.largest_loss:+,.2f}")
        if self.by_exit_reason:
            lines.append("  by exit reason:")
            for r, n in sorted(self.by_exit_reason.items(), key=lambda kv: -kv[1]):
                lines.append(f"    {r:20s} {n}")
        if self.by_venue:
            lines.append("  by venue:")
            for v, m in sorted(self.by_venue.items()):
                lines.append(f"    {v:15s} positions={int(m['positions'])}  "
                             f"realized=${m['realized']:+,.2f}  "
                             f"open_notional=${m['open_notional']:,.2f}")

        lines.append("\n================================================================")
        return "\n".join(lines)


def build_summary(data_dir: Path | str) -> SummaryReport:
    import json
    p = Path(data_dir)

    rep = SummaryReport(generated_at=datetime.now(timezone.utc))

    # --- signals
    sig_path = p / "signals.jsonl"
    if sig_path.exists():
        timestamps: list[datetime] = []
        for line in sig_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            rep.n_signals += 1
            src = row.get("source") or "?"
            rep.signals_by_source[src] = rep.signals_by_source.get(src, 0) + 1
            ts_raw = (row.get("signal") or {}).get("timestamp")
            if ts_raw:
                try:
                    timestamps.append(datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")))
                except Exception:
                    pass
        if timestamps:
            rep.window_start = min(timestamps)
            rep.window_end = max(timestamps)

    # --- decisions
    dec_path = p / "decisions.jsonl"
    if dec_path.exists():
        for line in dec_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            rep.n_decisions += 1
            rep.decisions_by_agent[d.get("agent_name", "?")] = rep.decisions_by_agent.get(d.get("agent_name", "?"), 0) + 1
            rep.decisions_by_action[d.get("action", "?")] = rep.decisions_by_action.get(d.get("action", "?"), 0) + 1

    # --- orders
    ord_path = p / "orders.jsonl"
    latest_orders: dict[str, dict] = {}
    if ord_path.exists():
        for line in ord_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            latest_orders[o["id"]] = o    # later entries win
        rep.n_orders = len(latest_orders)
        statuses = Counter(o["status"] for o in latest_orders.values())
        rep.orders_by_status = dict(statuses)
        n_filled = statuses.get("filled", 0) + statuses.get("partially_filled", 0)
        rep.fill_rate = (n_filled / rep.n_orders) if rep.n_orders else 0.0
        # top rejection reasons
        rejected = [o for o in latest_orders.values() if o["status"] == "rejected"]
        reasons = Counter((o.get("error") or "?") for o in rejected)
        rep.rejected_top_reasons = reasons.most_common(5)

    # --- positions
    pos_path = p / "positions.jsonl"
    latest_pos: dict[str, dict] = {}
    if pos_path.exists():
        for line in pos_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                pdata = json.loads(line)
            except Exception:
                continue
            latest_pos[pdata["id"]] = pdata
    open_pos = [p for p in latest_pos.values() if p.get("status") == "open"]
    closed_pos = [p for p in latest_pos.values() if p.get("status") == "closed"]
    rep.n_open = len(open_pos)
    rep.n_closed = len(closed_pos)

    wins = [p for p in closed_pos if (p.get("realized_pnl") or 0.0) > 0]
    losses = [p for p in closed_pos if (p.get("realized_pnl") or 0.0) <= 0]
    rep.n_winning = len(wins)
    rep.n_losing = len(losses)
    rep.win_rate = (len(wins) / len(closed_pos)) if closed_pos else 0.0
    rep.realized_pnl = sum((p.get("realized_pnl") or 0.0) for p in closed_pos)
    # Unrealized P&L. For BUY_YES, mark is the current YES mid; for BUY_NO,
    # mark is the current NO mid. The store records current_mark on whichever
    # side the position is in, so (mark - entry) * size is correct for both.
    rep.unrealized_pnl = sum(
        ((p.get("current_mark") or p.get("entry_price") or 0.0) - (p.get("entry_price") or 0.0))
        * (p.get("size_contracts") or 0)
        for p in open_pos
    )
    rep.avg_win = (sum(p.get("realized_pnl") or 0.0 for p in wins) / len(wins)) if wins else 0.0
    rep.avg_loss = (sum(p.get("realized_pnl") or 0.0 for p in losses) / len(losses)) if losses else 0.0
    rep.largest_win = max((p.get("realized_pnl") or 0.0) for p in wins) if wins else 0.0
    rep.largest_loss = min((p.get("realized_pnl") or 0.0) for p in losses) if losses else 0.0

    by_reason = Counter(p.get("exit_reason") or "?" for p in closed_pos)
    rep.by_exit_reason = dict(by_reason)

    by_venue = defaultdict(lambda: {"positions": 0, "realized": 0.0, "open_notional": 0.0})
    for p in latest_pos.values():
        v = p.get("venue") or "?"
        by_venue[v]["positions"] += 1
        if p.get("status") == "closed":
            by_venue[v]["realized"] += (p.get("realized_pnl") or 0.0)
        else:
            by_venue[v]["open_notional"] += (p.get("entry_price") or 0.0) * (p.get("size_contracts") or 0)
    rep.by_venue = {k: dict(v) for k, v in by_venue.items()}

    return rep

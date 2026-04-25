"""Research-grade analysis of the 2-hour paper run.
Reads data/*.jsonl and computes deeper statistics than the headline report."""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median, pstdev

DATA = Path("/home/user/pdx/trumptrade/data")


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def _latest_per_id(rows: list[dict], key: str = "id") -> dict[str, dict]:
    by_id = {}
    for r in rows:
        if key in r:
            by_id[r[key]] = r
    return by_id


def main():
    signals = _load(DATA / "signals.jsonl")
    decisions = _load(DATA / "decisions.jsonl")
    orders = list(_latest_per_id(_load(DATA / "orders.jsonl")).values())
    positions = list(_latest_per_id(_load(DATA / "positions.jsonl")).values())

    print("=" * 70)
    print("  RESEARCH ANALYSIS — 120-tick paper run")
    print("=" * 70)

    # ── Funnel ──────────────────────────────────────────────────
    print("\n[FUNNEL]")
    print(f"  signals -> decisions -> orders -> filled -> positions")
    n_filled = sum(1 for o in orders if o["status"] == "filled")
    n_rejected = sum(1 for o in orders if o["status"] == "rejected")
    print(f"    {len(signals)} -> {len(decisions)} -> {len(orders)} -> "
          f"{n_filled} -> {len(positions)}")
    print(f"  decision-to-order ratio : {len(orders)/max(len(decisions),1):.2%}")
    print(f"  order fill rate         : {n_filled/max(len(orders),1):.2%}")
    print(f"  risk reject rate        : {n_rejected/max(len(orders),1):.2%}")

    # ── Decision distribution ───────────────────────────────────
    print("\n[DECISION ATTRIBUTION]")
    by_agent = Counter(d.get("agent_name", "?") for d in decisions)
    for agent, n in by_agent.most_common():
        print(f"  {agent:10s} {n}  ({n/len(decisions):.0%})")

    by_category = Counter(d.get("category") for d in decisions if d.get("category"))
    print("\n[POLICY-CATEGORY ATTRIBUTION (policy agent only)]")
    for cat, n in by_category.most_common():
        print(f"  {cat:24s} {n}")

    # ── Risk-rejection analysis ─────────────────────────────────
    print("\n[RISK GATING]")
    rej = [o for o in orders if o["status"] == "rejected"]
    rej_reasons = Counter((o.get("error") or "?") for o in rej)
    for reason, n in rej_reasons.most_common(5):
        print(f"  {reason[:60]:60s} {n}")
    print(f"  -> {n_rejected} rejected of {len(orders)} total = "
          f"{n_rejected/max(len(orders),1):.1%}")

    # ── Position outcomes ───────────────────────────────────────
    print("\n[POSITION OUTCOMES]")
    closed = [p for p in positions if p.get("status") == "closed"]
    open_pos = [p for p in positions if p.get("status") == "open"]
    pnls = [p.get("realized_pnl") or 0.0 for p in closed]
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x <= 0]

    print(f"  closed positions   : {len(closed)}")
    print(f"  win rate           : {len(wins)/max(len(closed),1):.1%}")
    print(f"  realized P&L total : ${sum(pnls):+,.2f}")
    print(f"  realized mean      : ${mean(pnls) if pnls else 0:+,.2f}")
    print(f"  realized median    : ${median(pnls) if pnls else 0:+,.2f}")
    print(f"  realized stdev     : ${pstdev(pnls) if len(pnls) > 1 else 0:,.2f}")
    if wins:
        print(f"  avg win            : ${mean(wins):+,.2f}")
    if losses:
        print(f"  avg loss           : ${mean(losses):+,.2f}")
    if wins and losses:
        edge = mean(wins) / abs(mean(losses))
        print(f"  win/loss ratio     : {edge:.2f}x")
        # expectancy per trade
        p_win = len(wins) / len(closed)
        p_loss = 1 - p_win
        ev = p_win * mean(wins) + p_loss * mean(losses)
        print(f"  expectancy/trade   : ${ev:+,.2f}")
    print(f"  open positions     : {len(open_pos)}")
    if open_pos:
        unreal_total = sum(
            ((p.get("current_mark") or p.get("entry_price") or 0) - (p.get("entry_price") or 0))
            * (p.get("size_contracts") or 0)
            for p in open_pos
        )
        print(f"  open unreal P&L    : ${unreal_total:+,.2f}")
    print(f"  TOTAL mark-to-mkt  : ${sum(pnls) + (unreal_total if open_pos else 0):+,.2f}")

    # ── By venue ────────────────────────────────────────────────
    print("\n[VENUE PERFORMANCE]")
    by_venue = defaultdict(lambda: {"closed": 0, "wins": 0, "pnl": 0.0})
    for p in closed:
        v = p.get("venue", "?")
        by_venue[v]["closed"] += 1
        by_venue[v]["pnl"] += (p.get("realized_pnl") or 0)
        if (p.get("realized_pnl") or 0) > 0:
            by_venue[v]["wins"] += 1
    for v in sorted(by_venue):
        d = by_venue[v]
        wr = d["wins"] / max(d["closed"], 1)
        print(f"  {v:11s} closed={d['closed']:>3}  win_rate={wr:.0%}  P&L=${d['pnl']:+,.2f}")

    # ── By exit reason ──────────────────────────────────────────
    print("\n[EXIT-REASON PERFORMANCE]")
    by_reason = defaultdict(lambda: {"n": 0, "pnl": 0.0, "wins": 0})
    for p in closed:
        r = p.get("exit_reason") or "?"
        by_reason[r]["n"] += 1
        by_reason[r]["pnl"] += (p.get("realized_pnl") or 0)
        if (p.get("realized_pnl") or 0) > 0:
            by_reason[r]["wins"] += 1
    for r, d in sorted(by_reason.items(), key=lambda kv: -kv[1]["pnl"]):
        wr = d["wins"] / max(d["n"], 1)
        avg = d["pnl"] / max(d["n"], 1)
        print(f"  {r:18s} n={d['n']:>3}  win_rate={wr:.0%}  "
              f"avg_pnl=${avg:+,.2f}  total=${d['pnl']:+,.2f}")

    # ── Hold time ───────────────────────────────────────────────
    print("\n[HOLD TIME ANALYSIS]")
    from datetime import datetime
    holds = []
    for p in closed:
        try:
            o = datetime.fromisoformat(p["entry_at"].replace("Z", "+00:00"))
            c = datetime.fromisoformat(p["closed_at"].replace("Z", "+00:00"))
            holds.append((c - o).total_seconds())
        except Exception:
            pass
    if holds:
        print(f"  median hold (sec)  : {median(holds):.0f}")
        print(f"  mean hold (sec)    : {mean(holds):.0f}")
        print(f"  shortest           : {min(holds):.0f}s")
        print(f"  longest            : {max(holds):.0f}s")

    # ── Per-signal attribution ──────────────────────────────────
    print("\n[PER-SIGNAL ATTRIBUTION (top 10 by P&L)]")
    sig_pnl = defaultdict(float)
    sig_count = defaultdict(int)
    for p in closed:
        sid = p.get("source_signal_id") or "?"
        sig_pnl[sid] += (p.get("realized_pnl") or 0)
        sig_count[sid] += 1

    sig_text = {}
    for s in signals:
        sd = s.get("signal", {})
        sig_text[sd.get("id")] = (sd.get("text") or "")[:60]

    top = sorted(sig_pnl.items(), key=lambda kv: -kv[1])[:10]
    for sid, pnl in top:
        n = sig_count[sid]
        text = sig_text.get(sid, "(unknown)")
        print(f"  {sid:14s} closed={n:>2}  pnl=${pnl:+8.2f}  '{text}'")


if __name__ == "__main__":
    main()

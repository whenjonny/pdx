import json
from datetime import datetime, timezone
from pathlib import Path
from trumptrade.reports import build_summary


def test_empty_dir_yields_zero_report(tmp_path):
    rep = build_summary(tmp_path)
    assert rep.n_signals == 0
    assert rep.n_decisions == 0
    assert rep.n_orders == 0
    assert rep.n_open == 0
    assert rep.n_closed == 0
    assert rep.win_rate == 0.0


def _w(p: Path, lines: list[dict]) -> None:
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n")


def test_full_summary(tmp_path):
    # signals
    _w(tmp_path / "signals.jsonl", [
        {"source": "mock", "signal": {"id": "s1", "timestamp": "2026-04-21T10:00:00+00:00", "text": "x"}},
        {"source": "mock", "signal": {"id": "s2", "timestamp": "2026-04-22T10:00:00+00:00", "text": "y"}},
    ])
    # decisions
    _w(tmp_path / "decisions.jsonl", [
        {"id": "d1", "action": "open", "venue": "v", "market_id": "m", "agent_name": "policy",
         "side": "BUY_YES", "size_contracts": 10, "confidence": 0.6,
         "created_at": "2026-04-21T10:01:00"},
        {"id": "d2", "action": "close", "venue": "v", "market_id": "m", "agent_name": "exit",
         "side": "SELL_YES", "size_contracts": 10, "confidence": 1.0,
         "created_at": "2026-04-22T10:02:00"},
    ])
    # orders (3 entries: latest per id wins)
    _w(tmp_path / "orders.jsonl", [
        {"id": "o1", "venue": "v", "market_id": "m", "side": "BUY_YES",
         "qty_contracts": 10, "limit_price": 0.40, "status": "pending",
         "fills": [], "created_at": "2026-04-21T10:01:00"},
        {"id": "o1", "venue": "v", "market_id": "m", "side": "BUY_YES",
         "qty_contracts": 10, "limit_price": 0.40, "status": "filled",
         "fills": [{"fill_id": "f1", "qty": 10, "price": 0.40}],
         "created_at": "2026-04-21T10:01:00"},
        {"id": "o2", "venue": "v", "market_id": "m", "side": "BUY_YES",
         "qty_contracts": 5, "limit_price": 0.40, "status": "rejected",
         "fills": [], "created_at": "2026-04-21T10:01:30",
         "error": "max_per_position"},
    ])
    # positions (one closed win, one open)
    _w(tmp_path / "positions.jsonl", [
        {"id": "p1", "venue": "v", "market_id": "m", "market_title": "x",
         "side": "BUY_YES", "entry_price": 0.40, "size_contracts": 100,
         "entry_at": "2026-04-21T10:00:00+00:00",
         "status": "closed", "exit_reason": "take_profit",
         "exit_price": 0.55, "realized_pnl": 15.0,
         "closed_at": "2026-04-22T11:00:00+00:00"},
        {"id": "p2", "venue": "v", "market_id": "m2", "market_title": "y",
         "side": "BUY_YES", "entry_price": 0.30, "size_contracts": 50,
         "entry_at": "2026-04-22T10:00:00+00:00",
         "status": "open"},
    ])

    rep = build_summary(tmp_path)
    assert rep.n_signals == 2
    assert rep.signals_by_source == {"mock": 2}
    assert rep.n_decisions == 2
    assert rep.decisions_by_agent == {"policy": 1, "exit": 1}
    assert rep.decisions_by_action == {"open": 1, "close": 1}
    assert rep.n_orders == 2
    assert rep.orders_by_status["filled"] == 1
    assert rep.orders_by_status["rejected"] == 1
    assert 0.0 < rep.fill_rate < 1.0
    assert rep.n_open == 1
    assert rep.n_closed == 1
    assert rep.n_winning == 1
    assert rep.win_rate == 1.0
    assert rep.realized_pnl == 15.0
    assert rep.by_exit_reason == {"take_profit": 1}

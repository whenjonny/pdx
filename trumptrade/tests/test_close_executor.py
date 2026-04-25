from datetime import datetime, timezone
from pathlib import Path
from trumptrade.monitor import OpenPosition, CloseExecutor


def _pos():
    return OpenPosition(
        venue="polymarket", market_id="m1", market_title="t",
        side="BUY_YES", entry_price=0.40, size_contracts=100,
        entry_at=datetime.now(timezone.utc),
    )


def test_alert_mode_does_not_submit_anywhere(tmp_path: Path):
    log = tmp_path / "close.jsonl"
    e = CloseExecutor(mode="alert", log_path=log, venue_clients={})
    o = e.close(_pos(), price_hint=0.55, reason="take_profit", detail="hit target")
    assert o.reason == "take_profit"
    assert o.size_contracts == 100
    assert log.exists()
    contents = log.read_text().strip().splitlines()
    assert len(contents) == 1


def test_paper_mode_logs_no_broker_required(tmp_path: Path):
    e = CloseExecutor(mode="paper", log_path=tmp_path / "close.jsonl",
                      venue_clients={})  # no client needed in paper
    o = e.close(_pos(), price_hint=0.30, reason="stop_loss")
    assert o.reason == "stop_loss"


def test_live_mode_needs_wired_client():
    e = CloseExecutor(mode="live", log_path=None, venue_clients={})
    import pytest
    with pytest.raises(RuntimeError):
        e.close(_pos(), price_hint=0.30, reason="stop_loss")

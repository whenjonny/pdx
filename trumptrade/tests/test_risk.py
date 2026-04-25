from datetime import datetime, timezone, timedelta
from pathlib import Path
from trumptrade.monitor import OpenPosition, PositionStore
from trumptrade.risk import RiskLimits, RiskChecker


def _store(tmp_path):
    return PositionStore(tmp_path / "positions.jsonl")


def _make_pos(**overrides):
    base = dict(
        venue="polymarket", market_id="m1", market_title="t",
        side="BUY_YES", entry_price=0.40, size_contracts=100,
        entry_at=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return OpenPosition(**base)


def test_clean_account_allows_normal_trade(tmp_path):
    s = _store(tmp_path)
    limits = RiskLimits(account_value_usd=10_000, max_per_position_pct=0.05)
    chk = RiskChecker(limits, s)
    v = chk.check(venue="polymarket", category="tariff_china",
                  event_id="evt1", intended_notional=200.0)
    assert v.allowed
    assert v.notional_allowed >= 200.0


def test_blocks_oversized_single_position(tmp_path):
    s = _store(tmp_path)
    limits = RiskLimits(account_value_usd=10_000, max_per_position_pct=0.03)
    chk = RiskChecker(limits, s)
    # 5% of $10k = $500 > 3% cap -> block
    v = chk.check(venue="polymarket", category="x", event_id="e", intended_notional=500.0)
    assert not v.allowed
    assert any(b.rule == "max_per_position" for b in v.breaches)


def test_per_venue_cap(tmp_path):
    s = _store(tmp_path)
    limits = RiskLimits(account_value_usd=10_000, max_per_venue_pct=0.10,
                        max_per_position_pct=0.10)
    # already $900 open on polymarket
    s.open(_make_pos(entry_price=0.90, size_contracts=1000))   # $900 notional
    chk = RiskChecker(limits, s)
    # adding $200 more -> $1100 > $1000 venue cap
    v = chk.check(venue="polymarket", category="x", event_id="e", intended_notional=200.0)
    assert not v.allowed
    assert any(b.rule == "max_per_venue" for b in v.breaches)


def test_total_exposure_cap(tmp_path):
    s = _store(tmp_path)
    limits = RiskLimits(account_value_usd=10_000, max_total_exposure_pct=0.20,
                        max_per_venue_pct=1.0, max_per_position_pct=1.0)
    s.open(_make_pos(entry_price=0.90, size_contracts=2000))   # $1800
    chk = RiskChecker(limits, s)
    v = chk.check(venue="kalshi", category="x", event_id="e", intended_notional=300.0)
    assert not v.allowed
    assert any(b.rule == "max_total_exposure" for b in v.breaches)


def test_liquidity_gate(tmp_path):
    s = _store(tmp_path)
    limits = RiskLimits(min_market_volume_24h=5000.0)
    chk = RiskChecker(limits, s)
    v = chk.check(venue="polymarket", category="x", event_id="e",
                  intended_notional=100.0, market_volume_24h=500.0)
    assert not v.allowed
    assert any(b.rule == "min_market_volume_24h" for b in v.breaches)


def test_daily_loss_circuit_breaker(tmp_path):
    s = _store(tmp_path)
    limits = RiskLimits(account_value_usd=10_000, daily_loss_circuit_breaker_pct=0.05)
    # close a position with -$600 P&L today  (-6%, below -5% breaker)
    p = _make_pos()
    s.open(p)
    p.realized_pnl = -600.0
    p.status = "closed"
    p.closed_at = datetime.now(timezone.utc)
    p.exit_reason = "stop_loss"
    s.update(p)

    chk = RiskChecker(limits, s)
    v = chk.check(venue="polymarket", category="x", event_id="e", intended_notional=10.0)
    assert not v.allowed
    assert any(b.rule == "daily_loss_circuit_breaker" for b in v.breaches)

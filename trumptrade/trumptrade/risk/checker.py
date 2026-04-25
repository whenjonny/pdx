"""Pre-trade risk gate. Call .check(...) before opening any new position."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from typing import Optional
from trumptrade.monitor.position import OpenPosition
from trumptrade.risk.limits import RiskLimits


@dataclass
class RiskBreach:
    rule: str
    detail: str
    cap_value: Optional[float] = None
    actual_value: Optional[float] = None


@dataclass
class RiskVerdict:
    allowed: bool
    breaches: list[RiskBreach] = field(default_factory=list)
    notional_allowed: float = 0.0
    notes: list[str] = field(default_factory=list)


class RiskChecker:
    def __init__(self, limits: RiskLimits, store):
        self.limits = limits
        self.store = store

    def check(
        self,
        venue: str,
        category: str | None,
        event_id: str | None,
        intended_notional: float,
        market_volume_24h: Optional[float] = None,
    ) -> RiskVerdict:
        v = RiskVerdict(allowed=True)
        L = self.limits
        acct = L.account_value_usd

        open_positions = self.store.open_positions()

        # 1. account-level total exposure
        total_open_notional = sum(p.notional_at_entry for p in open_positions)
        if (total_open_notional + intended_notional) / acct > L.max_total_exposure_pct:
            v.breaches.append(RiskBreach(
                "max_total_exposure",
                "would exceed account total exposure cap",
                cap_value=L.max_total_exposure_pct * acct,
                actual_value=total_open_notional + intended_notional,
            ))

        # 2. per-venue exposure
        per_venue_notional = sum(p.notional_at_entry for p in open_positions if p.venue == venue)
        if (per_venue_notional + intended_notional) / acct > L.max_per_venue_pct:
            v.breaches.append(RiskBreach(
                "max_per_venue", f"would exceed per-venue cap on {venue!r}",
                cap_value=L.max_per_venue_pct * acct,
                actual_value=per_venue_notional + intended_notional,
            ))

        # 3. per-category exposure (uses source_alert_id metadata via .note for now;
        #    cleaner integration with the trumptrade pipeline later)
        if category:
            per_cat_notional = sum(
                p.notional_at_entry for p in open_positions
                if (p.note or "").startswith(f"category:{category}")
            )
            if (per_cat_notional + intended_notional) / acct > L.max_per_category_pct:
                v.breaches.append(RiskBreach(
                    "max_per_category",
                    f"would exceed per-category cap on {category!r}",
                    cap_value=L.max_per_category_pct * acct,
                    actual_value=per_cat_notional + intended_notional,
                ))

        # 4. per-event exposure (linked positions count toward same event)
        if event_id:
            per_event_notional = sum(
                p.notional_at_entry for p in open_positions
                if event_id in (p.market_id or "") or event_id in (p.note or "")
            )
            if (per_event_notional + intended_notional) / acct > L.max_per_event_pct:
                v.breaches.append(RiskBreach(
                    "max_per_event",
                    f"would exceed per-event cap on {event_id!r}",
                    cap_value=L.max_per_event_pct * acct,
                    actual_value=per_event_notional + intended_notional,
                ))

        # 5. per-position cap
        if intended_notional / acct > L.max_per_position_pct:
            v.breaches.append(RiskBreach(
                "max_per_position", "single position too large",
                cap_value=L.max_per_position_pct * acct,
                actual_value=intended_notional,
            ))

        # 6. open-position counts
        if len(open_positions) >= L.max_open_positions:
            v.breaches.append(RiskBreach(
                "max_open_positions", f"already at cap of {L.max_open_positions}",
            ))
        per_venue_count = sum(1 for p in open_positions if p.venue == venue)
        if per_venue_count >= L.max_open_per_venue:
            v.breaches.append(RiskBreach(
                "max_open_per_venue",
                f"already at venue cap of {L.max_open_per_venue} on {venue!r}",
            ))

        # 7. market liquidity gate
        if market_volume_24h is not None and market_volume_24h < L.min_market_volume_24h:
            v.breaches.append(RiskBreach(
                "min_market_volume_24h",
                f"24h volume {market_volume_24h:.0f} < min {L.min_market_volume_24h:.0f}",
                cap_value=L.min_market_volume_24h,
                actual_value=market_volume_24h,
            ))

        # 8. daily loss circuit breaker
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_realized = sum(
            (p.realized_pnl or 0.0)
            for p in self.store.closed_positions()
            if p.closed_at and p.closed_at >= today_start
        )
        if today_realized / acct < -L.daily_loss_circuit_breaker_pct:
            v.breaches.append(RiskBreach(
                "daily_loss_circuit_breaker",
                f"already down {today_realized:.2f} today, blocking new opens",
                cap_value=-L.daily_loss_circuit_breaker_pct * acct,
                actual_value=today_realized,
            ))

        v.allowed = len(v.breaches) == 0
        if v.allowed:
            v.notional_allowed = min(
                intended_notional,
                L.max_per_position_pct * acct,
                L.max_total_exposure_pct * acct - total_open_notional,
                L.max_per_venue_pct * acct - per_venue_notional,
            )
            v.notional_allowed = max(0.0, v.notional_allowed)
        return v

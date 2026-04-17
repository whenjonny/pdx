"""Fetch real Polymarket data and convert to backtest formats.

This module bridges the Polymarket API client with the backtest data
structures (MarketPath, MultiOutcomeSnapshot, CrossPlatformPath).

Usage:
    from pdx_backtest.historical_data import (
        fetch_binary_market_paths,
        fetch_negrisk_snapshots,
    )

    paths = fetch_binary_market_paths(n_markets=50)
    snapshots = fetch_negrisk_snapshots(min_outcomes=3)
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import numpy as np

from pdx_backtest.data import CrossPlatformPath, MarketPath, MultiOutcomeSnapshot
from pdx_backtest.polymarket_client import (
    EventInfo,
    MarketInfo,
    PriceCandle,
    fetch_events,
    fetch_markets,
    fetch_midpoints,
    fetch_multi_outcome_events,
    fetch_price_history,
)

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / "data_cache"


# ---------------------------------------------------------------------------
# Realistic fallback generators (calibrated to actual Polymarket statistics)
#
# These replace the original synthetic generators when the API is
# unreachable.  Key calibration differences from data.py generators:
#
#   - Binary: market noise ~0.6% (real Poly spread ~1.2% in 2025),
#     longshot bias 1% (not 3%), lag 1 step (not 3).
#   - NegRisk: opportunity rate 5% (not 15%), mispricing 1.5¢ (not 2¢),
#     so sum_yes deviates by ~1.5¢ only 1-in-20 snapshots.
#   - Cross-platform: spread 2.5¢ mean but only on a few steps,
#     not persistent.  Matches Ng et al. finding that spreads are
#     fleeting and most of the time venues are within 1¢.
# ---------------------------------------------------------------------------


def _generate_realistic_binary_path(
    n_steps: int = 500,
    initial_prob: float | None = None,
    seed: int = 0,
) -> MarketPath:
    """Binary market path calibrated to real Polymarket CLOB behaviour."""
    rng = np.random.default_rng(seed)
    if initial_prob is None:
        initial_prob = rng.uniform(0.10, 0.90)

    vol = rng.uniform(0.005, 0.018)
    shocks = rng.normal(0, vol, size=n_steps)
    true_prob = np.clip(initial_prob + np.cumsum(shocks), 0.001, 0.999)

    # Market price: 1-step lag, 0.6% noise, 1% longshot bias
    lagged = np.concatenate([[initial_prob], true_prob[:-1]])
    biased = lagged + 0.01 * (0.5 - lagged)
    noise = rng.normal(0, 0.006, size=n_steps)
    market_price = np.clip(biased + noise, 0.001, 0.999)

    outcome = int(rng.random() < true_prob[-1])
    return MarketPath(
        timestamps=np.arange(n_steps, dtype=float),
        true_prob=true_prob,
        market_price=market_price,
        outcome=outcome,
    )


def _generate_realistic_negrisk(
    n_outcomes: int = 5,
    n_snapshots: int = 200,
    seed: int = 0,
) -> list[MultiOutcomeSnapshot]:
    """NegRisk snapshots calibrated to IMDEA findings.

    ~5% of snapshots have an arbitrageable deviation of ~1.5¢.
    The rest are within noise of sum_yes ≈ 1.0.
    """
    rng = np.random.default_rng(seed)
    alpha = rng.uniform(0.5, 3.0, size=n_outcomes)
    true_probs = rng.dirichlet(alpha)
    winner = int(rng.choice(n_outcomes, p=true_probs))

    snapshots: list[MultiOutcomeSnapshot] = []
    for _ in range(n_snapshots):
        noisy = true_probs + rng.normal(0, 0.005, size=n_outcomes)
        noisy = np.clip(noisy, 0.005, 0.995)

        has_opportunity = rng.random() < 0.05
        if has_opportunity:
            bias = rng.choice([-1.0, 1.0]) * abs(rng.normal(0.015, 0.005))
        else:
            bias = rng.normal(0, 0.002)

        scale = (1.0 + bias) / noisy.sum()
        yes_prices = np.clip(noisy * scale, 0.005, 0.995)
        no_prices = np.clip(1.0 - yes_prices + rng.normal(0, 0.003, size=n_outcomes),
                            0.005, 0.995)

        snapshots.append(MultiOutcomeSnapshot(
            yes_prices=yes_prices,
            no_prices=no_prices,
            winner_index=winner,
        ))
    return snapshots


def _generate_realistic_cross_platform(
    n_steps: int = 500,
    seed: int = 0,
) -> CrossPlatformPath:
    """Cross-platform path with realistic fleeting spreads."""
    rng = np.random.default_rng(seed)
    initial = rng.uniform(0.20, 0.80)
    vol = rng.uniform(0.006, 0.015)
    shocks = rng.normal(0, vol, size=n_steps)
    true_prob = np.clip(initial + np.cumsum(shocks), 0.001, 0.999)

    price_a = true_prob + rng.normal(0, 0.003, size=n_steps)
    lagged = np.concatenate([np.full(4, initial), true_prob[:-4]])
    # Most of the time venues are within 1¢; ~8% of steps have wider gap
    spread = rng.normal(0.005, 0.003, size=n_steps)
    spike_mask = rng.random(n_steps) < 0.08
    spread[spike_mask] = rng.normal(0.020, 0.006, size=spike_mask.sum())
    price_b = lagged + spread

    price_a = np.clip(price_a, 0.001, 0.999)
    price_b = np.clip(price_b, 0.001, 0.999)
    outcome = int(rng.random() < true_prob[-1])

    return CrossPlatformPath(
        timestamps=np.arange(n_steps, dtype=float),
        price_a=price_a,
        price_b=price_b,
        true_prob=true_prob,
        outcome=outcome,
    )


def _ensure_cache_dir() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def _cache_path(key: str) -> Path:
    return _ensure_cache_dir() / f"{key}.json"


def _load_cache(key: str, max_age_hours: float = 24.0) -> Optional[list | dict]:
    p = _cache_path(key)
    if not p.exists():
        return None
    age_hours = (time.time() - p.stat().st_mtime) / 3600
    if age_hours > max_age_hours:
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _save_cache(key: str, data: list | dict) -> None:
    _cache_path(key).write_text(json.dumps(data))


# ---------------------------------------------------------------------------
# Convert price candles → MarketPath
# ---------------------------------------------------------------------------


def _candles_to_market_path(
    candles: list[PriceCandle],
    outcome: int = -1,
    market_info: Optional[MarketInfo] = None,
) -> MarketPath:
    """Convert OHLC candles to a MarketPath.

    Since we only have market prices (no "true probability"), we derive
    a smoothed estimate using an EMA as a proxy for the true probability.
    The raw close prices become market_price.
    """
    if not candles:
        raise ValueError("Empty candle list")

    timestamps = np.array([c.timestamp for c in candles], dtype=float)
    close_prices = np.array([c.close for c in candles], dtype=float)
    close_prices = np.clip(close_prices, 0.001, 0.999)

    # EMA as proxy for "true" probability (removes noise)
    alpha = 2.0 / (min(20, len(candles)) + 1)
    ema = np.zeros_like(close_prices)
    ema[0] = close_prices[0]
    for i in range(1, len(ema)):
        ema[i] = alpha * close_prices[i] + (1 - alpha) * ema[i - 1]
    true_prob = np.clip(ema, 0.001, 0.999)

    # Determine outcome from final price if not provided
    if outcome < 0:
        if market_info and market_info.closed:
            final_price = close_prices[-1]
            outcome = 1 if final_price > 0.5 else 0
        else:
            outcome = 1 if close_prices[-1] > 0.5 else 0

    return MarketPath(
        timestamps=timestamps,
        true_prob=true_prob,
        market_price=close_prices,
        outcome=outcome,
    )


# ---------------------------------------------------------------------------
# Fetch binary market paths
# ---------------------------------------------------------------------------


def fetch_binary_market_paths(
    n_markets: int = 50,
    min_volume: float = 10_000,
    interval: str = "max",
    fidelity: int = 60,
    use_cache: bool = True,
    include_closed: bool = True,
) -> list[MarketPath]:
    """Fetch real price histories from Polymarket binary markets.

    Falls back to realistically-calibrated synthetic data if the API is
    unreachable (e.g. in a sandboxed environment).
    """
    logger.info("Fetching binary market listings from Polymarket…")

    try:
        markets: list[MarketInfo] = []
        offset = 0
        while len(markets) < n_markets * 2:
            batch = fetch_markets(
                limit=100, active=True, closed=include_closed,
                order="volume", ascending=False, offset=offset,
            )
            if not batch:
                break
            markets.extend(m for m in batch if m.is_binary and m.volume >= min_volume)
            offset += 100
    except Exception as exc:
        logger.warning("API unreachable (%s) — using realistic fallback data", exc)
        paths = [_generate_realistic_binary_path(n_steps=500, seed=i)
                 for i in range(n_markets)]
        logger.info("Generated %d realistic fallback binary paths", len(paths))
        return paths

    markets = markets[:n_markets * 2]
    logger.info("Found %d binary markets with volume >= $%.0f", len(markets), min_volume)

    paths: list[MarketPath] = []
    for m in markets:
        if len(paths) >= n_markets:
            break
        if not m.token_ids:
            continue

        token_id = m.token_ids[0]
        cache_key = f"candles_{token_id}_{interval}_{fidelity}"

        cached = _load_cache(cache_key) if use_cache else None
        if cached is not None:
            candles = [PriceCandle(**c) for c in cached]
        else:
            try:
                candles = fetch_price_history(token_id, interval=interval,
                                              fidelity=fidelity)
                if use_cache and candles:
                    _save_cache(cache_key, [
                        {"timestamp": c.timestamp, "open": c.open, "high": c.high,
                         "low": c.low, "close": c.close, "volume": c.volume}
                        for c in candles
                    ])
            except Exception as exc:
                logger.warning("Failed to fetch history for %s: %s", m.slug, exc)
                continue

        if len(candles) < 10:
            continue

        try:
            path = _candles_to_market_path(candles, market_info=m)
            paths.append(path)
            logger.debug("Loaded %s: %d candles", m.slug, len(candles))
        except Exception as exc:
            logger.warning("Failed to convert %s: %s", m.slug, exc)

    if not paths:
        logger.warning("No real data fetched — using realistic fallback data")
        paths = [_generate_realistic_binary_path(n_steps=500, seed=i)
                 for i in range(n_markets)]

    logger.info("Successfully loaded %d binary market paths", len(paths))
    return paths


# ---------------------------------------------------------------------------
# Fetch NegRisk (multi-outcome) snapshots
# ---------------------------------------------------------------------------


def fetch_negrisk_snapshots(
    min_outcomes: int = 3,
    max_events: int = 20,
    use_cache: bool = True,
) -> list[list[MultiOutcomeSnapshot]]:
    """Fetch multi-outcome event data and build NegRisk snapshot sequences.

    Falls back to realistically-calibrated synthetic data if the API is
    unreachable.
    """
    logger.info("Fetching multi-outcome events from Polymarket…")
    try:
        events = fetch_multi_outcome_events(min_markets=min_outcomes, limit=50)
    except Exception as exc:
        logger.warning("API unreachable (%s) — using realistic NegRisk fallback", exc)
        sequences = []
        for i in range(max_events):
            n_outcomes = np.random.default_rng(i).integers(3, 8)
            seq = _generate_realistic_negrisk(n_outcomes=n_outcomes,
                                               n_snapshots=200, seed=i)
            sequences.append(seq)
        logger.info("Generated %d realistic NegRisk sequences", len(sequences))
        return sequences

    events = events[:max_events]
    logger.info("Found %d multi-outcome events", len(events))

    all_snapshot_sequences: list[list[MultiOutcomeSnapshot]] = []

    for event in events:
        if len(event.markets) < min_outcomes:
            continue

        # Fetch price history for each outcome
        outcome_candles: dict[int, list[PriceCandle]] = {}
        for idx, m in enumerate(event.markets):
            if not m.token_ids:
                continue
            token_id = m.token_ids[0]
            cache_key = f"negrisk_{token_id}_max_60"

            cached = _load_cache(cache_key) if use_cache else None
            if cached is not None:
                candles = [PriceCandle(**c) for c in cached]
            else:
                try:
                    candles = fetch_price_history(token_id, interval="max",
                                                  fidelity=60)
                    if use_cache and candles:
                        _save_cache(cache_key, [
                            {"timestamp": c.timestamp, "open": c.open,
                             "high": c.high, "low": c.low, "close": c.close,
                             "volume": c.volume}
                            for c in candles
                        ])
                except Exception as exc:
                    logger.warning("Failed to fetch %s: %s", m.slug, exc)
                    continue

            if candles:
                outcome_candles[idx] = candles

        if len(outcome_candles) < min_outcomes:
            continue

        # Time-align candles by timestamp
        all_timestamps: set[int] = set()
        for candles in outcome_candles.values():
            all_timestamps.update(c.timestamp for c in candles)
        sorted_ts = sorted(all_timestamps)

        # Build price lookup per outcome
        price_lookup: dict[int, dict[int, float]] = {}
        for idx, candles in outcome_candles.items():
            price_lookup[idx] = {c.timestamp: c.close for c in candles}

        outcome_indices = sorted(outcome_candles.keys())
        n_outcomes = len(outcome_indices)

        # Determine winner (highest final price)
        final_prices = []
        for idx in outcome_indices:
            last_candle = outcome_candles[idx][-1]
            final_prices.append(last_candle.close)
        winner_idx = int(np.argmax(final_prices))

        snapshots: list[MultiOutcomeSnapshot] = []
        for ts in sorted_ts:
            yes_prices = np.zeros(n_outcomes)
            for i, idx in enumerate(outcome_indices):
                yes_prices[i] = price_lookup[idx].get(ts, 0.0)
            if (yes_prices == 0).any():
                continue

            yes_prices = np.clip(yes_prices, 0.005, 0.995)
            no_prices = np.clip(1.0 - yes_prices, 0.005, 0.995)

            snapshots.append(MultiOutcomeSnapshot(
                yes_prices=yes_prices,
                no_prices=no_prices,
                winner_index=winner_idx,
            ))

        if len(snapshots) >= 10:
            all_snapshot_sequences.append(snapshots)
            logger.info("Event '%s': %d snapshots, %d outcomes, sum_yes range [%.3f, %.3f]",
                        event.title, len(snapshots), n_outcomes,
                        min(s.sum_yes for s in snapshots),
                        max(s.sum_yes for s in snapshots))

    if not all_snapshot_sequences:
        logger.warning("No real NegRisk data — using realistic fallback")
        for i in range(max_events):
            n_outcomes = np.random.default_rng(i + 100).integers(3, 8)
            seq = _generate_realistic_negrisk(n_outcomes=n_outcomes,
                                               n_snapshots=200, seed=i + 100)
            all_snapshot_sequences.append(seq)

    logger.info("Loaded %d NegRisk snapshot sequences", len(all_snapshot_sequences))
    return all_snapshot_sequences


# ---------------------------------------------------------------------------
# Fetch cross-platform paths (Polymarket prices only — Kalshi is simulated)
# ---------------------------------------------------------------------------


def fetch_cross_platform_proxy_paths(
    n_markets: int = 20,
    kalshi_lag_minutes: int = 4,
    kalshi_spread_mean: float = 0.025,
    fidelity: int = 5,
    use_cache: bool = True,
) -> list[CrossPlatformPath]:
    """Build CrossPlatformPath using real Polymarket data + simulated Kalshi lag.

    Falls back to realistically-calibrated synthetic data if the API is
    unreachable.
    """
    logger.info("Fetching markets for cross-platform analysis…")
    try:
        markets = fetch_markets(limit=100, active=True, closed=True,
                                order="volume", ascending=False)
    except Exception as exc:
        logger.warning("API unreachable (%s) — using realistic cross-platform fallback", exc)
        paths = [_generate_realistic_cross_platform(n_steps=500, seed=i)
                 for i in range(n_markets)]
        logger.info("Generated %d realistic cross-platform paths", len(paths))
        return paths

    binary_markets = [m for m in markets if m.is_binary and m.volume >= 50_000]
    binary_markets = binary_markets[:n_markets * 2]

    paths: list[CrossPlatformPath] = []
    rng = np.random.default_rng(42)

    for m in binary_markets:
        if len(paths) >= n_markets:
            break
        if not m.token_ids:
            continue

        token_id = m.token_ids[0]
        cache_key = f"xplat_{token_id}_max_{fidelity}"

        cached = _load_cache(cache_key) if use_cache else None
        if cached is not None:
            candles = [PriceCandle(**c) for c in cached]
        else:
            try:
                candles = fetch_price_history(token_id, interval="max",
                                              fidelity=fidelity)
                if use_cache and candles:
                    _save_cache(cache_key, [
                        {"timestamp": c.timestamp, "open": c.open,
                         "high": c.high, "low": c.low, "close": c.close,
                         "volume": c.volume}
                        for c in candles
                    ])
            except Exception as exc:
                logger.warning("Failed: %s", exc)
                continue

        if len(candles) < 20:
            continue

        timestamps = np.array([c.timestamp for c in candles], dtype=float)
        price_a = np.array([c.close for c in candles], dtype=float)
        price_a = np.clip(price_a, 0.001, 0.999)

        # Simulate Kalshi: lag + spread + noise
        lag = kalshi_lag_minutes
        if lag > 0 and lag < len(price_a):
            lagged = np.concatenate([np.full(lag, price_a[0]), price_a[:-lag]])
        else:
            lagged = price_a.copy()
        spread_noise = rng.normal(kalshi_spread_mean, 0.006, size=len(price_a))
        price_b = np.clip(lagged + spread_noise, 0.001, 0.999)

        true_prob = price_a.copy()
        outcome = 1 if price_a[-1] > 0.5 else 0

        paths.append(CrossPlatformPath(
            timestamps=timestamps,
            price_a=price_a,
            price_b=price_b,
            true_prob=true_prob,
            outcome=outcome,
        ))

    if not paths:
        logger.warning("No real cross-platform data — using realistic fallback")
        paths = [_generate_realistic_cross_platform(n_steps=500, seed=i)
                 for i in range(n_markets)]

    logger.info("Built %d cross-platform paths", len(paths))
    return paths


# ---------------------------------------------------------------------------
# Live NegRisk snapshot (real-time)
# ---------------------------------------------------------------------------


def fetch_live_negrisk_snapshot(
    event: EventInfo,
) -> Optional[MultiOutcomeSnapshot]:
    """Fetch current prices for a multi-outcome event and return a snapshot."""
    token_ids = []
    for m in event.markets:
        if m.token_ids:
            token_ids.append(m.token_ids[0])
        else:
            return None

    if len(token_ids) < 3:
        return None

    try:
        midpoints = fetch_midpoints(token_ids)
    except Exception:
        return None

    yes_prices = np.array([midpoints.get(tid, 0.0) for tid in token_ids])
    if (yes_prices == 0).any():
        return None

    yes_prices = np.clip(yes_prices, 0.005, 0.995)
    no_prices = np.clip(1.0 - yes_prices, 0.005, 0.995)

    return MultiOutcomeSnapshot(
        yes_prices=yes_prices,
        no_prices=no_prices,
        winner_index=0,  # unknown during live trading
    )

# Cross-Venue Statistical Arbitrage: Polymarket <-> predictX

Detects and trades price discrepancies between Polymarket and predictX
prediction markets. Applies the YES-only filter discovered in backtest
forensics (YES-side win rate 54.9% vs NO-side 36.9%).

## Architecture

```
Polymarket (CLOB)          predictX (CPMM)
     │                          │
     └──── Price Feeds ─────────┘
                │
         Market Matcher (fuzzy question matching)
                │
         Spread Calculator (net after fees/slippage/settlement risk)
                │
         EMA Filter (persistent spreads only)
                │
         Kelly Sizing (fractional, capped)
                │
         Risk Manager (7 pre-trade checks)
                │
         Executor (paper/live)
                │
         Portfolio Tracker
```

## Quickstart

```bash
pip install numpy requests

# Backtest on synthetic data
python stat_arb/run_backtest.py --markets 30 --steps 500 --seeds 5

# Scan live markets (read-only)
python stat_arb/run_scanner.py --once

# Paper trading bot
python stat_arb/run_bot.py --dry-run --interval 10

# Live trading (requires env vars)
export PDX_RPC_URL=http://localhost:8545
export PDX_MARKET_ADDRESS=0x...
export PDX_USDC_ADDRESS=0x...
export PDX_PRIVATE_KEY=0x...
python stat_arb/run_bot.py --live --capital 10000
```

## Strategy

**Cross-venue mean reversion with lead-lag exploitation.**

Polymarket's CLOB has deeper liquidity and faster price discovery.
predictX's CPMM adjusts more slowly. When a price dislocation exceeds
the cost of fees + slippage + settlement risk, we buy on the cheaper
venue and hold to settlement.

### Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| min_net_spread_bps | 150 | Minimum profitable spread after all costs |
| kelly_fraction | 0.25 | Quarter-Kelly sizing |
| max_position_usd | 5,000 | Max per-trade |
| max_total_exposure | 50,000 | Max total across all positions |
| cooldown_s | 30 | Seconds between trades on same market |
| slippage_bps | 30 | Estimated execution slippage |
| settlement_risk_bps | 50 | Cross-venue settlement premium |

### Fee Structure

| Venue | Maker | Taker |
|-------|-------|-------|
| Polymarket | 0% | ~1% |
| predictX | — | 0.3% (0.1% with evidence) |

## Files

```
stat_arb/
├── pdx_arb/
│   ├── types.py              # Shared data types
│   ├── config.py             # Configuration
│   ├── portfolio.py          # P&L tracking
│   ├── feeds/
│   │   ├── polymarket.py     # Polymarket price feed
│   │   ├── predictx.py       # predictX price feed
│   │   └── matcher.py        # Cross-venue market matcher
│   ├── strategy/
│   │   ├── spread.py         # Net spread calculator
│   │   └── stat_arb.py       # Signal generation + sizing
│   ├── execution/
│   │   └── executor.py       # Order routing + execution
│   └── risk/
│       └── risk_manager.py   # 7 pre-trade risk checks
├── tests/
│   └── test_spread.py        # Unit + integration tests
├── run_scanner.py            # Read-only opportunity scanner
├── run_bot.py                # Full trading bot (paper/live)
└── run_backtest.py           # Synthetic data backtest
```

## Risk Management

7 pre-trade checks:
1. Portfolio drawdown limit (15%)
2. Daily loss limit ($5,000)
3. Max open positions (20)
4. Per-market exposure cap ($10,000)
5. Total exposure cap ($50,000)
6. Single trade size limit ($5,000)
7. Minimum edge threshold (150 bps)

Dynamic position sizing: multiplier scales 1.0→0.0 as drawdown
approaches the limit.

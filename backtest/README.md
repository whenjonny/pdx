# PDX Backtest — Prediction Market Arbitrage

Event-driven discrete-event simulation for prediction market trading strategies.
Production-grade execution friction, 13-check risk management, and order management system.

## Architecture

Two execution models, both using the same strategy library:

1. **Event-driven** (recommended): `EventEngine` dispatches `MarketTick`, `OrderFill`,
   `OrderReject`, `Settlement`, `RiskAlert` events via priority queue. Strategies
   react to events — no lookahead, no future information leakage.

2. **Time-series** (legacy, in `legacy/`): Simple per-step iteration.
   Superseded by the event-driven approach.

### Event-Driven Pipeline

```
MarketSimulator → MarketTick events
                     ↓
              Strategy._on_tick()
                     ↓
            OrderSubmitted event
                     ↓
         RiskManager (13 pre-trade checks)
                     ↓  (pass)           ↓ (fail)
         OMS executes with friction    OrderReject
                     ↓
              OrderFill event
                     ↓
         Portfolio position tracking
                     ↓
         Settlement → ClosedTrade PnL
```

### Execution Friction (applied at fill time)

- Bernoulli execution failure (2% default)
- Beta-distributed partial fills (mean 85%)
- Proportional slippage (0.3% of size)
- Square-root market impact
- Latency-based adverse price movement

### Risk Management (13 pre-trade checks)

Global halt, strategy halt, cooldown, rate limit, trade size, drawdown,
daily loss, portfolio notional, position count, per-strategy limits
(notional/loss/positions), concentration, liquidity.

Dynamic position sizing: size multiplier scales from 1.0→0.25 linearly
between 5% and 15% portfolio drawdown.

## Quickstart

```bash
pip install numpy scipy pandas pytest

# Event-driven backtest (primary)
python3 backtest/run_event_backtest.py

# Statistical arbitrage deep analysis
python3 backtest/analyze_stat_arb.py

# Trade-level forensics
python3 backtest/analyze_trades.py

# Basic vs Enhanced stat arb comparison
python3 backtest/compare_stat_arb.py

# Tests
python3 -m pytest backtest/tests -v
```

## Strategies

### Event-Driven Strategies

| Strategy | File | Description |
|----------|------|-------------|
| Enhanced Stat Arb | `strategies/enhanced_stat_arb.py` | YES-only EMA mean reversion (7x PnL vs basic) |
| Stat Arb | `strategies/event_strategies.py` | EMA-based mean reversion, both sides |
| NegRisk Rebalancer | `strategies/event_strategies.py` | Multi-outcome basket arbitrage |
| Single Binary | `strategies/event_strategies.py` | Binary market rebalancing |
| Cross-Venue Arb | `strategies/event_strategies.py` | Cross-platform price differences |
| Longshot Bias | `strategies/event_strategies.py` | Exploits favorite-longshot bias |

### Key Finding: YES-Only Filter

Trade-level forensics across 968 trades (5 seeds x 50 markets) revealed:

| Side | Trades | Win Rate | Total PnL |
|------|--------|----------|-----------|
| YES  | 461    | 54.9%    | +$31,229  |
| NO   | 507    | 36.9%    | -$20,664  |

Removing NO-side trades converts break-even into profitable:
- Mean PnL: $2,617 → $7,688 (2.9x)
- T-stat: +1.17 → +2.61 (significant at 95%)
- Positive runs: 6/10 → 8/10

### Time-Series Strategies (legacy, in legacy/)

NegRisk Rebalancer, Bayesian Market Maker, Statistical Arbitrage,
Time Arbitrage, Cross-Platform/Venue Arb, Longshot Bias, LVR Arb,
Cross-Asset Arb, Volatility Event.

## Files

```
backtest/
├── README.md
├── run_event_backtest.py          # Primary backtest runner (event-driven)
├── analyze_stat_arb.py            # Parameter sweeps & robustness analysis
├── analyze_trades.py              # Trade-level forensics
├── compare_stat_arb.py            # Basic vs Enhanced head-to-head
├── pdx_backtest/                  # Core library
│   ├── __init__.py
│   ├── data.py                    # Synthetic market data generation
│   ├── metrics.py                 # Sharpe / Sortino / Calmar / MDD / Kelly
│   ├── friction.py                # Execution friction model
│   ├── amm.py                     # CPMM mirroring PDXMarket.sol
│   ├── event_engine.py            # Event-driven simulation engine
│   ├── oms.py                     # Order management system
│   ├── portfolio.py               # Position & PnL tracking
│   ├── risk_manager.py            # 13-check risk manager
│   ├── engine.py                  # Legacy time-series engine
│   ├── polymarket_client.py       # Polymarket API client
│   ├── predict_fun_client.py      # predict.fun API client
│   ├── historical_data.py         # Real data fetching
│   ├── cross_venue_data.py        # Cross-venue data aggregation
│   ├── exchange_connector.py      # Live/paper trading connector
│   ├── live_sim.py                # Live simulation runner
│   └── strategies/
│       ├── base.py                # Strategy ABC + Trade/StrategyResult
│       ├── enhanced_stat_arb.py   # YES-only enhanced stat arb
│       ├── event_strategies.py    # 5 event-driven strategies
│       ├── stat_arb.py            # Time-series stat arb
│       ├── negrisk.py             # NegRisk rebalancer
│       ├── market_making.py       # Bayesian market maker
│       ├── single_binary.py       # Single binary rebalancer
│       ├── cross_platform.py      # Cross-platform arb
│       ├── cross_venue_arb.py     # Cross-venue arb
│       ├── cross_asset.py         # Cross-asset arb
│       ├── longshot_bias.py       # Longshot bias exploiter
│       ├── lvr_arb.py             # LVR-informed arb
│       ├── time_arb.py            # Time arb
│       └── vol_event.py           # Volatility event
├── tests/
│   ├── test_event_engine.py       # Event engine + integration tests (20)
│   ├── test_stat_arb_enhanced.py  # Enhanced stat arb tests (6)
│   ├── test_amm.py                # AMM tests
│   ├── test_metrics.py            # Metrics tests
│   ├── test_strategies.py         # Strategy tests
│   ├── test_new_strategies.py     # Extended strategy tests
│   └── test_real_data.py          # Real data integration tests
├── reports/                       # Generated reports
└── legacy/                        # Superseded time-series runners
    ├── run_backtest.py
    ├── run_realistic_backtest.py
    ├── run_full_analysis.py
    ├── run_risk_enhanced.py
    ├── run_real_backtest.py
    ├── run_live_trading.py
    └── run_cross_venue_sim.py
```

## Caveats

- **Synthetic data only.** Market data is generated to match Polymarket stylized
  facts (1.2% spread, 3-5 min lag, longshot bias). Not a forecast of live PnL.
- **Execution friction is modelled.** Fill rate ~83%, slippage, partial fills,
  and market impact are applied at order execution time.
- **Risk management is active.** 13 pre-trade checks reject ~17% of orders.
  Dynamic sizing reduces exposure during drawdowns.

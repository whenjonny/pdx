# PDX Backtest — Prediction-Market Arbitrage Strategies

Event-driven backtester for the four strategies identified in the
research brief.  Mirrors PDXMarket.sol's CPMM math so results are
directly transferable to the on-chain contract.

## Quickstart

```bash
# Install deps
pip install numpy scipy pandas pytest

# Run the full suite (single seed)
python3 backtest/run_backtest.py --report backtest/reports/run_001.md

# Robustness sweep across N seeds (distribution of outcomes)
python3 backtest/run_backtest.py --n-markets 50 --sweep 5

# Tests
python3 -m pytest backtest/tests -v
```

Output prints a comparison table (Sharpe / Sortino / Calmar / MDD /
profit-factor) and a detailed per-strategy breakdown.  A markdown
report can be emitted via `--report`.

## Strategies

| # | Strategy | File | Research anchor |
|---|----------|------|-----------------|
| 1 | NegRisk multi-outcome rebalancing | `strategies/negrisk.py` | IMDEA 2024-2025: $29 M realised profit |
| 2 | Bayesian CPMM market-making | `strategies/market_making.py` | Polymarket zero-maker-fee + rebates |
| 3 | Statistical arbitrage (half-Kelly) | `strategies/stat_arb.py` | Ludescher 2024; FiveThirtyEight vs PredictIt |
| 4 | Time arbitrage on long-dated certainties | `strategies/time_arb.py` | Capital-lockup premium thesis |

### 1. NegRisk rebalancer

Scans N-outcome markets; fires when `sum(YES) < 1 - threshold` (long
basket) or `sum(NO) < (N-1) - threshold` (short basket).  Trades are
guaranteed-profit by construction — the edge closes at settlement
regardless of outcome.

### 2. Bayesian market maker

Seeds a CPMM pool biased to a prior probability, then serves a mix
of informed and uninformed flow.  Tracks cash inflow, rebates, and
external token issuance so settlement PnL is exact (no MTM
double-counting).

### 3. Statistical arbitrage

Picks the single step with the largest `|p_model − p_market|` edge
per market, sizes via half-Kelly × 0.5 (quarter-Kelly), pays a
Kalshi-equivalent 1.2% taker fee, and settles at event resolution.

### 4. Time arbitrage

Buys long-dated near-certain YES (`fair_prob ≥ 0.75` with a ≥ 4¢
discount), holds for `settlement_days`, reports both absolute and
**annualised** returns so the capital-lockup premium is visible.

## Data model

`pdx_backtest/data.py` generates synthetic market data calibrated
to the stylised facts in the research:

- Polymarket 2025 mean bid/ask spread ≈ 1.2%
- Kalshi lags Polymarket by ~3–5 minutes at information inflection
- NegRisk mispricings are punctuated — 10–20% of snapshots in
  mature 5-way markets, not continuous.
- Long-shot / favourite bias: market price is pulled toward 0.5
  (Snowberg-Wolfers 2010)

No external data is fetched.  All seeds are deterministic.

## Metrics (`pdx_backtest/metrics.py`)

- Total return (dollar PnL / capital base — **not compounded**)
- CAGR (linear annualisation by default)
- Annualised volatility
- Sharpe, Sortino, Calmar
- Max drawdown on dollar equity curve
- Win rate, profit factor, gross P / L
- Kelly / half-Kelly helper

> Returns are per-trade ROIC by convention.  Compounding is turned
> off by default — this is the honest model for a recycled-capital
> arb book.  `compound=True` is available for portfolio-style runs.

## Sample output

```
Strategy                     trades  total        CAGR       Sharpe    Sortino   MDD       Win      PF
negrisk_rebalancer            2335   +2065.35%   +7748.4%   +93.61    +0.00    +0.00%   100%    inf
bayesian_market_maker         4000      +7.58%     +16.6%   +37.98   +22.89    -0.08%    90%    8.90
statistical_arbitrage          100     +74.96%     +39.0%    +0.65    +0.00   -64.93%    64%    1.15
time_arbitrage                   7      +1.14%      +0.3%    +3.73    +0.00    +0.00%   100%    inf
```

### Interpretation

1. **NegRisk** — eye-catching headline return is the "recycled $1k
   through 2,335 guaranteed arbs" model.  Realistic interpretation:
   avg per-trade ROIC ≈ 0.9%, always positive, never a loser by
   construction.  In the real Polymarket universe this edge is
   captured at sub-200 ms latency by competing bots — our number
   is an **upper bound** on an idealised catch-all strategy.

2. **Bayesian MM** — the "steady income" profile.  90% of steps are
   wins (fees), drawdown < 0.1%, ROI ≈ 7.58% across 20 markets.
   This most closely maps to PDX's own market-creator role.

3. **Statistical arbitrage** — genuine risk and genuine edge:
   Sharpe 0.65 with 64% win rate.  Much more capacity than NegRisk
   but requires a calibrated probability model to beat the market.

4. **Time arbitrage** — thin by count (7 trades on 100 markets) but
   consistently profitable.  Each trade earns the capital-lockup
   premium; annualisation shows only a modest excess return over
   the 4% risk-free rate.

### Robustness across seeds

5-seed sweep (`--sweep 5 --n-markets 50`):

```
Strategy                    mean_ret   std_ret   mean_sharpe   worst_case   best_case
negrisk_rebalancer         +1007.27%    43.80%      +93.51      +926.80%   +1059.62%
bayesian_market_maker         +7.46%     0.21%      +31.48        +7.11%       +7.69%
statistical_arbitrage        +68.35%   126.35%       +0.83       -42.82%     +313.24%
time_arbitrage                +0.54%     1.05%       +0.77        -0.80%       +1.52%
```

- **NegRisk** and **MM** have statistically tight distributions
  (low std, always positive) — confirmed edge.
- **Stat arb** mean is positive but the seed-to-seed variance is
  enormous; needs ≫ 100 markets to harvest.
- **Time arb** is marginal even in-sample; real-world viability
  depends heavily on catching the right mispriced near-certainties
  at scale.

## Files

```
backtest/
├── README.md                   <- this file
├── run_backtest.py             <- CLI entry point
├── pdx_backtest/
│   ├── __init__.py
│   ├── amm.py                  <- CPMM mirroring PDXMarket.sol
│   ├── data.py                 <- synthetic data generators
│   ├── engine.py               <- result aggregation
│   ├── metrics.py              <- Sharpe / Sortino / Calmar / MDD / Kelly
│   └── strategies/
│       ├── base.py             <- Strategy + Trade + StrategyResult
│       ├── negrisk.py          <- Strategy 1
│       ├── market_making.py    <- Strategy 2
│       ├── stat_arb.py         <- Strategy 3
│       └── time_arb.py         <- Strategy 4
├── tests/
│   ├── test_amm.py             <- CPMM invariants
│   ├── test_metrics.py         <- metric correctness + Kelly
│   └── test_strategies.py      <- per-strategy sanity
└── reports/                    <- markdown outputs
```

## Caveats

- **Synthetic data only.**  We don't ship historical Polymarket or
  Kalshi ticks.  Backtests prove the strategy logic is sound and
  the accounting is consistent with the on-chain CPMM; they do
  **not** forecast live P&L.
- **No transaction-latency modelling.**  NegRisk in particular is
  caught by bots in ≤ 200 ms in production; ignore nominal totals
  unless you believe you can win that race.
- **No predicate-failure modelling.**  Real NegRisk arbs can fail
  because one leg of the basket becomes illiquid mid-fill; the
  research note puts real capture at ~30-40% of detected opportunities.
- **Oracle-manipulation risk** (UMA $44 M secures $330 M TVL →
  15:1 ratio) is not modelled.  Apply your own haircut.

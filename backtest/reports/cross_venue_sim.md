# Cross-Venue Arbitrage Simulation Report

*2026-04-17 11:55*

## Summary

| Metric | Value |
|--------|-------|
| Simulated Duration | 5.0 hours |
| Ticks | 600 |
| Capital | $100,000 |
| Final Equity | $101,157.51 |
| Total PnL | $1,157.51 |
| Return | 1.16% |
| Closed Trades | 49 |

## Per-Strategy Breakdown

| Strategy | Trades | PnL | Avg PnL | Win Rate | Max Win | Max Loss |
|----------|--------|-----|---------|----------|---------|----------|
| live_cross_venue | 12 | $1374.93 | $114.58 | 100.0% | $484.22 | $29.21 |
| live_negrisk | 13 | $63.17 | $4.86 | 69.2% | $26.01 | $-17.66 |
| live_single_binary | 24 | $-280.59 | $-11.69 | 37.5% | $45.23 | $-195.12 |

## Venues

- **Polymarket** (Polygon / USDC): 0% maker fee
- **predict.fun** (Blast L2 / USDB): ~150 bps fee
- Settlement risk haircut: 50 bps (cross-chain bridge latency)

## Notes

- Simulated prices: Polymarket random walk + predict.fun lagged (1-3 ticks) with spread
- Cross-venue arb: trades when spread > 2 cents after all fees + settlement risk
- Other strategies (NegRisk, Single Binary) run in parallel as baseline comparison
- Positions auto-close after 60 ticks (~30 min simulated time)

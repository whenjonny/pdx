# Risk-Enhanced Backtest Report

## Calibration — Risk Profiles

| Strategy | Win Rate | Avg Win | Avg Loss | Kelly | Half-Kelly | Vol | Sharpe |
|----------|----------|---------|----------|-------|------------|-----|--------|
| cross_asset | 60.0% | $9.41 | $13.83 | 0.012 | 0.006 | 0.7802 | -0.18 |
| cross_platform | 100.0% | $7553.09 | $0.01 | 1.000 | 0.500 | 17.9935 | 0.42 |
| longshot | 0.0% | $0.00 | $0.00 | 0.000 | 0.000 | 0.0000 | 0.00 |
| negrisk | 100.0% | $2.23 | $0.01 | 1.000 | 0.500 | 0.0049 | 0.90 |
| single_binary | 100.0% | $13.80 | $0.01 | 1.000 | 0.500 | 0.0073 | 3.77 |
| stat_arb | 46.7% | $718.56 | $1155.66 | 0.000 | 0.000 | 0.9661 | -0.15 |
| time_arb | 0.0% | $0.00 | $0.00 | 0.000 | 0.000 | 0.0000 | 0.00 |
| vol_event | 69.0% | $426.83 | $148.75 | 0.581 | 0.291 | 0.4131 | 0.60 |

## Capital Allocation

| Strategy | Allocated | % of Total |
|----------|-----------|------------|
| cross_asset | $5,332 | 5.3% |
| cross_platform | $7,861 | 7.9% |
| longshot | $5,332 | 5.3% |
| negrisk | $16,899 | 16.9% |
| single_binary | $42,660 | 42.7% |
| stat_arb | $5,332 | 5.3% |
| time_arb | $5,332 | 5.3% |
| vol_event | $11,250 | 11.3% |

## Baseline vs Risk-Enhanced Comparison

| Strategy | Mode | Trades | PnL | Return | Sharpe | MDD | Win Rate |
|----------|------|--------|-----|--------|--------|-----|----------|
| cross_asset | baseline | 35 | $-118.98 | -0.95% | -2.97 | -1.02% | 51.4% |
| cross_asset | **risk-sized** | 35 | $-118.98 | -2.23% | -2.97 | -2.39% | 51.4% |
| cross_platform | baseline | 14 | $87823.51 | 702.59% | 4.37 | 0.00% | 100.0% |
| cross_platform | **risk-sized** | 14 | $138072.58 | 1756.47% | 4.37 | 0.00% | 100.0% |
| longshot | baseline | 1 | $55.51 | 0.44% | 0.00 | 0.00% | 100.0% |
| longshot | **risk-sized** | 1 | $55.51 | 1.04% | 0.00 | 0.00% | 100.0% |
| negrisk | baseline | 356 | $976.63 | 7.81% | 15.78 | 0.00% | 100.0% |
| negrisk | **risk-sized** | 356 | $16504.56 | 97.66% | 15.78 | 0.00% | 100.0% |
| single_binary | baseline | 2053 | $27607.34 | 220.86% | 69.31 | 0.00% | 100.0% |
| single_binary | **risk-sized** | 2053 | $1177718.01 | 2760.73% | 69.31 | 0.00% | 100.0% |
| stat_arb | baseline | 35 | $17016.52 | 136.13% | 3.63 | -36.82% | 62.9% |
| stat_arb | **risk-sized** | 35 | $3403.30 | 63.82% | 3.63 | -18.13% | 62.9% |
| vol_event | baseline | 29 | $7197.75 | 57.58% | 9.53 | -5.76% | 69.0% |
| vol_event | **risk-sized** | 29 | $68008.86 | 604.50% | 9.53 | -17.16% | 69.0% |

**Baseline Total PnL**: $140,558.30
**Risk-Enhanced Total PnL**: $1,403,643.84
**Improvement**: +898.6%

---
*Generated 2026-04-17 00:48*

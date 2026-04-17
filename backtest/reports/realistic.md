# Realistic Backtest Report (with Execution Friction)

## Friction Model

| Parameter | Polymarket | predict.fun |
|-----------|-----------|-------------|
| Half-spread | 60 bps (1.2% round-trip) | 100 bps (2% round-trip) |
| Market impact | 0.08 × sqrt(size/liquidity) | 0.15 × sqrt(size/liquidity) |
| Execution failure rate | 15% | 20% |
| Partial fill (mean) | ~77% | ~60% |
| Latency adverse move | σ=0.3% | σ=0.5% |

## Ideal vs Realistic

| Strategy | Mode | Trades | PnL | Return | Sharpe | Win Rate | Max DD |
|----------|------|--------|-----|--------|--------|----------|--------|
| cross_venue | Ideal | 200 | $26846.56 | 26.85% | 9.42 | 100.0% | 0.00% |
| negrisk | Ideal | 516 | $2667.90 | 2.67% | 15.14 | 100.0% | 0.00% |
| single_binary | Ideal | 3006 | $40761.55 | 40.76% | 65.47 | 100.0% | 0.00% |
| cross_venue | Realistic | 200 | $6765.19 | 6.77% | 4.02 | 33.5% | -0.70% |
| negrisk | Realistic | 516 | $-20859.78 | -20.86% | -36.82 | 0.0% | -20.81% |
| single_binary | Realistic | 3006 | $-1553.30 | -1.55% | -2.97 | 28.3% | -1.57% |

## Summary

- **Ideal total PnL**: $70,276.01
- **Realistic total PnL**: $-15,647.89
- **PnL reduction from friction**: 122.3%

## Why Win Rates Drop

1. **Slippage**: buying at ask (not mid) reduces effective edge per trade
2. **Execution failure**: ~15-20% of arb attempts fail (window closes)
3. **Partial fills**: only ~60-77% of order fills on average
4. **Market impact**: $1000 orders move price on thin books
5. **Latency**: price moves adversely during detection→execution gap

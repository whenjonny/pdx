# Real-Data Backtest Report

*Generated from Polymarket historical data*

## Strategy Performance

| Strategy | Trades | Total PnL | Return | Sharpe | Max DD | Win Rate |
|----------|--------|-----------|--------|--------|--------|----------|
| cross_asset | 50 | $-32.45 | -0.03% | -0.89 | -0.12% | 58.0% |
| cross_platform | 20 | $133142.07 | 133.14% | 5.03 | 0.00% | 100.0% |
| cross_venue | 200 | $13686.11 | 13.69% | 21.84 | 0.00% | 100.0% |
| longshot | 1 | $55.51 | 0.06% | 0.00 | 0.00% | 100.0% |
| negrisk | 516 | $2667.90 | 2.67% | 15.14 | 0.00% | 100.0% |
| single_binary | 3006 | $40761.55 | 40.76% | 65.47 | 0.00% | 100.0% |
| stat_arb | 50 | $-7558.03 | -7.56% | -1.78 | -10.15% | 52.0% |

## Notes

- Data source: Polymarket CLOB API (real historical prices)
- NegRisk data from multi-outcome events (3+ outcomes)
- Cross-platform uses real Polymarket prices with simulated Kalshi lag
- Capital base: $100,000
- No transaction costs on Polymarket (0% maker fee)

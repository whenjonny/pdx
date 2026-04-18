---
name: wallstreet-masters
description: "Analyze a stock through the lens of four Wall Street masters (Buffett, Burry, Munger, Lynch). Each produces a bullish/bearish/neutral signal with confidence and reasoning."
version: 0.1.0
user-invocable: true
---

# Wall Street Masters Stock Analysis

Apply the investment framework of four legendary investors to a target ticker. Each master emits:

```json
{"signal": "bullish|bearish|neutral", "confidence": 0-100, "reasoning": "..."}
```

Reference implementations (Python, from `zhound420/ai-hedge-fund`) are in `references/`. They depend on an external `langchain` / financial-data API stack — treat them as **specification**, not directly runnable. Claude applies the framework using fetched fundamentals + web search.

## Four Masters

### Warren Buffett — `references/warren_buffett.py`
Value investing with a long horizon. Signals on:
- **Fundamentals**: ROE ≥ 15%, debt/equity < 0.5, operating margin ≥ 15%, current ratio ≥ 1.5
- **Consistency**: 10 yr stable / growing net income
- **Moat**: durable ROE / margin vs peers
- **Pricing power**: gross margin trend
- **Book value growth**: equity CAGR
- **Management**: share buybacks ≥ dividends, disciplined capex
- **Intrinsic value**: owner-earnings DCF with margin of safety ≥ 30%

### Michael Burry — `references/michael_burry.py`
Contrarian deep-value + catalyst-driven short positions. Signals on:
- **FCF yield** (FCF / market cap) — ideally ≥ 15%
- **EV/EBIT** — ideally ≤ 6
- **Hard-asset balance sheet**: cash + tangible equity
- **Insider buying / buybacks**
- **Contrarian sentiment**: negative news flow, forced-selling

### Charlie Munger — `references/charlie_munger.py`
"Great business at a fair price." Signals on:
- **Moat strength**: high ROIC (≥ 20%) persistent over 10 yr
- **Management quality**: capital allocation track record
- **Business predictability**: low earnings volatility
- **Valuation**: normalized FCF yield
- **Mental-model checks**: incentive alignment, inversion, red flags

### Peter Lynch — `references/peter_lynch.py`
"Invest in what you know." GARP (growth at reasonable price). Signals on:
- **PEG ratio** (≤ 1 bullish, ≤ 0.5 strong)
- **Growth**: EPS / revenue 3-5 yr CAGR ≥ 15%
- **Category**: fast grower / stalwart / turnaround / asset play / cyclical
- **Balance sheet**: debt/equity trend
- **Insider buying**

## Workflow

### /masters-analyze <ticker>

1. Fetch fundamentals for the ticker (user provides an API key or uses a free source):
   - yfinance: `pip install yfinance`
   - SEC EDGAR for filings
   - Finviz / Stockanalysis.com for screens

2. For each of the four masters, compute the checks in their `.py` reference file. Each check returns a sub-score; sum them and normalize to a `confidence` 0-100.

3. Emit a consolidated report:

```
Ticker: AAPL
─────────────────────────────────────
Buffett   | bullish  | 78 | Durable moat, 25% ROE, 20% op margin, intrinsic value 12% above price
Burry     | neutral  | 42 | FCF yield 3.5% (below threshold), strong balance sheet
Munger    | bullish  | 71 | ROIC 35%, predictable cash flows, fair valuation
Lynch     | bearish  | 35 | PEG 2.1, slowing growth, stalwart category
─────────────────────────────────────
Consensus: 2 bullish / 1 neutral / 1 bearish → mild bullish
```

4. If ≥ 3 masters bullish and avg confidence ≥ 65 → flag as high-conviction long.
5. If ≥ 3 masters bearish → flag as avoid / short candidate.

## Notes
- Only for research / education. Not investment advice.
- Original source: https://github.com/zhound420/ai-hedge-fund
- To run the original LLM-driven agents end-to-end, set up the upstream project with `FINANCIAL_DATASETS_API_KEY` and a LangChain-compatible LLM.

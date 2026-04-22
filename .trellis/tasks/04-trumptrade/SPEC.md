# Task 04 — Trump Trading Monitor (Week 1 + Week 2)

Status: Week 1 DONE, Week 2 DONE. Live paper trading not yet validated.
Created: 2026-04-22
Updated: 2026-04-22
Owner: —

## Quick links
- Runbook: `trumptrade/RUNBOOK.md`
- Playbook: `trumptrade/config/trump_policy_playbook.yaml`
- Tests: `python -m pytest -v` in `trumptrade/` (15 passing)

## Goal

Build a **read-only** monitor that watches Trump-originated policy signals, classifies their market impact, expands to a ticker basket via a playbook, and emits alerts. **No order execution.** The user evaluates signal accuracy and decides Week 2 actions.

## Non-Goals (Week 1)

- Placing any orders (paper or real)
- Real-time sub-second latency (LLM chain takes 10-60s; acceptable)
- Scraping Truth Social directly — use mock / file-based source
- TradingAgents deep-analysis integration (Phase 2)

## Architecture

```
Signal Source (Truth Social / X / RSS / local file)
        |
        v
Policy Classifier (Claude Opus 4.7, prompt-cached playbook)
        |
        v (category + sentiment + follow-through confidence)
Basket Expander (deterministic YAML lookup)
        |
        v (list of {ticker, side, weight, thesis})
Alerter (stdout / file; Slack/Telegram later)
```

## Components

### 1. Signal Source (`trumptrade/signals/`)
Abstract interface `SignalSource` with methods:
- `poll() -> list[Signal]`: fetch new signals since last call
- `Signal` = `{id, author, timestamp, text, url, metadata}`

Implementations:
- `MockFileSource(path)` — reads JSON from a local file (for testing / demo). Ships with 5 sample Trump posts in `data/sample_posts/`.
- `TruthSocialSource` — **stub**, raises `NotImplementedError` with a message explaining the user needs `truthbrush` (third-party) or authenticated cookies. Not required for Week 1.
- `RSSFeedSource(url)` — reads from a pre-configured RSS (e.g., WH press briefing feed).

### 2. Policy Classifier (`trumptrade/classifier/`)
Single function:
```python
classify(signal: Signal, playbook: Playbook) -> Classification
```
where
```python
Classification = {
    category: str,          # matches playbook.categories key
    sentiment: "hawkish" | "dovish" | "neutral",
    follow_through: float,  # 0-1, prob. of actual policy impact
    rationale: str,
    confidence: float,      # 0-1, classifier's own confidence
    original_excerpt: str,  # quoted text anchoring the claim
}
```

Implementation:
- Uses **Anthropic Python SDK** with model `claude-opus-4-7`.
- System prompt embeds the playbook (categories + descriptions + follow-through priors) with `cache_control: {"type": "ephemeral"}` — frozen across calls.
- User prompt = signal text only (volatile).
- `output_config.format` = JSON schema enforcing the `Classification` shape.
- `thinking: {type: "adaptive"}`, `output_config.effort: "high"` — classification benefits from reasoning.
- Graceful error handling: if classification fails, emit a `Classification` with `category="unknown"` and `confidence=0.0`.

### 3. Basket Expander (`trumptrade/execution/basket.py`)
Pure function, no LLM:
```python
expand_basket(classification, playbook) -> list[BasketLeg]
BasketLeg = {ticker, side: "long"|"short", weight, thesis}
```
Logic: look up `playbook.categories[category].<sentiment>_long` and `<sentiment>_short`. Scale weights by `classification.confidence * classification.follow_through`.

### 4. Alerter (`trumptrade/execution/alerter.py`)
```python
alert(signal, classification, basket, min_confidence)
```
Writes to:
- stdout (formatted report)
- `data/alerts.jsonl` (append-only log for later backtest)

Skips alert if `classification.confidence * classification.follow_through < min_confidence`.

### 5. Pipeline (`trumptrade/pipeline.py`)
Orchestrator:
```python
class Pipeline:
    def run_once(self): ...  # poll once, process all new signals
    def run_loop(self, interval_sec=30): ...  # poll continuously
```

### 6. CLI (`trumptrade/cli.py`)
```
trumptrade analyze <post_id>           # one-shot analysis
trumptrade watch --source mock         # continuous watch loop
trumptrade watch --source rss --url ...
```

## Dependencies
- `anthropic >= 0.70`
- `pyyaml`
- `pydantic >= 2`
- `click` (CLI)

## Config
- `ANTHROPIC_API_KEY` environment variable (required)
- `TRUMPTRADE_PLAYBOOK` — path to playbook YAML (default: `config/trump_policy_playbook.yaml`)
- `TRUMPTRADE_DATA_DIR` — where alerts/logs go (default: `data/`)

## Risk Gates (enforced at Alerter + pipeline level)
From playbook `risk_gates`:
- Only emit alerts above `min_confidence_to_alert` (default 0.55)
- Never exceed `max_basket_notional_pct` in sizing logic (Week 2+)
- Reserve `walk_back_hard_stop` for Week 2

## Testing
- `tests/test_classifier.py` — mock Anthropic client, verify schema conformance
- `tests/test_basket.py` — pure function, no mocks needed
- `tests/test_pipeline_e2e.py` — end-to-end with `MockFileSource` + mocked classifier

## Week 1 Exit Criteria
1. `trumptrade watch --source mock` runs, processes 5 sample posts, emits structured alerts
2. For each alert: category, sentiment, basket, confidence all visible
3. `data/alerts.jsonl` contains 1 line per alert
4. User can read the output and agree/disagree with the classification (manual QA of 20+ real Trump posts)

## Week 2 — DONE
- `execution/walkback.py` — 48h opposite-sentiment reversal detector. Inverts
  prior basket legs to produce close orders. Unit tested.
- `execution/position_sizer.py` — risk-based sizing (risk% × account /
  (price × stop%)), with caps: `max_single_ticker_notional_pct` and
  `max_basket_notional_pct`. Short legs skip cash cap (margin assumed).
- `execution/paper_trader.py` — `SimulatedPaperTrader` (pure, for backtest +
  tests) and `AlpacaPaperTrader` (lazy-import alpaca-py).
- `backtest/harness.py` + `backtest/prices.py` — replay alerts.jsonl, open
  positions at signal post date, close after `hold_days` or on walk-back.
  `StubPriceSource` (deterministic, offline) + `YFinancePriceSource`
  (lazy-import).
- CLI commands: `trumptrade backtest`, `trumptrade paper-trade`.
- Fake keyword classifier (`classifier/fake_classifier.py`) — runs without
  ANTHROPIC_API_KEY. Used for offline demo and CI.
- 20 sample posts covering all 9 categories + walk-back pair + 4 noise posts.

## Week 3+ (later)
- TradingAgents deep analysis per ticker in basket (optional, expensive)
- Confidence calibration from P&L feedback (analogous to TradingAgents `reflect_and_remember`)
- Multi-source cross-validation (Truth + X + WH 3/3)
- Sharpe / max DD / drawdown-aware stop sizing
- 1-hour prompt cache TTL for continuous-watch workloads
- Truth Social real ingestion (requires truthbrush or alternative)
- Live Alpaca trading validation (currently paper-only gate)
